"""OpenAI Batch API client with caller-supplied stable custom_ids."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

from api.llm_core import (BatchHandle, BatchItem, BatchOutcome, CompletionResult,
                      Usage)
from utils.exceptions import BatchError

from .config import OpenAIConfig

log = logging.getLogger(__name__)
_FAILED = ("failed", "expired", "cancelled")


def _parse_usage(u: Optional[dict]) -> Usage:
    u = u or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    return Usage(u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0, cached)


class OpenAIBatchClient:
    """`client` may be an SDK client or a zero-arg callable returning one (lazy)."""

    def __init__(self, client: Any, config: OpenAIConfig,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client
        self.config = config
        self._sleep = sleep
        self._clock = clock

    @property
    def client(self):
        c = self._client
        if callable(c) and not hasattr(c, "batches"):
            c = self._client = c()
        return c

    @staticmethod
    def build_lines(items: List[BatchItem]) -> List[Dict[str, Any]]:
        ids = [i.custom_id for i in items]
        if len(set(ids)) != len(ids):
            raise BatchError("Duplicate custom_id in batch")
        lines = []
        for item in items:
            r = item.request
            body: Dict[str, Any] = {
                "model": r.model,
                "messages": [{"role": m.role, "content": m.content} for m in r.messages],
                "max_tokens": r.max_tokens,
                "temperature": r.temperature,
            }
            if r.response_format:
                body["response_format"] = dict(r.response_format)
            lines.append({"custom_id": item.custom_id, "method": "POST",
                          "url": "/v1/chat/completions", "body": body})
        return lines

    def submit_batch(self, items: List[BatchItem], description: str = "") -> BatchHandle:
        if not items:
            raise BatchError("Cannot submit an empty batch")
        lines = self.build_lines(items)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "batch.jsonl")
                with open(path, "w", encoding="utf-8") as f:
                    for line in lines:
                        f.write(json.dumps(line) + "\n")
                with open(path, "rb") as f:
                    input_file = self.client.files.create(file=f, purpose="batch")
            job = self.client.batches.create(
                input_file_id=input_file.id, endpoint="/v1/chat/completions",
                completion_window=self.config.batch_completion_window,
                metadata={"description": description,
                          "request_count": str(len(items))})
        except BatchError:
            raise
        except Exception as exc:
            raise BatchError(f"Failed to submit batch: {exc}", cause=exc) from exc
        return BatchHandle(job.id, {"input_file_id": input_file.id,
                                    "request_count": len(items)})

    def check_batch_status(self, handle: BatchHandle):
        try:
            return self.client.batches.retrieve(handle.batch_id)
        except Exception as exc:
            raise BatchError(f"Failed to check batch status: {exc}", cause=exc) from exc

    def collect_batch(self, handle: BatchHandle, timeout: Optional[float] = None,
                      poll_interval: float = 60.0,
                      sleep: Optional[Callable[[float], None]] = None) -> Dict[str, BatchOutcome]:
        sleep = sleep or self._sleep
        timeout = 24 * 3600.0 if timeout is None else timeout
        waited = 0.0
        while True:
            job = self.check_batch_status(handle)
            status = job.status
            if status == "completed":
                return self._retrieve(handle, job)
            if status in _FAILED:
                detail = self._error_detail(job) if status == "failed" else ""
                raise BatchError(f"Batch {handle.batch_id} {status}. {detail}".strip())
            if waited >= timeout:
                raise BatchError(f"Timed out after {timeout}s waiting for batch "
                                 f"{handle.batch_id} (status={status})")
            sleep(poll_interval)
            waited += poll_interval

    def _error_detail(self, job) -> str:
        fid = getattr(job, "error_file_id", None)
        if not fid:
            return ""
        try:
            return self.client.files.content(fid).text[:2000]
        except Exception:  # detail is best-effort
            return ""

    def _retrieve(self, handle: BatchHandle, job) -> Dict[str, BatchOutcome]:
        fid = getattr(job, "output_file_id", None)
        if not fid:
            raise BatchError(f"Batch {handle.batch_id} completed without output file")
        try:
            text = self.client.files.content(fid).text
        except Exception as exc:
            raise BatchError(f"Failed to download batch results: {exc}", cause=exc) from exc
        outcomes: Dict[str, BatchOutcome] = {}
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError as exc:
                raise BatchError("Unparsable batch result line", cause=exc) from exc
            cid = row.get("custom_id")
            outcomes[cid] = self._outcome(cid, row)
        return outcomes

    @staticmethod
    def _outcome(cid: str, row: dict) -> BatchOutcome:
        resp = row.get("response")
        if resp and not row.get("error"):
            body = resp.get("body") or {}
            choices = body.get("choices")
            if resp.get("status_src", 200) == 200 and choices:
                choice = choices[0]
                return BatchOutcome(cid, result=CompletionResult(
                    content=(choice.get("message") or {}).get("content") or "",
                    usage=_parse_usage(body.get("usage")),
                    model=body.get("model") or "",
                    finish_reason=choice.get("finish_reason"), raw=body))
            return BatchOutcome(cid, error=f"Invalid response: {json.dumps(body)[:500]}")
        err = row.get("error")
        return BatchOutcome(cid, error=json.dumps(err) if err else "Unknown result format")
