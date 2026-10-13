"""Library of Congress Subject Headings client (id.loc.gov suggest2)."""
from __future__ import annotations

from typing import Any

from metadata_standard import Term
from utils.exceptions import VocabParseError

from .base import Request, VocabularyClient

LCSH_URL = "https://id.loc.gov/authorities/subjects/suggest2"
LCSH_COLLECTION = ("http://id.loc.gov/authorities/subjects/"
                   "collection_LCSHAuthorizedHeadings")


class LcshClient(VocabularyClient):
    """Keyword search first; left-anchored search tops up when short."""
    name = group = "LCSH"

    def _req(self, query: str, search_type: str) -> Request:
        return LCSH_URL, {"q": query, "searchtype": search_type,
                          "count": self.max_results, "memberOf": LCSH_COLLECTION}

    def _build_request(self, query: str) -> Request:
        return self._req(query, "keyword")

    def _fallback_requests(self, query: str) -> list[Request]:
        return [self._req(query, "leftanchored")]

    def _needs_fallback(self, terms: list[Term]) -> bool:
        return len(self.dedupe(terms)) < self.max_results

    def _parse(self, payload: Any) -> list[Term]:
        if not isinstance(payload, dict):
            raise VocabParseError("LCSH payload is not an object")
        hits = payload.get("hits", [])
        if not isinstance(hits, list):
            raise VocabParseError("LCSH 'hits' is not a list")
        return [Term(label=h["aLabel"], uri=h["uri"], source="LCSH")
                for h in hits
                if isinstance(h, dict) and h.get("aLabel") and h.get("uri")]
