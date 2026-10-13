"""Step 1 processor: collect -> extract (batch or individual) -> write."""
from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional

from processors.base import ProcessorStep
from utils.exceptions import TswError
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

from .batch_runner import BatchExtractor
from .collector import Document, DocumentCollector
from .extractor import MetadataExtractor
from .results import ExtractionOutcome, Failed, RunSummary, Succeeded, summarize
from .writer import WorkflowWriter

logger = logging.getLogger(__name__)


class MetadataExtractionProcessor(ProcessorStep):
    name = "metadata_extraction"

    def __init__(self, provider, extractor: MetadataExtractor,
                 collector: Optional[DocumentCollector] = None,
                 use_batch: Optional[bool] = None,
                 should_use_batch: Optional[Callable[[int], bool]] = None,
                 on_batch_failure: str = "raise",
                 sleep: Callable[[float], None] = time.sleep,
                 throttle: float = 1.0,
                 clock: Callable[[], float] = time.time) -> None:
        self.provider = provider
        self.extractor = extractor
        self.collector = collector or DocumentCollector()
        self.use_batch = use_batch  # None = decide by provider/size
        self._should_use_batch = should_use_batch or getattr(
            provider, "should_use_batch", lambda n: n > 5)
        self.on_batch_failure = on_batch_failure
        self.sleep = sleep
        self.throttle = throttle
        self.clock = clock

    def _batch_wanted(self, n: int) -> bool:
        if not getattr(self.provider, "supports_batch", False):
            return False
        if self.use_batch is not None:
            return self.use_batch
        return bool(self._should_use_batch(n))

    def _run_individual(self, documents) -> Dict[str, ExtractionOutcome]:
        outcomes: Dict[str, ExtractionOutcome] = {}
        for i, doc in enumerate(documents):
            try:
                outcomes[doc.doc_id] = Succeeded(self.extractor.extract(doc))
            except TswError as e:
                logger.error("Extraction failed for %s: %s", doc.filename, e)
                outcomes[doc.doc_id] = Failed(doc.doc_id, e)
            if i < len(documents) - 1 and self.throttle:
                self.sleep(self.throttle)
        return outcomes

    def run(self, input_folder, run_folder: RunFolder) -> RunSummary:
        start = self.clock()
        collection = self.collector.collect(input_folder)
        docs = collection.documents
        if self._batch_wanted(len(docs)):
            mode = "BATCH"
            outcomes = BatchExtractor(
                self.provider, self.extractor, self.on_batch_failure,
                sleep=self.sleep).run(docs)
        else:
            mode = "INDIVIDUAL"
            outcomes = self._run_individual(docs)
        summary = summarize(outcomes, mode, self.clock() - start,
                            {s.path: s.reason for s in collection.skipped})
        WorkflowWriter(WorkflowStore(run_folder)).write(
            docs, outcomes, summary, collection.skipped)
        logger.info("Step 1 complete: %d/%d succeeded (%s)",
                    summary.succeeded, summary.total, mode)
        return summary
