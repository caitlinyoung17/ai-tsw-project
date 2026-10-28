"""Single-entry vocabulary selection. Failures are explicit, never an empty success."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from api.llm_core import (CompletionRequest, CompletionResult, LLMProvider,
                          RetryPolicy, Usage, call_with_retry,
                          parse_json_response)
from metadata_standard import MetadataStandard, Term
from prompts.params import SELECTION, CallParams
from prompts.vocab_selection import render_vocab_selection
from utils.exceptions import LLMError, PayloadValidationError

logger = logging.getLogger(__name__)


class SelectionStatus(str, Enum):
    SELECTED = "selected"
    NONE_SELECTED = "none_selected"
    SKIPPED_NO_CANDIDATES = "skipped_no_candidates"
    FAILED = "failed"


@dataclass(frozen=True)
class ExtractedEntry:
    entry_id: int
    title: str = ""
    abstract: str = ""
    subjects: tuple = ()

    @classmethod
    def from_item(cls, entry_id: int, item: dict) -> "ExtractedEntry":
        a = item.get("analysis") or {}
        return cls(entry_id, str(a.get("title") or "").strip(),
                   str(a.get("abstract") or "").strip())


@dataclass(frozen=True)
class SelectionResult:
    status: SelectionStatus
    terms: list = field(default_factory=list)  # list[Term]
    usage: Optional[Usage] = None
    error: Optional[str] = None
    unmatched_labels: list = field(default_factory=list)
    raw: Optional[str] = None

    @property
    def has_issue(self) -> bool:
        return self.status is SelectionStatus.FAILED or bool(self.unmatched_labels)


Renderer = Callable[[str, str, str], list]


class VocabularySelector:
    def __init__(self, provider: LLMProvider, model: str, *,
                 templates: Renderer = render_vocab_selection,
                 params: CallParams = SELECTION, max_attempts: int = 5,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.provider = provider
        self.model = model
        self.templates = templates
        self.params = params
        self.max_attempts = max_attempts
        self.sleep = sleep

    def build_request(self, entry: ExtractedEntry,
                      standard: MetadataStandard) -> Optional[CompletionRequest]:
        """None when there are no candidates (nothing to ask)."""
        if not standard.has_candidates():
            return None
        messages = self.templates(entry.title, entry.abstract, standard.render_for_prompt())
        return CompletionRequest(model=self.model, messages=tuple(messages),
                                 max_tokens=self.params.max_tokens,
                                 temperature=self.params.temperature,
                                 metadata={"entry_id": entry.entry_id})

    def select(self, entry: ExtractedEntry, standard: MetadataStandard) -> SelectionResult:
        request = self.build_request(entry, standard)
        if request is None:
            return SelectionResult(SelectionStatus.SKIPPED_NO_CANDIDATES)
        policy = RetryPolicy(max_attempts=self.max_attempts, sleep=self.sleep)
        try:
            completion = call_with_retry(lambda: self.provider.complete(request), policy)
        except LLMError as e:
            logger.error("Selection failed for entry %s: %s", entry.entry_id, e)
            return SelectionResult(SelectionStatus.FAILED, error=str(e))
        return self.to_result(completion, standard)

    def to_result(self, completion: Optional[CompletionResult], standard: MetadataStandard,
                  error: Optional[str] = None) -> SelectionResult:
        """Shared by the individual and batch paths."""
        if completion is None:
            return SelectionResult(SelectionStatus.FAILED, error=error or "No response")
        usage = completion.usage
        try:
            labels = MetadataStandard.validate_selection(
                parse_json_response(completion.content))
        except LLMError as e:  # LLMResponseError / PayloadValidationError
            return SelectionResult(SelectionStatus.FAILED, usage=usage,
                                   error=f"Unparseable selection: {e}",
                                   raw=completion.content)
        terms: list[Term] = standard.match_selected_labels(labels)
        unmatched = standard.unmatched_labels(labels)
        status = SelectionStatus.SELECTED if terms else SelectionStatus.NONE_SELECTED
        return SelectionResult(status, terms, usage, None, unmatched,
                               raw=completion.content)
