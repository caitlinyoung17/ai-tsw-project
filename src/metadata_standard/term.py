"""Controlled-vocabulary term value object and source priority."""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from enum import Enum
from typing import Any, Mapping

from utils.exceptions import VocabularyFormatError


class VocabSource(str, Enum):
    GETTY_AAT = "Getty AAT"
    LCSH = "LCSH"
    FAST = "FAST"
    GETTY_TGN = "Getty TGN"


# Lower number = higher priority.
SOURCE_PRIORITY: dict[str, int] = {
    VocabSource.GETTY_AAT.value: 1,
    VocabSource.LCSH.value: 2,
    VocabSource.FAST.value: 3,
    VocabSource.GETTY_TGN.value: 4,
}
DEFAULT_PRIORITY = 999


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, DEFAULT_PRIORITY)


@dataclass(frozen=True)
class Term:
    label: str
    uri: str
    source: str
    description: str = ""
    qid: str = ""
    subject_id: str = ""
    type: str = ""
    tag: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Term":
        if not isinstance(d, Mapping):
            raise VocabularyFormatError(f"Term must be a mapping, got {type(d).__name__}")
        for key in ("label", "uri", "source"):
            if key not in d:
                raise VocabularyFormatError(f"Term missing required key '{key}': {dict(d)!r}")
        names = [f.name for f in fields(cls)]
        return cls(**{n: ("" if d.get(n) is None else str(d[n])) for n in names if n in d})

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def priority(self) -> int:
        return source_priority(self.source)

    def format(self) -> str:
        """'label (uri) [source]' (uri omitted when empty)."""
        src = self.source or "Unknown"
        if self.uri:
            return f"{self.label} ({self.uri}) [{src}]"
        return f"{self.label} [{src}]"
