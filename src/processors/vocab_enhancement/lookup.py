"""Orchestrates client lookups into a MetadataStandard."""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from api.vocab.base import VocabularyClient
from metadata_standard import MetadataStandard
from utils.exceptions import VocabularyError


class LookupResult(MetadataStandard):
    """MetadataStandard plus the per-subject errors hit during lookup."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.errors: list[str] = []


def _search_term(entity: str) -> str:
    """'Baltimore--Maryland (City)' -> 'Baltimore--Maryland'."""
    if "(" in entity and entity.endswith(")"):
        i = entity.rfind("(")
        if i > 0:
            return entity[:i].strip()
    return entity


class VocabLookupService:
    def __init__(self, subject_clients: Sequence[VocabularyClient],
                 geo_clients: Sequence[VocabularyClient],
                 per_vocab_limit: int = 3, geo_limit: int = 1,
                 logger: Optional[logging.Logger] = None) -> None:
        self.subject_clients = list(subject_clients)
        self.geo_clients = list(geo_clients)
        self.per_vocab_limit = per_vocab_limit
        self.geo_limit = geo_limit
        self.logger = logger or logging.getLogger(__name__)

    def _gather(self, clients, query, label, limit, errors) -> list:
        """Clients in order; ``limit`` caps each client ``group``."""
        by_group: dict[str, int] = {}
        out = []
        for c in clients:
            room = limit - by_group.get(c.group, 0)
            if room <= 0:
                continue
            try:
                terms = c.search(query, label)[:room]
            except VocabularyError as e:  # one failure must not stop the run
                errors.append(f"{label} [{c.name}]: {e}")
                self.logger.warning("Lookup failed for %r in %s: %s", label, c.name, e)
                continue
            by_group[c.group] = by_group.get(c.group, 0) + len(terms)
            out.extend(terms)
        return out

    def lookup(self, subjects: Sequence[str],
               geographic_entities: Sequence[str]) -> LookupResult:
        result = LookupResult()
        for subject in subjects:
            subject = (subject or "").strip()
            if not subject or subject in result.subject_to_terms:
                continue
            terms = self._gather(self.subject_clients, subject, subject,
                                 self.per_vocab_limit, result.errors)
            result.add_terms(subject, MetadataStandard.dedupe(terms))
        for entity in geographic_entities:
            entity = (entity or "").strip()
            if not entity or entity in result.geographic_to_terms:
                continue
            terms = self._gather(self.geo_clients, _search_term(entity), entity,
                                 self.geo_limit, result.errors)
            result.add_terms(entity, terms, geographic=True)
        return result
