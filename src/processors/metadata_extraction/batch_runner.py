"""Batch extraction keyed by stable document ids."""
from __future__ import annotations

import logging
from typing import Dict, List

from api.llm_core.types import BatchItem
from utils.exceptions import BatchError, LLMResponseError, TswError

from .collector import Document
from .extractor import MetadataExtractor
from .results import ExtractionOutcome, Failed, Succeeded

logger = logging.getLogger(__name__)


class BatchExtractor:
    def __init__(self, provider, extractor: MetadataExtractor,
                 on_batch_failure: str = "raise", poll_interval: float = 60.0,
                 timeout=None, sleep=None) -> None:
        if on_batch_failure not in ("raise", "individual"):
            raise ValueError("on_batch_failure must be 'raise' or 'individual'")
        self.provider = provider
        self.extractor = extractor
        self.on_batch_failure = on_batch_failure
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep

    def run(self, documents: List[Document]) -> Dict[str, ExtractionOutcome]:
        outcomes: Dict[str, ExtractionOutcome] = {}
        items: List[BatchItem] = []
        by_id: Dict[str, Document] = {}
        for doc in documents:
            try:
                if self.extractor.needs_chunking(doc):  # many requests: run individually
                    outcomes[doc.doc_id] = self._individual(doc)
                    continue
                request = self.extractor.build_request(doc)
            except TswError as e:  # empty documents never enter the batch
                outcomes[doc.doc_id] = Failed(doc.doc_id, e)
                continue
            items.append(BatchItem(custom_id=doc.doc_id, request=request))
            by_id[doc.doc_id] = doc
        if items:
            try:
                handle = self.provider.submit_batch(items)
                results = self.provider.collect_batch(
                    handle, self.timeout, self.poll_interval, self.sleep)
            except BatchError as e:
                if self.on_batch_failure == "raise":
                    raise
                logger.warning("Batch failed (%s); falling back to individual calls "
                               "for %d documents", e, len(items))
                for doc_id, doc in by_id.items():
                    outcomes[doc_id] = self._individual(doc)
            else:
                for doc_id, doc in by_id.items():
                    outcomes[doc_id] = self._from_batch(doc, results.get(doc_id))
        # preserve input order
        return {d.doc_id: outcomes[d.doc_id] for d in documents}

    def _from_batch(self, doc: Document, outcome) -> ExtractionOutcome:
        if outcome is None:
            return Failed(doc.doc_id, LLMResponseError(
                f"No batch result for {doc.doc_id}", path=doc.path))
        if outcome.error or outcome.result is None:
            return Failed(doc.doc_id, LLMResponseError(
                outcome.error or "Empty batch result", path=doc.path))
        try:
            return Succeeded(self.extractor.parse(doc, outcome.result))
        except TswError as e:
            return Failed(doc.doc_id, e)

    def _individual(self, doc: Document) -> ExtractionOutcome:
        try:
            return Succeeded(self.extractor.extract(doc))
        except TswError as e:
            return Failed(doc.doc_id, e)
