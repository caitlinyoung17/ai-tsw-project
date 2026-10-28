"""Command line entry point and composition root for step 1.5."""
from __future__ import annotations

import argparse
import logging

from utils.logging_setup import configure_logging
from typing import List, Optional

from api.open_ai.config import OpenAIConfig
from api.open_ai.provider import PortkeyOpenAIProvider
from processors.metadata_extraction.extractor import MetadataExtractor
from utils.run_folder import RunFolder

from .processor import BatchCleanupProcessor
from .reprocessor import ItemReprocessor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step 1.5: batch cleanup")
    p.add_argument("--folder", required=True, help="Run folder from step 1")
    p.add_argument("--model", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(run_parameters={"command": "batch_cleanup", **vars(args)})
    config = OpenAIConfig.from_env()
    provider = PortkeyOpenAIProvider(config)
    extractor = MetadataExtractor(provider, args.model or config.default_model)
    summary = BatchCleanupProcessor(ItemReprocessor(extractor)).run(RunFolder(args.folder))
    logging.info(f"STEP 1.5 {summary.status.name}: fixed={summary.n_fixed} "
          f"still_failed={summary.n_still_failed}")
    return 1 if summary.n_still_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
