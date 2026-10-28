"""Pipeline wiring. The composition root helper is the only env reader."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from processors.metadata_extraction.chunking import ChunkingConfig
from utils.run_folder import DEFAULT_OUTPUT_ROOT, RunFolder


@dataclass
class PipelineConfig:
    input_folder: Optional[Path] = None
    output_root: Path = DEFAULT_OUTPUT_ROOT
    model: Optional[str] = None
    use_batch: Optional[bool] = None
    chunking: Optional[ChunkingConfig] = None   # None = no chunking
    keep_going: bool = False
    threshold: float = 85


@dataclass
class PipelineContext:
    run_folder: Optional[RunFolder]
    provider: Any
    standard_factory: Callable[[RunFolder], Any]   # run folder -> VocabLookupService
    config: PipelineConfig
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("pipeline"))
    clock: Callable[[], datetime] = datetime.now
    sleep: Callable[[float], None] = time.sleep


def default_standard_factory(run_folder: RunFolder):
    from processors.vocab_enhancement.cli import build_processor
    return build_processor(run_folder).lookup


def build_default_context(args) -> PipelineContext:
    """Real wiring: reads env via OpenAIConfig.from_env()."""
    from api.open_ai import OpenAIConfig, build_openai_provider
    openai_cfg = OpenAIConfig.from_env()
    chunking = None
    if args.full_text_scan or args.chunk_size or args.abstract_scan_max_chunks is not None \
            or args.max_chunks is not None:
        kw = {"full_text_scan": args.full_text_scan}
        if args.chunk_size:
            kw["chunk_size"] = args.chunk_size
        if args.abstract_scan_max_chunks is not None:
            kw["abstract_scan_max_chunks"] = args.abstract_scan_max_chunks
        if args.max_chunks is not None:
            kw["max_chunks"] = args.max_chunks
        chunking = ChunkingConfig(**kw)
    cfg = PipelineConfig(
        input_folder=Path(args.input) if args.input else None,
        output_root=Path(args.output_root), model=args.model or openai_cfg.default_model,
        use_batch=args.batch, chunking=chunking, keep_going=args.keep_going)
    rf = RunFolder(args.folder) if args.folder else None
    return PipelineContext(rf, build_openai_provider(openai_cfg),
                           default_standard_factory, cfg)
