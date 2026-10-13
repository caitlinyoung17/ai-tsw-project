"""Collect raw typed entities from workflow items (pure)."""
from __future__ import annotations

from dataclasses import dataclass

from processors.entity_authority.entities import parse_typed_entity


@dataclass(frozen=True)
class RawEntity:
    original_str: str
    name: str
    type: str
    entry_index: int
    source: str
    context: str


def extract_all_entities(items: list[dict]) -> list[RawEntity]:
    """items are Workflow.items (api_stats trailer already removed)."""
    raw: list[RawEntity] = []
    for idx, item in enumerate(items):
        analysis = item.get("analysis") if isinstance(item, dict) else None
        if not analysis:
            continue
        source = item.get("filename") or item.get("file_path") or f"entry_{idx}"
        entities = analysis.get("namedEntities") or analysis.get("named_entities") or []
        if isinstance(entities, str):
            entities = [e.strip() for e in entities.split(",") if e.strip()]
        if not entities:
            continue
        title = (analysis.get("title") or "").strip()
        abstract = (analysis.get("abstract") or "").strip()
        context = " ".join(p for p in (title, abstract) if p).lower()
        for e in entities:
            if not e or len(e.strip()) < 2:
                continue
            name, etype = parse_typed_entity(e)
            if not name:
                continue
            raw.append(RawEntity(e.strip(), name, etype, idx, source, context))
    return raw
