"""CLI: python -m processors.vocab_enhancement.cli --folder PATH"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from api.vocab import (FastClient, FastGeographicClient, GettyAATClient,
                       GettyTGNClient, HttpClient, LcshClient, QueryCache,
                       ResponseLog, VocabStatsTracker)
from processors.vocab_enhancement.lookup import VocabLookupService
from processors.vocab_enhancement.processor import VocabEnhancementProcessor
from utils.exceptions import TswError
from utils.logging_setup import configure_logging
from utils.run_folder import DEFAULT_OUTPUT_ROOT, RunFolder


def build_processor(run_folder: RunFolder) -> VocabEnhancementProcessor:
    """Composition root: wires real HTTP clients."""
    run_folder.ensure_dirs()
    http, cache, stats = HttpClient(), QueryCache(), VocabStatsTracker()
    log = ResponseLog(run_folder.logs_dir / "dissertation_step2_vocab_full_responses_log.txt")
    kw = dict(cache=cache, stats=stats, response_log=log)
    lookup = VocabLookupService(
        [LcshClient(http, **kw), FastClient(http, **kw),
         GettyAATClient(http, **kw), GettyTGNClient(http, **kw)],
        [FastGeographicClient(http, **kw)], stats=stats)
    return VocabEnhancementProcessor(run_folder, lookup, stats=stats)


def main(argv=None, default_output_root=None) -> int:
    ap = argparse.ArgumentParser(description="Step 2: vocabulary enhancement")
    ap.add_argument("--folder", help="Run folder (default: newest in output root)")
    ap.add_argument("--output-root", default=default_output_root or str(DEFAULT_OUTPUT_ROOT))
    args = ap.parse_args(argv)
    configure_logging(run_parameters={"command": "vocab_enhancement", **vars(args)})
    try:
        rf = RunFolder(args.folder) if args.folder else RunFolder.newest(args.output_root)
        summary = build_processor(rf).run()
    except TswError as e:
        logging.error("%s", e)
        return 1
    logging.info("Subjects with terms: %d/%d; geographic: %d/%d; errors: %d",
                 summary.subjects_with_terms, summary.n_subjects,
                 summary.geographic_with_terms, summary.n_geographic,
                 len(summary.errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
