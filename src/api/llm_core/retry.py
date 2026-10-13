"""Retry policy: retries only LLMTransientError."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from utils.exceptions import LLMTransientError

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    sleep: Callable[[float], None] = time.sleep
    # Number of retries performed by the last call_with_retry (not usage).
    retries: int = field(default=0, init=False)

    def delay_for(self, attempt: int) -> float:
        return min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))


def call_with_retry(fn: Callable[[], T], policy: RetryPolicy) -> T:
    """Call fn, retrying LLMTransientError up to policy.max_attempts total attempts."""
    policy.retries = 0
    attempt = 1
    while True:
        try:
            return fn()
        except LLMTransientError:
            if attempt >= policy.max_attempts:
                raise
            policy.sleep(policy.delay_for(attempt))
            policy.retries += 1
            attempt += 1
