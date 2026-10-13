"""Getty AAT / TGN clients (XML); one shared parser."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from metadata_standard import Term
from utils.exceptions import VocabParseError

from .base import Request, VocabularyClient
from .relevance import word_overlap

AAT_URL = "http://vocabsservices.getty.edu/AATService.asmx/AATGetTermMatch"
TGN_URL = "http://vocabsservices.getty.edu/TGNService.asmx/TGNGetTermMatch"
_ARCH_WORDS = ("architecture", "architectural", "building", "style")
_GEO_WORDS = ("american", "southern", "northern", "eastern", "western",
              "city", "state", "county")


def _parse_getty_xml(text: str, source: str, uri_base: str) -> list[Term]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise VocabParseError(f"Malformed Getty XML: {e}", cause=e)
    terms = []
    for el in root.findall(".//Subject"):
        sid, pref = el.find("Subject_ID"), el.find("Preferred_Term")
        sid_text = (sid.text or "").strip() if sid is not None else ""
        label = (pref.text or "").strip() if pref is not None else ""
        if not (sid_text and label):  # None-safe: skip incomplete records
            continue
        terms.append(Term(label=label, uri=f"{uri_base}{sid_text}",
                          source=source, subject_id=sid_text))
    return terms


class GettyAATClient(VocabularyClient):
    name, group, response_format = "Getty AAT", "Getty", "text"

    def _build_request(self, query: str) -> Request:
        return AAT_URL, {"term": query, "logop": "and", "notes": ""}

    def _parse(self, payload: Any) -> list[Term]:
        return _parse_getty_xml(payload, "Getty AAT", "http://vocab.getty.edu/aat/")

    def _fallback_requests(self, query: str) -> list[Request]:
        if " " not in query:
            return []
        return [(AAT_URL, {"term": w, "logop": "and", "notes": ""})
                for w in query.split() if len(w) > 3]

    def _accept_fallback(self, term: Term, query: str) -> bool:
        return word_overlap(term.label, query) or any(
            w in term.label.lower() for w in _ARCH_WORDS)


class GettyTGNClient(VocabularyClient):
    name, group, response_format = "Getty TGN", "Getty", "text"

    def _build_request(self, query: str) -> Request:
        return TGN_URL, {"name": query, "placetypeid": "", "nationid": ""}

    def _parse(self, payload: Any) -> list[Term]:
        return _parse_getty_xml(payload, "Getty TGN", "http://vocab.getty.edu/tgn/")

    def _fallback_requests(self, query: str) -> list[Request]:
        return [(TGN_URL, {"name": w, "placetypeid": "", "nationid": ""})
                for w in query.lower().split() if w in _GEO_WORDS or len(w) > 4]
