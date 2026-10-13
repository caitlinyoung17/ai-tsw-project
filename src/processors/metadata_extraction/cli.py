"""Command line entry point and composition root for step 1."""
from __future__ import annotations

import argparse
import logging

from utils.logging_setup import configure_logging
from pathlib import Path
from typing import List, Optional

from api.open_ai.config import OpenAIConfig
from api.open_ai.provider import PortkeyOpenAIProvider
from utils.run_folder import RunFolder

from .extractor import MetadataExtractor
from .processor import MetadataExtractionProcessor

src_DIR = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step 1: dissertation metadata extraction")
    p.add_argument("--input", default=str(src_DIR / "DigitizedDissertationTest"))
    p.add_argument("--output-root", default=str(src_DIR / "output_folders"))
    p.add_argument("--model", default=None)
    p.add_argument("--batch", dest="batch", action="store_true", default=None)
    p.add_argument("--no-batch", dest="batch", action="store_false")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    config = OpenAIConfig.from_env()
    provider = PortkeyOpenAIProvider(config)
    model = args.model or config.default_model
    run_folder = RunFolder.create(args.output_root)
    processor = MetadataExtractionProcessor(
        provider, MetadataExtractor(provider, model), use_batch=args.batch)
    summary = processor.run(args.input, run_folder)
    logging.info(f"STEP 1 COMPLETE: {summary.succeeded}/{summary.total} succeeded "
          f"({summary.mode}) in {run_folder.root.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
