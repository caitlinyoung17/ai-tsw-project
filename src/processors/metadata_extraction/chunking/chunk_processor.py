"""Substep 2: per-piece LLM calls (no merging)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from api.llm_core.types import CompletionRequest, Usage
from api.llm_core.validation import parse_json_response, postprocess_api_response
from prompts import (CHUNK, EXTRACTION, CallParams, abstract_completion_template,
                     chunk_entities_template, front_matter_template)
from utils.exceptions import LLMResponseError
from utils.text import normalize_for_comparison

_FRONT_KEYS = ("title", "creator", "date", "department", "abstract", "type",
               "access", "publisher", "sponsor", "language")


@dataclass(frozen=True)
class FrontMatterResult:
    metadata: dict
    abstract_complete: bool
    usage: Usage
    raw: str


@dataclass(frozen=True)
class ChunkResult:
    index: int
    subjects: List[str]
    named_entities: List[str]
    geographic_entities: List[str]
    content_warning: str
    usage: Usage
    raw: str


@dataclass(frozen=True)
class AbstractResult:
    abstract: str
    complete: bool
    usage: Usage
    raw: str


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(a.prompt_tokens + b.prompt_tokens,
                 a.completion_tokens + b.completion_tokens,
                 a.cached_tokens + b.cached_tokens)


def abstract_looks_complete(abstract: str, text: str, tail: int = 200) -> bool:
    """Heuristic: the abstract's end is visible with text continuing after it."""
    abstract = (abstract or "").strip()
    if not abstract:
        return False
    key = normalize_for_comparison(abstract[-60:])
    norm = normalize_for_comparison(text)
    pos = norm.rfind(key) if key else -1
    if pos < 0:
        return True  # synthesized abstract (not quoted from the text)
    return len(norm) - (pos + len(key)) >= tail


class ChunkProcessor:
    def __init__(self, provider, model: str, templates: Optional[dict] = None,
                 front_params: CallParams = EXTRACTION,
                 chunk_params: CallParams = CHUNK) -> None:
        self.provider = provider
        self.model = model
        t = templates or {}
        self.front_template = t.get("front") or front_matter_template()
        self.chunk_template = t.get("chunk") or chunk_entities_template()
        self.abstract_template = t.get("abstract") or abstract_completion_template()
        self.front_params = front_params
        self.chunk_params = chunk_params

    def _call(self, template, text: str, params: CallParams):
        req = CompletionRequest(model=self.model,
                                messages=tuple(template.render(text=text)),
                                max_tokens=params.max_tokens,
                                temperature=params.temperature)
        completion = self.provider.complete(req)
        raw = (completion.content or "").strip()
        if not raw:
            raise LLMResponseError("Empty response")
        parsed = parse_json_response(raw)
        if not parsed:
            raise LLMResponseError("No JSON in response")
        return parsed, completion.usage, raw

    def process_front_matter(self, text: str) -> FrontMatterResult:
        parsed, usage, raw = self._call(self.front_template, text, self.front_params)
        parsed = postprocess_api_response(parsed)
        meta = {k: parsed.get(k, "") for k in _FRONT_KEYS}
        return FrontMatterResult(meta, abstract_looks_complete(meta["abstract"], text),
                                 usage, raw)

    def process_chunk(self, text: str, index: int, total: int) -> ChunkResult:
        parsed, usage, raw = self._call(self.chunk_template, text, self.chunk_params)
        p = postprocess_api_response(parsed)
        return ChunkResult(index, list(p["subjects"]), list(p["namedEntities"]),
                           list(p["geographicEntities"]), p["contentWarning"],
                           usage, raw)

    def process_abstract_chunk(self, text: str) -> AbstractResult:
        parsed, usage, raw = self._call(self.abstract_template, text, self.chunk_params)
        return AbstractResult(str(parsed.get("abstract") or "").strip(),
                              bool(parsed.get("abstract_complete")), usage, raw)
