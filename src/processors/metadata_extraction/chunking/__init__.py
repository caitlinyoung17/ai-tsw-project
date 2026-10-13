"""Long-document handling for step 1."""
from .chunk_processor import (AbstractResult, ChunkProcessor, ChunkResult,
                              FrontMatterResult)
from .config import ChunkingConfig
from .paginated_merger import (MergedMetadata, PaginatedProcessor, Split, merge,
                               split_document)
from .size_check import needs_chunking


from typing import Callable, Optional


class ChunkingStrategyImpl:
    """Adapter satisfying MetadataExtractor's ChunkingStrategy hook."""

    def __init__(self, provider, model: str, config: Optional[ChunkingConfig] = None,
                 token_counter: Optional[Callable[[str], int]] = None,
                 templates: Optional[dict] = None) -> None:
        self.config = config or ChunkingConfig()
        self.token_counter = token_counter
        self.processor = PaginatedProcessor(
            ChunkProcessor(provider, model, templates), self.config)

    def needs_chunking(self, text: str) -> bool:
        return needs_chunking(text, self.config, self.token_counter)

    def run(self, text: str, doc_id: str = "") -> MergedMetadata:
        return self.processor.run(text, doc_id)
