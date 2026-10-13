"""Provider-neutral value types for LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: Tuple[Message, ...]
    max_tokens: int
    temperature: float
    response_format: Optional[Mapping[str, Any]] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class CompletionResult:
    content: str
    usage: Usage
    model: str
    finish_reason: Optional[str] = None
    raw: Any = None


@dataclass(frozen=True)
class BatchItem:
    custom_id: str
    request: CompletionRequest


@dataclass(frozen=True)
class BatchHandle:
    batch_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchOutcome:
    """Result for one batch item: exactly one of result/error is set."""
    custom_id: str
    result: Optional[CompletionResult] = None
    error: Optional[str] = None
