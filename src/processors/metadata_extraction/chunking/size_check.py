"""Substep 1: decide whether a document needs chunking."""
from __future__ import annotations

from typing import Callable, Optional

from .config import ChunkingConfig


def needs_chunking(text: str, config: ChunkingConfig,
                   token_counter: Optional[Callable[[str], int]] = None) -> bool:
    if not config.enabled:
        return False
    if token_counter is not None:
        return token_counter(text) > config.max_whole_document_tokens
    return len(text) > config.max_whole_document_chars
