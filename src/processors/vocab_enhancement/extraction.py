"""Pull subjects / geographic entities out of a workflow item."""
from __future__ import annotations

from typing import Any, Mapping

from utils import schema
from utils.subjects import parse_subject_list


def extract_subjects_and_geo(item: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    analysis = item.get("analysis") if isinstance(item, Mapping) else None
    if not isinstance(analysis, Mapping):
        return [], []
    return (parse_subject_list(analysis.get(schema.SUBJECTS)),
            parse_subject_list(analysis.get("geographic_entities")))
