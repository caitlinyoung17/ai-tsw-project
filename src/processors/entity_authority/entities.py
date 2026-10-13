"""Entity model and pure parsing/classification helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Entity:
    name: str
    type: str = "unknown"
    variants: list[str] = field(default_factory=list)
    count: int = 0
    sources: list[str] = field(default_factory=list)
    original_forms: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)


def normalize_entity_name(name: str) -> str:
    """Whitespace collapse plus '&'/'Co.'/'Inc.' expansion (legacy behavior)."""
    normalized = re.sub(r"\s+", " ", name.strip())
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"\bCo\.\b", "Company", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bInc\.\b", "Incorporated", normalized, flags=re.IGNORECASE)
    return normalized


def classify_entity_fallback(entity: str) -> str:
    """Heuristic type for entities lacking an explicit '(type)' suffix."""
    low = entity.lower()
    if any(t in low for t in ["university", "college", "institute", "school", "department"]):
        return "institution"
    if any(t in low for t in ["company", "co.", "inc.", "corp.", "corporation",
                              "association", "society", "foundation", "committee"]):
        return "organization"
    if any(t in low for t in ["study", "project", "program", "trial", "survey"]):
        return "project"
    if re.match(r"^[A-Z]\. ?[A-Z]\.? [A-Z]", entity):
        return "person"
    if re.match(r"^[A-Z][a-z]+ [A-Z]\. [A-Z]", entity):
        return "person"
    words = entity.split()
    if len(words) >= 2 and all(w and w[0].isupper() for w in words[:2]):
        return "person"
    if any(t in low for t in ["city", "state", "province", "county", "region", "country"]):
        return "location"
    return "unknown"


def parse_typed_entity(entity_str: str) -> tuple[str, str]:
    """'John F. Staub (architect)' -> ('John F. Staub', 'architect')."""
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", entity_str.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    name = entity_str.strip()
    return name, classify_entity_fallback(name)
