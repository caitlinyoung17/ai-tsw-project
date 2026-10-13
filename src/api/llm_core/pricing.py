"""Pricing model, provider-agnostic."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Optional

from utils.exceptions import UnknownModelError

from .types import Usage


@dataclass(frozen=True)
class ModelPrice:
    input_per_1k: float
    output_per_1k: float
    cached_per_1k: Optional[float] = None
    batch_discount: float = 0.5


class PricingProvider(ABC):
    """Maps model names to prices. `fallback_model` makes fallback explicit."""

    def __init__(self, fallback_model: Optional[str] = None) -> None:
        self.fallback_model = fallback_model

    @abstractmethod
    def price(self, model: str) -> ModelPrice:
        """Return the price or raise UnknownModelError."""

    def resolve(self, model: str) -> ModelPrice:
        try:
            return self.price(model)
        except UnknownModelError:
            if self.fallback_model is None:
                raise
            return self.price(self.fallback_model)

    def cost(self, usage: Usage, model: str, batch: bool = False) -> float:
        p = self.resolve(model)
        # cached tokens are a subset of prompt tokens, billed at the cached rate
        cached = min(usage.cached_tokens, usage.prompt_tokens)
        cached_rate = p.cached_per_1k if p.cached_per_1k is not None else p.input_per_1k
        total = (((usage.prompt_tokens - cached) / 1000) * p.input_per_1k
                 + (usage.completion_tokens / 1000) * p.output_per_1k
                 + (cached / 1000) * cached_rate)
        return total * p.batch_discount if batch else total


class TablePricing(PricingProvider):
    """Pricing backed by an injected mapping."""

    def __init__(self, table: Mapping[str, ModelPrice],
                 fallback_model: Optional[str] = None) -> None:
        super().__init__(fallback_model)
        self._table = dict(table)

    def price(self, model: str) -> ModelPrice:
        try:
            return self._table[model]
        except KeyError:
            raise UnknownModelError(f"No pricing for model '{model}'") from None
