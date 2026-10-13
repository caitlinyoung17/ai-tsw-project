"""Step 1.5 processor: detect failed batch items and reprocess them."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from processors.base import ProcessorStep
from utils.exceptions import TswError
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

from .detection import FailureDetector
from .report import ItemOutcome, render_cleanup_report
from .reprocessor import ItemReprocessor
from .writer import CleanupWriter

logger = logging.getLogger(__name__)


class CleanupStatus(Enum):
    NOT_A_BATCH_RUN = "not_a_batch_run"
    NOTHING_TO_CLEAN = "nothing_to_clean"
    CLEANED = "cleaned"


@dataclass(frozen=True)
class CleanupSummary:
    status: CleanupStatus
    n_fixed: int = 0
    n_still_failed: int = 0


def is_batch_run(api_stats: dict) -> bool:
    """Explicit `processing_mode` marker; legacy output (no marker) is assumed batch."""
    mode = (api_stats or {}).get("processing_mode")
    if mode is None:
        return True
    return str(mode).upper() == "BATCH"


class BatchCleanupProcessor(ProcessorStep):
    name = "batch_cleanup"

    def __init__(self, reprocessor: ItemReprocessor,
                 detector: FailureDetector | None = None) -> None:
        self.reprocessor = reprocessor
        self.detector = detector or FailureDetector()

    def run(self, run_folder: RunFolder, store: WorkflowStore | None = None
            ) -> CleanupSummary:
        store = store or WorkflowStore(run_folder)
        workflow = store.load()  # raises on missing/malformed
        if not is_batch_run(workflow.api_stats):
            logger.info("Not a batch run; cleanup not needed.")
            return CleanupSummary(CleanupStatus.NOT_A_BATCH_RUN)
        failed = self.detector.detect(workflow.items)
        if not failed:
            return CleanupSummary(CleanupStatus.NOTHING_TO_CLEAN)
        fixes: Dict[int, object] = {}
        outcomes: List[ItemOutcome] = []
        for f in failed:
            try:
                fixes[f.index] = self.reprocessor.reprocess(f.item)
                outcomes.append(ItemOutcome(f, True))
            except TswError as e:
                logger.error("Could not repair item %d: %s", f.index, e)
                outcomes.append(ItemOutcome(f, False, str(e)))
        CleanupWriter(store).apply(workflow, fixes)
        report = run_folder.metadata_dir / "step1_5_cleanup_report.txt"
        report.write_text(render_cleanup_report(outcomes), encoding="utf-8")
        n_fixed = len(fixes)
        return CleanupSummary(CleanupStatus.CLEANED, n_fixed, len(failed) - n_fixed)
