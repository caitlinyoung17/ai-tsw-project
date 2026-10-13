"""Prompt templating (concrete templates live in the prompts package, changeset 04)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from string import Template
from typing import List

from utils.exceptions import PayloadValidationError

from .types import Message


def _missing(template: str, vars: dict) -> List[str]:
    names = {m.group('named') or m.group('braced')
             for m in Template.pattern.finditer(template)
             if m.group('named') or m.group('braced')}
    return sorted(n for n in names if n not in vars)


@dataclass(frozen=True)
class PromptTemplate:
    """`$name` / `${name}` placeholders; use `$$` for a literal dollar."""
    system: str
    user: str

    def render(self, **vars) -> List[Message]:
        missing = sorted(set(_missing(self.system, vars)) | set(_missing(self.user, vars)))
        if missing:
            raise PayloadValidationError(f"Missing prompt variables: {', '.join(missing)}")
        return [Message("system", Template(self.system).substitute(vars)),
                Message("user", Template(self.user).substitute(vars))]


def truncate_for_prompt(text: str, max_chars: int, marker: str = "\n[...truncated...]") -> str:
    """Truncate text to at most max_chars (marker included)."""
    if max_chars < 0:
        raise PayloadValidationError("max_chars must be >= 0")
    if len(text) <= max_chars:
        return text
    if max_chars <= len(marker):
        return text[:max_chars]
    return text[:max_chars - len(marker)] + marker
