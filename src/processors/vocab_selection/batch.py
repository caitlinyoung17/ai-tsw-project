"""Batch execution of selection requests with an explicit custom_id mapping."""
from __future__ import annotations

import logging
from typing import Optional, Sequence, Tuple

from api.llm_core import BatchItem, LLMProvider
from metadata_standard import MetadataStandard

from .selector import (ExtractedEntry, SelectionResult, SelectionStatus,
                       VocabularySelector)

logger = logging.getLogger(__name__)


class SelectionBatchRunner:
    def __init__(self, provider: LLMProvider, selector: VocabularySelector, *,
                 timeout: Optional[float] = None, poll_interval: float = 60.0,
                 sleep=None) -> None:
        self.provider = provider
        self.selector = selector
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.sleep = sleep

    def run(self, entries: Sequence[Tuple[ExtractedEntry, MetadataStandard]]
            ) -> dict[int, SelectionResult]:
        """entry_id -> result. BatchError from the provider propagates (no silent fallback)."""
        results: dict[int, SelectionResult] = {}
        items: list[BatchItem] = []
        mapping: dict[str, Tuple[int, MetadataStandard]] = {}
        for entry, standard in entries:
            request = self.selector.build_request(entry, standard)
            if request is None:
                results[entry.entry_id] = SelectionResult(
                    SelectionStatus.SKIPPED_NO_CANDIDATES)
                continue
            cid = f"entry-{entry.entry_id}"
            mapping[cid] = (entry.entry_id, standard)
            items.append(BatchItem(cid, request))
        if not items:
            return results
        logger.info("Batch: submitting %d request(s)", len(items))
        handle = self.provider.submit_batch(items)
        logger.info("Batch: submitted; waiting for results")
        outcomes = self.provider.collect_batch(
            handle, timeout=self.timeout, poll_interval=self.poll_interval,
            sleep=self.sleep)
        for cid, (entry_id, standard) in mapping.items():
            outcome = outcomes.get(cid)
            if outcome is None:
                results[entry_id] = SelectionResult(
                    SelectionStatus.FAILED, error="Missing from batch results")
            else:
                results[entry_id] = self.selector.to_result(
                    outcome.result, standard, outcome.error)
        return results
