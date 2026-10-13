"""Reprocess one failed item through step 1's MetadataExtractor."""
from __future__ import annotations

import logging
import os
import time
from typing import Callable

from processors.metadata_extraction.collector import Document, default_pdf_reader
from processors.metadata_extraction.extractor import MetadataExtractor
from processors.metadata_extraction.results import ExtractionResult
from utils.exceptions import EmptyDocumentError, LLMError

logger = logging.getLogger(__name__)


def default_text_loader(path: str) -> str:
    if path.lower().endswith(".pdf"):
        return default_pdf_reader(path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class ItemReprocessor:
    def __init__(self, extractor: MetadataExtractor,
                 text_loader: Callable[[str], str] = default_text_loader,
                 attempts: int = 3, backoff: float = 4.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.extractor = extractor
        self.text_loader = text_loader
        self.attempts = attempts
        self.backoff = backoff
        self.sleep = sleep

    def _document(self, item: dict) -> Document:
        path = item.get("file_path") or ""
        filename = item.get("filename") or os.path.basename(path)
        if not path:
            raise EmptyDocumentError(f"No source path for {filename}")
        try:
            text = self.text_loader(path)
        except (OSError, FileNotFoundError) as e:
            raise EmptyDocumentError(f"No source content for {filename}",
                                     path=path, cause=e)
        return Document(filename, filename, path, text or "")

    def reprocess(self, item: dict) -> ExtractionResult:
        """Raises EmptyDocumentError (never retried) or the last LLMError."""
        document = self._document(item)
        last: LLMError | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                return self.extractor.extract(document)
            except EmptyDocumentError:
                raise
            except LLMError as e:
                last = e
                logger.warning("Reprocess %s attempt %d/%d failed: %s",
                               document.filename, attempt, self.attempts, e)
                if attempt < self.attempts:
                    self.sleep(self.backoff * attempt)
        assert last is not None
        raise last
