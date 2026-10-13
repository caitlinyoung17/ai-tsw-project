"""Analysis-record keys and the single blank-metadata factory.

The Step 1 prompt and LLM output use camelCase (``namedEntities``,
``geographicEntities``); later steps use snake_case. ``to_snake`` /
``to_camel`` are the one place this mapping lives.
"""
from __future__ import annotations

TITLE = "title"
CREATOR = "creator"
DATE = "date"
DEPARTMENT = "department"
ABSTRACT = "abstract"
SUBJECTS = "subjects"
TYPE = "type"
ACCESS = "access"
PUBLISHER = "publisher"
SPONSOR = "sponsor"
LANGUAGE = "language"
NAMED_ENTITIES = "namedEntities"
GEOGRAPHIC_ENTITIES = "geographicEntities"
CONTENT_WARNING = "contentWarning"

_CAMEL_TO_SNAKE = {
    NAMED_ENTITIES: "named_entities",
    GEOGRAPHIC_ENTITIES: "geographic_entities",
    CONTENT_WARNING: "content_warning",
}
_SNAKE_TO_CAMEL = {v: k for k, v in _CAMEL_TO_SNAKE.items()}


def empty_metadata() -> dict:
    """Fresh blank record (new lists each call)."""
    return {
        TITLE: "", CREATOR: "", DATE: "", DEPARTMENT: "", ABSTRACT: "",
        SUBJECTS: [], TYPE: "", ACCESS: "", PUBLISHER: "", SPONSOR: "",
        LANGUAGE: "", NAMED_ENTITIES: [], GEOGRAPHIC_ENTITIES: [],
        CONTENT_WARNING: "None",
    }


def to_snake(analysis: dict) -> dict:
    return {_CAMEL_TO_SNAKE.get(k, k): v for k, v in analysis.items()}


def to_camel(analysis: dict) -> dict:
    return {_SNAKE_TO_CAMEL.get(k, k): v for k, v in analysis.items()}
