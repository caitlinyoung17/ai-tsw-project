"""Single word-overlap relevance function shared by FAST/Getty/geographic."""
from __future__ import annotations


def word_overlap(label: str, query: str) -> bool:
    """True if label and query share at least one (case-insensitive) word."""
    q = {w.lower() for w in query.split()}
    return bool(q & {w.lower() for w in (label or "").split()})
