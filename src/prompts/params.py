"""Single source of call parameters for batch and individual paths."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallParams:
    max_tokens: int
    temperature: float = 0.0


EXTRACTION = CallParams(max_tokens=8000, temperature=0.0)  # batch values chosen as source
CHUNK = CallParams(max_tokens=4000, temperature=0.0)
CLEANUP = CallParams(max_tokens=4000, temperature=0.1)
SELECTION = CallParams(max_tokens=1500, temperature=0.0)
