"""Detect failed items from a batch run. Pure functions, no I/O."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence

from utils import schema

ERROR_INDICATORS = (
    "Processing error:", "Error:", "Failed to", "Exception:", "Traceback:",
    "REPROCESSING FAILED:", "Timeout", "Connection error", "API error",
    "Internal server error", "Rate limit", "Service unavailable", "Bad gateway",
)
_WS = {" ", "\n", "\t", "\r"}
_REQUIRED_KEYS = tuple(schema.to_snake(schema.empty_metadata()).keys())
_REQUIRED_NONEMPTY = (schema.TITLE, schema.ABSTRACT)


class FailureReason(Enum):
    NO_ANALYSIS = "Missing analysis section"
    EXPLICIT_ERROR = "Explicit processing error in response"
    EMPTY_RESPONSE = "Empty response"
    BROKEN_JSON = "Completely broken JSON structure"
    REPETITION = "Extreme repetition/corruption pattern detected"
    MISSING_FIELDS = "Required metadata fields missing"


@dataclass(frozen=True)
class FailedItem:
    index: int
    item: dict
    reason: FailureReason


def max_char_dominance(text: str) -> float:
    """Share of `text` taken by its most common non-whitespace character."""
    counts = Counter(c for c in text if c not in _WS)
    if not counts or not text:
        return 0.0
    return max(counts.values()) / len(text)


def has_extreme_repetition(text: str, max_char_count: int = 2500,
                           max_word_run: int = 500) -> bool:
    if not text or len(text.strip()) < 30:
        return False
    if len(text) > max_char_count:
        counts = Counter(c for c in text if c not in _WS)
        if counts:
            top = max(counts.values())
            if top > max_char_count:
                return True
            if top / len(text) > 0.8 and len(text) > 2000:
                return True
    words = text.split()
    run, prev = 0, None
    for w in words:
        run = run + 1 if w == prev else 1
        prev = w
        if run >= max_word_run:
            return True
    return False


def is_completely_broken_json(raw: str) -> bool:
    if not raw or len(raw.strip()) < 10:
        return False
    opens, closes = raw.count("{"), raw.count("}")
    return any((
        opens == 0 and closes == 0,
        abs(opens - closes) > 12,
        raw.strip().startswith(("Error:", "Failed:", "Exception:")) and len(raw) < 50,
        len(raw) > 1000 and max_char_dominance(raw) >= 0.8,
    ))


def classify_item(item: dict) -> FailureReason | None:
    analysis = item.get("analysis") if isinstance(item, dict) else None
    if not isinstance(analysis, dict):
        return FailureReason.NO_ANALYSIS
    raw = analysis.get("raw_response", "") or ""
    if any(i in raw for i in ERROR_INDICATORS):
        return FailureReason.EXPLICIT_ERROR
    if not raw.strip():
        return FailureReason.EMPTY_RESPONSE
    if is_completely_broken_json(raw):
        return FailureReason.BROKEN_JSON
    if has_extreme_repetition(raw):
        return FailureReason.REPETITION
    if (any(k not in analysis for k in _REQUIRED_KEYS)
            or any(not str(analysis.get(k) or "").strip() for k in _REQUIRED_NONEMPTY)):
        return FailureReason.MISSING_FIELDS
    return None


def detect_failed_items(items: Sequence[dict]) -> List[FailedItem]:
    out = []
    for i, item in enumerate(items):
        reason = classify_item(item)
        if reason is not None:
            out.append(FailedItem(i, item, reason))
    return out


class FailureDetector:
    """Object wrapper so callers can inject a detector."""

    def detect(self, items: Sequence[dict]) -> List[FailedItem]:
        return detect_failed_items(items)
