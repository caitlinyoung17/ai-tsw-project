"""Typed exception hierarchy for the TSW pipeline.

Policy
------
Raise: missing/invalid required input, I/O failure, malformed payload,
API failure.
Return a default: zero search hits, empty subject list, LLM legitimately
selecting nothing.
Never return None or bool-as-error from a public function.
"""
from __future__ import annotations

from typing import Optional


class TswError(Exception):
    """Base class for all pipeline errors."""

    def __init__(self, message: str = "", *, path: Optional[str] = None,
                 cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


class ConfigError(TswError):
    """Missing env var / bad config value."""


class WorkflowFilesNotFound(TswError):
    """Run folder lacks text_workflow.json/.xlsx."""


class WorkflowFormatError(TswError):
    """json/xlsx present but malformed."""


class EmptyDocumentError(TswError):
    """Input text empty after cleaning."""


class LLMError(TswError):
    """Base for LLM failures."""


class LLMResponseError(LLMError):
    """No choices, empty content, truncated."""


class PayloadValidationError(LLMError):
    """Request or response schema invalid."""


class LLMTransientError(LLMError):
    """Retryable (rate limit, timeout, 5xx)."""


class BatchError(LLMError):
    """Batch failed / expired / unparsable."""


class UnknownModelError(TswError):
    """No pricing for model (strict mode)."""


class VocabularyError(TswError):
    """Base for vocabulary failures."""


class VocabularyLoadError(VocabularyError):
    """File missing / unreadable."""


class VocabularyFormatError(VocabularyError):
    """Shape wrong."""


class VocabHttpError(VocabularyError):
    """Transport failure to a vocab service."""


class VocabParseError(VocabularyError):
    """Service returned unparsable payload."""


class StepFailedError(TswError):
    """Wraps a processor failure with step name."""

    def __init__(self, message: str = "", *, step: Optional[str] = None,
                 path: Optional[str] = None,
                 cause: Optional[BaseException] = None) -> None:
        super().__init__(message, path=path, cause=cause)
        self.step = step
