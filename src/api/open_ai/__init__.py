"""OpenAI (via Portkey) provider."""
from typing import Any, Callable, Optional

from .batch import OpenAIBatchClient
from .config import OpenAIConfig
from .pricing import OPENAI_PRICES, OpenAIPricing
from .provider import PortkeyOpenAIProvider


def build_openai_provider(config: OpenAIConfig,
                          client_factory: Optional[Callable[[OpenAIConfig], Any]] = None
                          ) -> PortkeyOpenAIProvider:
    """Composition-root helper."""
    return PortkeyOpenAIProvider(config, client_factory=client_factory)


__all__ = ["OpenAIBatchClient", "OpenAIConfig", "OpenAIPricing", "OPENAI_PRICES",
           "PortkeyOpenAIProvider", "build_openai_provider"]
