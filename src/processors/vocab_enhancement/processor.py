"""Step 2 processor. Not yet a ProcessorStep subclass (processors/base.py
arrives in 06); it exposes ``name`` and ``run`` per that interface."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from api.vocab.stats import VocabStatsTracker
from processors.base import ProcessorStep
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

from .extraction import extract_subjects_and_geo
from .lookup import VocabLookupService
from .writers import write_excel, write_json, write_report, write_usage_log

logger = logging.getLogger(__name__)
USAGE_LOG_NAME = "dissertation_step2_vocab_api_usage_log.txt"


@dataclass
class VocabSummary:
    n_subjects: int = 0
    n_geographic: int = 0
    subjects_with_terms: int = 0
    geographic_with_terms: int = 0
    errors: list[str] = field(default_factory=list)
    total_requests: int = 0
    nothing_to_do: bool = False


class VocabEnhancementProcessor(ProcessorStep):
    name = "vocab_enhancement"

    def __init__(self, run_folder: RunFolder, lookup: VocabLookupService, *,
                 store: Optional[WorkflowStore] = None,
                 stats: Optional[VocabStatsTracker] = None,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.run_folder = run_folder
        self.lookup = lookup
        self.store = store or WorkflowStore(run_folder)
        self.stats = stats or getattr(lookup, "stats", None)
        self.clock = clock

    def run(self, run_folder: Optional[RunFolder] = None) -> VocabSummary:
        rf = run_folder or self.run_folder
        rf.require_workflow_files()           # WorkflowFilesNotFound
        logger.info("Sub-step 1/4: loading workflow and extracting subjects")
        workflow = self.store.load()          # WorkflowFormatError
        subjects: set[str] = set()
        geos: set[str] = set()
        for item in workflow.items:
            s, g = extract_subjects_and_geo(item)
            subjects.update(s)
            geos.update(g)
        if not subjects and not geos:
            logger.info("NoSubjectsFound: no subjects or geographic entities")
            return VocabSummary(nothing_to_do=True)

        logger.info("Sub-step 2/4: looking up %d subject(s) and %d geographic "
                    "entit(ies) in controlled vocabularies", len(subjects), len(geos))
        standards = self.lookup.lookup(sorted(subjects), sorted(geos))
        logger.info("Sub-step 3/4: writing Excel, JSON and vocabulary report")
        write_excel(self.store, standards)
        write_json(self.store, workflow, standards)
        rf.ensure_dirs()
        write_report(rf.vocab_report_path, standards, clock=self.clock,
                     max_terms_per_vocab=self.lookup.per_vocab_limit)
        logger.info("Sub-step 4/4: writing API usage log")
        total_requests = 0
        if self.stats:
            summary = self.stats.summary(len(subjects) + len(geos))
            total_requests = summary["total_requests"]
            write_usage_log(rf.logs_dir / USAGE_LOG_NAME, summary,
                            len(subjects) + len(geos), self.clock)
        errors = list(getattr(standards, "errors", []))
        return VocabSummary(
            n_subjects=len(subjects), n_geographic=len(geos),
            subjects_with_terms=sum(1 for t in standards.subject_to_terms.values() if t),
            geographic_with_terms=sum(1 for t in standards.geographic_to_terms.values() if t),
            errors=errors, total_requests=total_requests)
