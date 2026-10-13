"""Request/response validation and JSON parsing."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional

from utils.exceptions import LLMResponseError, PayloadValidationError

from .types import CompletionRequest


def validate_request(request: CompletionRequest) -> None:
    if not request.model:
        raise PayloadValidationError("Request has no model")
    if not request.messages:
        raise PayloadValidationError("Request has no messages")
    for m in request.messages:
        if m.role not in ("system", "user", "assistant"):
            raise PayloadValidationError(f"Invalid message role: {m.role!r}")
        if not isinstance(m.content, str) or not m.content.strip():
            raise PayloadValidationError(f"Empty content for {m.role} message")
    if request.max_tokens <= 0:
        raise PayloadValidationError("max_tokens must be positive")
    if not 0 <= request.temperature <= 2:
        raise PayloadValidationError("temperature must be within [0, 2]")


def parse_json_response(raw: Optional[str]) -> Dict[str, Any]:
    """Parse a JSON object from LLM output with recovery strategies.

    Raises LLMResponseError on failure. `{}` is a valid parse.
    """
    if not raw or not raw.strip():
        raise LLMResponseError("Empty response")

    def _loads(s: str):
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None

    try:
        cleaned = re.sub(r'```json\s*|\s*```', '', raw)
        cleaned = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
        parsed = _loads(cleaned)
        if parsed is not None:
            return parsed
    except json.JSONDesrcError:
        pass

    try:
        m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
        if m:
            parsed = _loads(re.sub(r',(\s*[}\]])', r'\1', m.group(0)))
            if parsed is not None:
                return parsed
    except json.JSONDesrcError:
        pass

    try:
        fixed = re.sub(r'(\w+):', r'"\1":', raw)
        fixed = re.sub(r':\s*([^",\[\{][^,\]\}]*)', r': "\1"', fixed)
        fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
        m = re.search(r'\{.*\}', fixed, re.DOTALL)
        if m:
            parsed = _loads(m.group(0))
            if parsed is not None:
                return parsed
    except json.JSONDesrcError:
        pass

    raise LLMResponseError("All JSON parsing strategies failed")


def validate_response(raw_content: Optional[str], required_keys: Iterable[str] = (),
                      finish_reason: Optional[str] = None) -> Dict[str, Any]:
    """Parse content and check required keys; raises LLMResponseError."""
    if finish_reason == "length":
        raise LLMResponseError("Response truncated (finish_reason=length)")
    data = parse_json_response(raw_content)
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise LLMResponseError(f"Response missing required keys: {', '.join(missing)}")
    return data


def postprocess_api_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the dissertation-workflow response (moved from shared_utilities)."""

    def ensure_list(v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(',') if i.strip()]
        if isinstance(v, list):
            return v
        return []

    for key in ('namedEntities', 'geographicEntities'):
        if key in response_data:
            items = list(dict.fromkeys(ensure_list(response_data[key])))
            response_data[key] = [e for e in items if len(e) > 1 or not e.isalnum()]
        else:
            response_data.setdefault(key, [])

    if 'subjects' in response_data:
        response_data['subjects'] = ensure_list(response_data['subjects'])
    elif 'topics' in response_data:
        response_data['subjects'] = ensure_list(response_data.pop('topics'))
    elif 'subjectHeadings' in response_data:
        response_data['subjects'] = ensure_list(response_data.pop('subjectHeadings'))
    else:
        response_data.setdefault('subjects', [])

    if 'contentWarning' not in response_data:
        response_data['contentWarning'] = 'None'
    elif isinstance(response_data['contentWarning'], str):
        cw = response_data['contentWarning'].strip()
        if cw == '' or cw.lower() == 'none':
            response_data['contentWarning'] = 'None'
        else:
            cw = cw[0].upper() + cw[1:]
            response_data['contentWarning'] = cw.rstrip('.') + '.'
    else:
        response_data['contentWarning'] = 'None'

    for key in ("title", "creator", "date", "department", "abstract",
                "type", "access", "publisher", "sponsor", "language"):
        if isinstance(response_data.get(key), str):
            response_data[key] = response_data[key].strip()

    return response_data
