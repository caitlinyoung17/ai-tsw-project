"""Portkey-transport OpenAI implementation of LLMProvider."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from api.llm_core import (BatchHandle, BatchItem, BatchOutcome, CompletionRequest,
                      CompletionResult, LLMProvider, PricingProvider,
                      RetryPolicy, Usage, call_with_retry)
from utils.exceptions import LLMError, LLMResponseError, LLMTransientError

from .batch import OpenAIBatchClient
from .config import OpenAIConfig
from .pricing import OpenAIPricing

log = logging.getLogger(__name__)


def _default_client_factory(config: OpenAIConfig):
    from portkey_ai import Portkey  # lazy: no import-time client
    return Portkey(api_key=config.api_key, provider=config.portkey_provider)


def map_exception(exc: BaseException) -> LLMError:
    """Classify an SDK exception without importing the SDK."""
    if isinstance(exc, LLMError):
        return exc
    status = getattr(exc, "status_src", None)
    name = type(exc).__name__
    if (status == 429 or (isinstance(status, int) and status >= 500)
            or isinstance(exc, TimeoutError)
            or "RateLimit" in name or "Timeout" in name
            or "ConnectionError" in name or "InternalServer" in name):
        return LLMTransientError(f"{name}: {exc}", cause=exc)
    return LLMError(f"{name}: {exc}", cause=exc)


def parse_usage(usage: Any) -> Usage:
    """Build Usage from an SDK object or dict; missing usage yields zeros."""
    if usage is None:
        return Usage()

    def get(obj, key):
        if obj is None:
            return None
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

    details = get(usage, "prompt_tokens_details")
    return Usage(int(get(usage, "prompt_tokens") or 0),
                 int(get(usage, "completion_tokens") or 0),
                 int(get(details, "cached_tokens") or 0))


class PortkeyOpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, config: OpenAIConfig,
                 client_factory: Optional[Callable[[OpenAIConfig], Any]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 pricing: Optional[PricingProvider] = None) -> None:
        self.config = config
        self._factory = client_factory or _default_client_factory
        self._client = None
        self._sleep = sleep
        self._pricing = pricing or OpenAIPricing()
        self._batch: Optional[OpenAIBatchClient] = None
        self.retry_policy = RetryPolicy(config.max_attempts, config.base_delay,
                                        config.max_delay, sleep)

    @property
    def client(self):
        if self._client is None:
            self._client = self._factory(self.config)
        return self._client

    @property
    def pricing(self) -> PricingProvider:
        return self._pricing

    def _body(self, request: CompletionRequest) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": request.model or self.config.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format:
            body["response_format"] = dict(request.response_format)
        return body

    def complete(self, request: CompletionRequest) -> CompletionResult:
        body = self._body(request)

        def attempt() -> CompletionResult:
            try:
                resp = self.client.chat.completions.create(**body)
            except Exception as exc:  # classify SDK errors
                raise map_exception(exc) from exc
            choices = getattr(resp, "choices", None)
            if not choices:
                raise LLMResponseError("OpenAI response had no choices")
            choice = choices[0]
            content = getattr(getattr(choice, "message", None), "content", None)
            return CompletionResult(
                content=content or "",
                usage=parse_usage(getattr(resp, "usage", None)),
                model=getattr(resp, "model", None) or body["model"],
                finish_reason=getattr(choice, "finish_reason", None),
                raw=resp)

        return call_with_retry(attempt, self.retry_policy)

    # batch -----------------------------------------------------------
    @property
    def batch_client(self) -> OpenAIBatchClient:
        if self._batch is None:
            self._batch = OpenAIBatchClient(lambda: self.client, self.config,
                                            sleep=self._sleep)
        return self._batch

    @property
    def supports_batch(self) -> bool:
        return True

    def submit_batch(self, requests: List[BatchItem]) -> BatchHandle:
        return self.batch_client.submit_batch(requests)

    def collect_batch(self, handle: BatchHandle, timeout: Optional[float] = None,
                      poll_interval: float = 60.0,
                      sleep: Optional[Callable[[float], None]] = None) -> Dict[str, BatchOutcome]:
        return self.batch_client.collect_batch(handle, timeout, poll_interval, sleep)

    def should_use_batch(self, n: int) -> bool:
        return n > self.config.batch_threshold
