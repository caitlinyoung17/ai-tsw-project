"""OpenAI price table (moved from model_pricing.py; July 2025 rates)."""
from __future__ import annotations

from typing import Optional

from api.llm_core import ModelPrice, TablePricing

_P = ModelPrice
OPENAI_PRICES = {
    "gpt-4o": _P(0.0025, 0.01, cached_per_1k=0.00125),
    "gpt-4o-2024-08-06": _P(0.0025, 0.01, cached_per_1k=0.00125),
    "gpt-4o-mini": _P(0.00015, 0.0006, cached_per_1k=0.000075),
    "gpt-4o-mini-2024-07-18": _P(0.00015, 0.0006, cached_per_1k=0.000075),
    "gpt-4.1": _P(0.002, 0.008, cached_per_1k=0.0005),
    "gpt-4.1-2025-04-14": _P(0.002, 0.008, cached_per_1k=0.0005),
    "gpt-4.1-mini": _P(0.0004, 0.0016, cached_per_1k=0.0001),
    "gpt-4.1-mini-2025-04-14": _P(0.0004, 0.0016, cached_per_1k=0.0001),
}


class OpenAIPricing(TablePricing):
    def __init__(self, fallback_model: Optional[str] = None) -> None:
        super().__init__(OPENAI_PRICES, fallback_model)
