"""OpenAI-via-Portkey configuration. Environment is read only in `from_env`."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from utils.exceptions import ConfigError


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    portkey_provider: str = "@glib-achoate-openai"
    default_model: str = "gpt-4o"
    batch_threshold: int = 5
    timeout: float = 120.0
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    batch_completion_window: str = "24h"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ConfigError("OpenAIConfig.api_key is required")
        if not self.default_model:
            raise ConfigError("OpenAIConfig.default_model is required")

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "OpenAIConfig":
        e = os.environ if env is None else env
        key = e.get("PORTKEY_API_KEY")
        if not key:
            raise ConfigError("Missing required environment variable PORTKEY_API_KEY")
        return cls(api_key=key, default_model=e.get("MODEL_NAME") or "gpt-4o")
