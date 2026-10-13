"""FAST (OCLC) subject and geographic clients."""
from __future__ import annotations

from typing import Any

from metadata_standard import Term
from utils.exceptions import VocabParseError

from .base import Request, VocabularyClient
from .relevance import word_overlap

FAST_SUGGEST_URL = "https://fast.oclc.org/searchfast/fastsuggest"
FAST_URI = "http://id.worldcat.org/fast/{}"


def _first(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return value if isinstance(value, str) else (str(value) if value else "")


def parse_fast_docs(payload: Any, source: str, with_tag: bool) -> list[Term]:
    if not isinstance(payload, dict):
        raise VocabParseError("FAST payload is not an object")
    response = payload.get("response")
    if response is None:
        return []
    if not isinstance(response, dict) or not isinstance(response.get("docs", []), list):
        raise VocabParseError("FAST payload has malformed 'response'")
    terms = []
    for doc in response.get("docs", []):
        if not isinstance(doc, dict):
            raise VocabParseError("FAST doc is not an object")
        suggest_all, id_root = _first(doc.get("suggestall")), _first(doc.get("idroot"))
        if not (suggest_all and id_root):
            continue
        tag = doc.get("tag", "") if with_tag else ""
        if isinstance(tag, list):
            tag = ", ".join(str(t) for t in tag if t)
        terms.append(Term(label=_first(doc.get("auth")) or suggest_all,
                          uri=FAST_URI.format(id_root), source=source,
                          type=_first(doc.get("type")), subject_id=id_root,
                          tag=str(tag or "")))
    return terms


class FastClient(VocabularyClient):
    name = group = "FAST"

    def _params(self, query: str) -> dict:
        return {"query": query, "queryReturn": "suggestall,idroot,auth,type",
                "suggest": "autoSubject", "rows": self.max_results * 2,
                "sort": "usage desc"}

    def _build_request(self, query: str) -> Request:
        return FAST_SUGGEST_URL, self._params(query)

    def _parse(self, payload: Any) -> list[Term]:
        return parse_fast_docs(payload, "FAST", with_tag=False)

    def _fallback_requests(self, query: str) -> list[Request]:
        if " " not in query:
            return []
        return [(FAST_SUGGEST_URL, self._params(w))
                for w in query.split() if len(w) > 3]

    def _accept_fallback(self, term: Term, query: str) -> bool:
        return word_overlap(term.label, query)


class FastGeographicClient(VocabularyClient):
    name = group = "FAST Geographic"

    def __init__(self, http, **kw) -> None:
        kw.setdefault("max_results", 1)
        super().__init__(http, **kw)

    def _params(self, query: str) -> dict:
        return {"query": query, "queryReturn": "suggestall,idroot,auth,type,tag",
                "suggest": "autoSubject", "rows": self.max_results * 2,
                "sort": "usage desc", "facet": "type", "facet.field": "type"}

    def _build_request(self, query: str) -> Request:
        return FAST_SUGGEST_URL, {**self._params(query), "fq": "type:Geographic"}

    def _parse(self, payload: Any) -> list[Term]:
        return parse_fast_docs(payload, "FAST Geographic", with_tag=True)

    def _fallback_requests(self, query: str) -> list[Request]:
        return [(FAST_SUGGEST_URL, self._params(query))]  # no geographic filter

    def _accept_fallback(self, term: Term, query: str) -> bool:
        return word_overlap(term.label, query) or "geographic" in term.type.lower()
