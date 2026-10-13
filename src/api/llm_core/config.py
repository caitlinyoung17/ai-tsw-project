"""LLM configuration. Environment is read only in `from_env`."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from utils.exceptions import ConfigError


@dataclass(frozen=True)
class LLMConfig:
    model: str
    max_tokens: int = 3000
    temperature: float = 0.0
    timeout: float = 120.0
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.model:
            raise ConfigError("LLMConfig.model is required")
        if self.max_tokens <= 0:
            raise ConfigError("max_tokens must be positive")
        if self.max_attempts < 1:
            raise ConfigError("max_attempts must be >= 1")

    @classmethod
    def from_env(cls, prefix: str = "LLM_", env: Optional[Mapping[str, str]] = None,
                 require_api_key: bool = False) -> "LLMConfig":
        """Build from `<prefix>MODEL`, `<prefix>API_KEY`, etc. Called by the composition root."""
        e = os.environ if env is None else env
        model = e.get(prefix + "MODEL")
        if not model:
            raise ConfigError(f"Missing required environment variable {prefix}MODEL")
        api_key = e.get(prefix + "API_KEY")
        if require_api_key and not api_key:
            raise ConfigError(f"Missing required environment variable {prefix}API_KEY")

        def num(key, default, conv):
            raw = e.get(prefix + key)
            if raw in (None, ""):
                return default
            try:
                return conv(raw)
            except ValueError:
                raise ConfigError(f"Invalid value for {prefix}{key}: {raw!r}") from None

        d = cls.__dataclass_fields__
        return cls(
            model=model,
            max_tokens=num("MAX_TOKENS", d["max_tokens"].default, int),
            temperature=num("TEMPERATURE", d["temperature"].default, float),
            timeout=num("TIMEOUT", d["timeout"].default, float),
            max_attempts=num("MAX_ATTEMPTS", d["max_attempts"].default, int),
            base_delay=num("BASE_DELAY", d["base_delay"].default, float),
            max_delay=num("MAX_DELAY", d["max_delay"].default, float),
            api_key=api_key,
        )
