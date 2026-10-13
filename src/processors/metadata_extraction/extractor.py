"""Single-document metadata extraction."""
from __future__ import annotations

import time
from typing import Callable, Optional, Protocol, List

from api.llm_core.prompts import PromptTemplate
from api.llm_core.types import CompletionRequest, CompletionResult
from api.llm_core.validation import parse_json_response, postprocess_api_response
from prompts import EXTRACTION, CallParams, metadata_extraction_template
from utils.exceptions import EmptyDocumentError, LLMResponseError
from utils.text import preprocess_ocr_text

from .collector import Document
from .results import ExtractionResult


class ChunkingStrategy(Protocol):
    """Long-document strategy (changeset 07); None means whole-document only."""

    def needs_chunking(self, text: str) -> bool: ...

    def run(self, text: str, doc_id: str = ""): ...  # -> MergedMetadata


class MetadataExtractor:
    def __init__(self, provider, model: str,
                 template: Optional[PromptTemplate] = None,
                 params: CallParams = EXTRACTION,
                 ocr_preprocess: Callable[[str], str] = preprocess_ocr_text,
                 chunking: Optional[ChunkingStrategy] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.provider = provider
        self.model = model
        self.template = template or metadata_extraction_template()
        self.params = params
        self.ocr_preprocess = ocr_preprocess
        self.chunking = chunking
        self.clock = clock

    def build_request(self, document: Document) -> CompletionRequest:
        """Raises EmptyDocumentError if the text is empty after preprocessing."""
        text = self.ocr_preprocess(document.text or "").strip()
        if not text:
            raise EmptyDocumentError(f"Empty document: {document.filename}",
                                     path=document.path)
        messages = self.template.render(text=text)
        return CompletionRequest(model=self.model, messages=tuple(messages),
                                 max_tokens=self.params.max_tokens,
                                 temperature=self.params.temperature)

    def parse(self, document: Document, completion: CompletionResult,
              elapsed: float = 0.0) -> ExtractionResult:
        """Turn a completion (individual or batch) into an ExtractionResult."""
        raw = (completion.content or "").strip()
        if not raw:
            raise LLMResponseError(f"Empty response for {document.filename}",
                                   path=document.path)
        parsed = parse_json_response(raw)
        if not parsed:
            raise LLMResponseError(f"No metadata in response for {document.filename}",
                                   path=document.path)
        return ExtractionResult(document.doc_id, postprocess_api_response(parsed),
                                completion.usage, raw, elapsed)

    def _prepared_text(self, document: Document) -> str:
        return self.ocr_preprocess(document.text or "").strip()

    def needs_chunking(self, document: Document) -> bool:
        return bool(self.chunking and
                    self.chunking.needs_chunking(self._prepared_text(document)))

    def _extract_chunked(self, document: Document) -> ExtractionResult:
        start = self.clock()
        merged = self.chunking.run(self._prepared_text(document), document.doc_id)
        return ExtractionResult(document.doc_id, postprocess_api_response(merged.metadata),
                                merged.usage, merged.raw, self.clock() - start,
                                tuple(merged.warnings))

    def extract(self, document: Document) -> ExtractionResult:
        if self.chunking is not None:
            if not self._prepared_text(document):
                raise EmptyDocumentError(f"Empty document: {document.filename}",
                                         path=document.path)
            if self.needs_chunking(document):
                return self._extract_chunked(document)
        request = self.build_request(document)
        start = self.clock()
        completion = self.provider.complete(request)
        return self.parse(document, completion, self.clock() - start)
