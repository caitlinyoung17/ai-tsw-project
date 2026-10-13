"""Metadata extraction prompt templates (full document, front matter, chunks)."""
from __future__ import annotations

from typing import Sequence

from api.llm_core.prompts import PromptTemplate

from .fields import (ALL_FIELDS, CONTENT_WARNING_INSTRUCTIONS,
                     DISSERTATION_DESCRIPTION, FRONT_MATTER_FIELDS,
                     FULL_TEXT_FIELDS, FieldSpec)


def _field_json(f: FieldSpec) -> str:
    if f.rules:
        items = "\n".join(f"        - {r}" for r in f.rules)
        return f'    "{f.name}": "{f.description}. Include:\\n{items}"'
    return f'    "{f.name}": "{f.description}"'


def json_format(fields: Sequence[FieldSpec]) -> str:
    return "{\n" + ",\n    \n".join(_field_json(f) for f in fields) + "\n}"


def _esc(text: str) -> str:
    return text.replace("$", "$$")


_FULL_TEXT_USER = "Here is the full dissertation text:\n\n$text"


def metadata_extraction_template(fields: Sequence[FieldSpec] = ALL_FIELDS) -> PromptTemplate:
    """Full-document prompt. Render with text=<stripped dissertation text>."""
    system = _esc(f"""{DISSERTATION_DESCRIPTION}

You will be given the full OCR'd text of a single dissertation. Using that full text, extract and construct the following metadata fields.

Return ONLY a JSON response in this exact format:

{json_format(fields)}

Focus on capturing accurate bibliographic information (title, creator, date, department, etc.) and the core intellectual content of the dissertation (abstract, subjects, named entities, and geographic entities).

{CONTENT_WARNING_INSTRUCTIONS}

Return ONLY the JSON response in the exact format specified above.""")
    return PromptTemplate(system, _FULL_TEXT_USER)


def front_matter_template() -> PromptTemplate:
    """Front matter only (title page, abstract, etc.). Render with text=."""
    system = _esc(f"""{DISSERTATION_DESCRIPTION}

You will be given the opening pages (front matter) of a single dissertation. Extract the following metadata fields from that text.

Return ONLY a JSON response in this exact format:

{json_format(FRONT_MATTER_FIELDS)}

Return ONLY the JSON response in the exact format specified above.""")
    return PromptTemplate(system, "Here is the front matter of the dissertation:\n\n$text")


def chunk_entities_template() -> PromptTemplate:
    """Partial-excerpt prompt asking only the full-text fields. Render with text=."""
    system = _esc(f"""{DISSERTATION_DESCRIPTION}

You will be given a partial excerpt from the body of a single dissertation, not the whole work. Do not guess or infer any field you cannot see in this excerpt, such as title, author, or date; report only what this excerpt supports.

Return ONLY a JSON response in this exact format:

{json_format(FULL_TEXT_FIELDS)}

{CONTENT_WARNING_INSTRUCTIONS}

Return ONLY the JSON response in the exact format specified above.""")
    return PromptTemplate(system, "Here is a partial excerpt of the dissertation:\n\n$text")


def abstract_completion_template() -> PromptTemplate:
    """Ask whether the abstract has ended in the text so far. Render with text=."""
    system = ("You are an archivist reading the beginning of a dissertation. "
              "Given the text so far, determine whether the formal abstract has ended "
              "within this text.\n\n"
              "Return ONLY a JSON response in this exact format:\n\n"
              '{\n    "abstract_found": true or false,\n'
              '    "abstract_complete": true if the abstract ends within the text, '
              "false if the text stops before the abstract ends,\n"
              '    "abstract": "the abstract text found so far, word-for-word, or an empty string (\'\')"\n}')
    return PromptTemplate(system, "Here is the text so far:\n\n$text")
