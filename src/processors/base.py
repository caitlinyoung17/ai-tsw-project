"""Common interface for pipeline processor steps."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProcessorStep(ABC):
    """A pipeline step. Subclasses set `name` and implement `run`.

    Dependencies (provider, store, sleep, clock) are constructor arguments;
    `run` takes only the per-invocation inputs (folders) and returns a typed
    result. Failures are raised as `utils.exceptions.TswError` subclasses.
    """

    name: str = "step"

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the step."""
