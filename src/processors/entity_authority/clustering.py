"""Fuzzy clustering of entity names. rapidfuzz is imported lazily."""
from __future__ import annotations

import difflib
import logging
from collections import Counter
from typing import Optional, Protocol

from processors.entity_authority.entities import Entity, normalize_entity_name
from processors.entity_authority.extraction import RawEntity
from utils.exceptions import ConfigError

logger = logging.getLogger(__name__)


class Similarity(Protocol):
    def __call__(self, a: str, b: str) -> float:
        """Score 0-100 for two (already normalized) names."""


def _difflib_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio() * 100


def default_similarity(require_rapidfuzz: bool = False) -> tuple[Similarity, Optional[str]]:
    """Return (similarity, library_name). library_name is None for difflib."""
    try:
        from rapidfuzz import fuzz
        return fuzz.ratio, "rapidfuzz"
    except ImportError:
        if require_rapidfuzz:
            raise ConfigError("rapidfuzz is required but not installed")
        logger.warning("rapidfuzz not installed; falling back to difflib")
        return _difflib_similarity, None


def cluster_entities(raw: list[str], similarity: Similarity,
                     threshold: float = 85) -> list[Entity]:
    """Greedy clustering (same order semantics as legacy).

    Canonical = most frequent, then longest variant. count = mentions.
    """
    counts = Counter(raw)
    unique = list(counts)  # first-occurrence order
    norm = {n: normalize_entity_name(n) for n in unique}
    processed: set[str] = set()
    entities: list[Entity] = []
    for i, name in enumerate(unique):
        if name in processed:
            continue
        processed.add(name)
        group = [name]
        for other in unique[i + 1:]:
            if other in processed:
                continue
            if similarity(norm[name], norm[other]) >= threshold:
                group.append(other)
                processed.add(other)
        canonical = max(group, key=lambda x: (counts[x], len(x)))
        entities.append(Entity(name=canonical, variants=sorted(group),
                               count=sum(counts[g] for g in group)))
    return entities


def build_entities(raws: list[RawEntity], similarity: Similarity,
                   threshold: float = 85) -> list[Entity]:
    """Cluster raw entities and attach type/sources/forms/contexts."""
    clusters = cluster_entities([r.name for r in raws], similarity, threshold)
    by_variant = {v: e for e in clusters for v in e.variants}
    forms: dict[str, set[str]] = {e.name: set() for e in clusters}
    for r in raws:
        e = by_variant[r.name]
        e.sources.append(r.source)
        e.contexts.append(r.context)
        forms[e.name].add(r.original_str)
        if e.type == "unknown" or r.type != "unknown":
            e.type = r.type
    for e in clusters:
        e.original_forms = sorted(forms[e.name])
    return clusters
