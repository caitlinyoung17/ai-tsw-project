"""Step 3 processor."""
from __future__ import annotations

import logging
import time
from typing import Optional

from processors.base import ProcessorStep
from api.llm_core import LLMProvider, RunLogs, UsageTracker
from metadata_standard import MetadataStandard
from prompts.params import SELECTION, CallParams
from utils.exceptions import WorkflowFormatError
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

from .batch import SelectionBatchRunner
from .selector import ExtractedEntry, SelectionResult, VocabularySelector
from .writer import SelectionWriter


logger = logging.getLogger(__name__)


class Step2NotRunError(WorkflowFormatError):
    """No entry has vocabulary_search_results: run step 2 first."""


class VocabSelectionProcessor(ProcessorStep):
    name = "vocab_selection"

    def __init__(self, run_folder: RunFolder, provider: LLMProvider, model: str, *,
                 store: Optional[WorkflowStore] = None, params: CallParams = SELECTION,
                 use_batch: Optional[bool] = None, batch_threshold: int = 5,
                 sleep=None) -> None:
        self.run_folder = run_folder
        self.provider = provider
        self.store = store or WorkflowStore(run_folder)
        self.use_batch = use_batch
        self.batch_threshold = batch_threshold
        kwargs = {"sleep": sleep} if sleep else {}
        self.selector = VocabularySelector(provider, model, params=params, **kwargs)
        self.batch_sleep = sleep
        self.usage = UsageTracker()

    def _write_usage_logs(self, pairs, results, batch: bool, elapsed: float) -> None:
        pricing = getattr(self.provider, "pricing", None)
        if pricing is None:
            return
        logs = RunLogs(pricing, self.run_folder.logs_dir, "dissertation_vocabulary_selection")
        model = self.selector.model
        logger.info("Writing token usage and full-response logs to %s", self.run_folder.logs_dir)
        for entry, _ in pairs:
            r = results.get(entry.entry_id)
            if r is not None and r.usage is not None:
                logs.response(entry.entry_id, entry.title or entry.entry_id, r.raw or "",
                              model, r.usage, 0.0, batch,
                              {"status": r.status.value,
                               **({"error": r.error} if r.error else {})})
        issues = sum(1 for r in results.values() if r.has_issue)
        logs.summary(model, len(results), issues, elapsed, self.usage.usage, batch,
                     {"Processing mode": "BATCH" if batch else "INDIVIDUAL"})

    def run(self) -> dict:
        self.run_folder.require_workflow_files()
        logger.info("Sub-step 1/3: loading workflow")
        workflow = self.store.load()
        if not any("vocabulary_search_results" in (it.get("analysis") or {})
                   for it in workflow.items):
            raise Step2NotRunError(
                "No vocabulary_search_results found; run step 2 first",
                path=str(self.run_folder.json_path))
        pairs = [(ExtractedEntry.from_item(i, it), MetadataStandard.from_workflow_item(it))
                 for i, it in enumerate(workflow.items)]
        n_requests = sum(1 for _, s in pairs if s.has_candidates())
        batch = self.use_batch
        if batch is None:
            batch = self.provider.supports_batch and n_requests >= self.batch_threshold
        if batch and not self.provider.supports_batch:
            batch = False
        t_start = time.monotonic()
        logger.info("Sub-step 2/3: selecting terms for %d entr(ies) via %s",
                    n_requests, "BATCH" if batch else "INDIVIDUAL calls")
        if batch:
            results = SelectionBatchRunner(self.provider, self.selector,
                                           sleep=self.batch_sleep).run(pairs)
        else:
            results = {}
            for n, (e, s) in enumerate(pairs, 1):
                logger.info("Entry %d/%d: %s", n, len(pairs), e.title or e.entry_id)
                results[e.entry_id] = self.selector.select(e, s)
        for r in results.values():
            if r.usage is not None:
                self.usage.record(r.usage, batch=batch)
        logger.info("Sub-step 3/3: writing JSON, Excel and selection report")
        self._write_usage_logs(pairs, results, batch, time.monotonic() - t_start)
        writer = SelectionWriter(self.store)
        new = writer.write_json(workflow, results)
        writer.write_excel(new)
        summary = writer.write_selection_report(new, results)
        summary["usage"] = self.usage.summary()
        return summary
