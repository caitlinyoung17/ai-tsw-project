"""Test doubles for the LLM layer."""
from __future__ import annotations

from typing import List, Union

from utils.exceptions import LLMResponseError

from .pricing import PricingProvider, TablePricing, ModelPrice
from .provider import LLMProvider
from .types import CompletionRequest, CompletionResult, Usage


class FakeProvider(LLMProvider):
    """Returns scripted responses (str) or raises scripted exceptions, in order."""
    name = "fake"

    def __init__(self, responses: List[Union[str, BaseException]],
                 usage: Usage = Usage(10, 5), pricing: PricingProvider = None) -> None:
        self._responses = list(responses)
        self._usage = usage
        self._pricing = pricing or TablePricing({"fake-model": ModelPrice(1.0, 2.0)})
        self.requests: List[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if not self._responses:
            raise LLMResponseError("FakeProvider has no more scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return CompletionResult(content=item, usage=self._usage,
                                model=request.model, finish_reason="stop")

    @property
    def pricing(self) -> PricingProvider:
        return self._pricing
