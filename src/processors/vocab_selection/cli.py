"""CLI: python -m processors.vocab_selection.cli --folder PATH [--model M]"""
from __future__ import annotations

import argparse
import logging

from utils.logging_setup import configure_logging
import sys

from utils.exceptions import TswError
from utils.run_folder import RunFolder


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Step 3: vocabulary term selection")
    ap.add_argument("--folder", required=True, help="Run folder path")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)
    configure_logging()
    try:
        from api.open_ai import OpenAIConfig, build_openai_provider
        from processors.vocab_selection.processor import VocabSelectionProcessor
        config = OpenAIConfig.from_env()
        provider = build_openai_provider(config)
        summary = VocabSelectionProcessor(
            RunFolder(args.folder), provider, args.model or config.default_model).run()
    except TswError as e:
        logging.error("%s", e)
        return 1
    logging.info("Selection summary: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
