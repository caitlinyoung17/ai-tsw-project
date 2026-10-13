"""Typed results for metadata extraction (replaces the legacy 9-tuples)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple, Union

from api.llm_core.types import Usage


@dataclass(frozen=True)
class ExtractionResult:
    doc_id: str
    metadata: dict
    usage: Usage
    raw: str
    elapsed: float = 0.0
    warnings: Tuple[str, ...] = ()  # e.g. partial chunk failures


@dataclass(frozen=True)
class Succeeded:
    result: ExtractionResult

    @property
    def doc_id(self) -> str:
        return self.result.doc_id


@dataclass(frozen=True)
class Failed:
    doc_id: str
    error: BaseException


ExtractionOutcome = Union[Succeeded, Failed]


@dataclass(frozen=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    usage: Usage
    mode: str  # "BATCH" | "INDIVIDUAL"
    elapsed: float = 0.0
    errors: Dict[str, str] = field(default_factory=dict)


def summarize(outcomes: Dict[str, ExtractionOutcome], mode: str,
              elapsed: float = 0.0, extra_errors: Dict[str, str] = None) -> RunSummary:
    prompt = completion = cached = ok = 0
    errors = dict(extra_errors or {})
    for doc_id, o in outcomes.items():
        if isinstance(o, Succeeded):
            ok += 1
            prompt += o.result.usage.prompt_tokens
            completion += o.result.usage.completion_tokens
            cached += o.result.usage.cached_tokens
        else:
            errors[doc_id] = str(o.error)
    return RunSummary(total=len(outcomes), succeeded=ok, failed=len(outcomes) - ok,
                      usage=Usage(prompt, completion, cached), mode=mode,
                      elapsed=elapsed, errors=errors)
