"""Chunking configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils.exceptions import ConfigError


@dataclass(frozen=True)
class ChunkingConfig:
    enabled: bool = True
    # ~100k tokens at ~4 chars/token: fits a 128k-context model with room for
    # the prompt and an 8k-token response.
    max_whole_document_chars: int = 400_000
    # Only used when a token_counter is supplied to needs_chunking().
    max_whole_document_tokens: int = 100_000
    front_matter_chars: int = 8000
    chunk_size: int = 40000
    overlap: int = 500
    full_text_scan: bool = False
    abstract_scan_max_chunks: int = 3  # 0 disables abstract continuation
    max_chunks: Optional[int] = None  # cap for full_text_scan; None = no cap

    def __post_init__(self) -> None:
        for name in ("max_whole_document_chars", "max_whole_document_tokens",
                     "front_matter_chars", "chunk_size"):
            if getattr(self, name) <= 0:
                raise ConfigError(f"{name} must be positive")
        if self.overlap < 0 or self.overlap >= self.chunk_size:
            raise ConfigError("overlap must be >= 0 and < chunk_size")
        if self.abstract_scan_max_chunks < 0:
            raise ConfigError("abstract_scan_max_chunks must be >= 0")
        if self.max_chunks is not None and self.max_chunks < 0:
            raise ConfigError("max_chunks must be >= 0 or None")
