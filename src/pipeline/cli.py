"""CLI: python -m pipeline"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from utils.exceptions import (ConfigError, StepFailedError, TswError,
                              WorkflowFilesNotFound)
from utils.logging_setup import configure_logging

from .context import build_default_context
from .pipeline import Pipeline
from .steps import default_steps

EXIT_OK, EXIT_CONFIG, EXIT_MISSING, EXIT_STEP = 0, 2, 3, 4
# step id -> description; derived from the steps so they remain the source of truth
STEP_IDS = {s.name: s.description for s in default_steps()}


def exit_src_for(exc: BaseException) -> int:
    """The single mapping from the TswError hierarchy to exit srcs."""
    if isinstance(exc, StepFailedError) and isinstance(exc.cause, TswError):
        return exit_src_for(exc.cause) if isinstance(
            exc.cause, (ConfigError, WorkflowFilesNotFound)) else EXIT_STEP
    if isinstance(exc, ConfigError):
        return EXIT_CONFIG
    if isinstance(exc, WorkflowFilesNotFound):
        return EXIT_MISSING
    return EXIT_STEP


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline", description="TSW pipeline runner")
    p.add_argument("--input", help="Folder of dissertation .txt files (step 1)")
    p.add_argument("--output-root", default="output_folders")
    p.add_argument("--folder", help="Existing run folder to resume")
    p.add_argument("--model", default=None)
    p.add_argument("--steps", default=None, help="Comma list of steps to run, e.g. 1,1.5,2,3,4. Steps: " + "; ".join(
        f"{k}={v}" for k, v in STEP_IDS.items()))
    p.add_argument("--batch", dest="batch", action="store_true", default=None)
    p.add_argument("--no-batch", dest="batch", action="store_false")
    p.add_argument("--full-text-scan", action="store_true")
    p.add_argument("--chunk-size", type=int, default=None)
    p.add_argument("--abstract-scan-max-chunks", type=int, default=None)
    p.add_argument("--max-chunks", type=int, default=None)
    p.add_argument("--keep-going", action="store_true")
    p.add_argument("--log-level", default="INFO", type=str.upper,
                   choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                   help="Logging verbosity (default INFO logs all progress; "
                        "ERROR suppresses everything but errors)")
    p.add_argument("--quiet", action="store_true",
                   help="Shortcut for --log-level ERROR")
    return p


def parse_steps(text: Optional[str]) -> Optional[List[str]]:
    if not text:
        return None
    ids = [t.strip() for t in text.split(",") if t.strip()]
    bad = [i for i in ids if i not in STEP_IDS]
    if bad:
        raise ConfigError(f"Unknown steps {bad}; choose from {list(STEP_IDS)}")
    return ids


def run_cli(args, context=None) -> int:
    """Shared by main() and tests (which pass a fake-wired context)."""
    try:
        only = parse_steps(args.steps)
        if only is None and args.folder and not args.input:
            only = list(STEP_IDS)[1:]   # resuming a folder: step 1 needs --input
        context = context or build_default_context(args)
        pipeline = Pipeline(default_steps())
        pipeline.validate_selection(only, resuming=context.run_folder is not None)
        report = pipeline.run(context, only=only)
    except TswError as e:
        logging.error("%s", e)
        return exit_src_for(e)
    logging.info("%s", report.render())
    return exit_src_for(report.failed.error) if report.failed else EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    level = "ERROR" if args.quiet else args.log_level
    configure_logging(getattr(logging, level, logging.INFO))
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
