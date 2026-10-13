"""Subject list parsing."""
from __future__ import annotations

import re
from typing import Optional, Union


def parse_subject_list(value: Union[str, list, None]) -> list[str]:
    """Accept a list, a comma/semicolon string, or empty. Empty -> []."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;]", value)
    elif isinstance(value, (list, tuple)):
        parts = value
    else:
        return []
    return [str(p).strip() for p in parts if p is not None and str(p).strip()]
