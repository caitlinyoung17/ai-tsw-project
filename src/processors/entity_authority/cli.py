"""CLI: python -m processors.entity_authority.cli --folder PATH"""
from __future__ import annotations

import argparse
import logging

from utils.logging_setup import configure_logging
import sys

from processors.entity_authority.processor import EntityAuthorityProcessor
from utils.exceptions import TswError
from utils.run_folder import RunFolder


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build entity authority file")
    ap.add_argument("--folder", required=True, help="Run folder path")
    ap.add_argument("--threshold", type=float, default=85)
    ap.add_argument("--require-rapidfuzz", action="store_true")
    args = ap.parse_args(argv)
    configure_logging()
    try:
        EntityAuthorityProcessor(RunFolder(args.folder), threshold=args.threshold,
                                 require_rapidfuzz=args.require_rapidfuzz).run()
    except TswError as e:
        logging.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
