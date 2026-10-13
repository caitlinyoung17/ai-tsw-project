"""Pure text helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def preprocess_ocr_text(text: str) -> str:
    """Minimal whitespace cleanup; does not strip punctuation or non-ASCII."""
    text = text.replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def normalize_for_comparison(s: str) -> str:
    """Lowercase letters and single spaces only; accents folded to ASCII."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def normalize_label_for_matching(s: str) -> str:
    """Lowercase, collapse whitespace, drop one trailing .,;:!?"""
    s = re.sub(r"\s+", " ", (s or "").lower().strip())
    return re.sub(r"[.,;:!?]$", "", s)


def dedupe_preserve_order(items: Iterable[T],
                          key: Callable[[T], object] = normalize_for_comparison
                          ) -> list[T]:
    seen: set = set()
    out: list[T] = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out
