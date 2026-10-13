"""Abstract LLM provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from utils.exceptions import BatchError

from .pricing import PricingProvider
from .types import BatchHandle, BatchItem, BatchOutcome, CompletionRequest, CompletionResult


class LLMProvider(ABC):
    name: str = "llm"

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Run one completion; raises typed LLM errors."""

    @property
    def supports_batch(self) -> bool:
        return False

    def submit_batch(self, requests: List[BatchItem]) -> BatchHandle:
        raise BatchError(f"{self.name} does not support batch")

    def collect_batch(self, handle: BatchHandle, timeout: Optional[float] = None,
                      poll_interval: float = 60.0,
                      sleep: Optional[Callable[[float], None]] = None) -> Dict[str, BatchOutcome]:
        raise BatchError(f"{self.name} does not support batch")

    @property
    @abstractmethod
    def pricing(self) -> PricingProvider:
        """Pricing for this provider's models."""
