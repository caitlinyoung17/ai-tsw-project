"""Per-run usage tracking and token/cost log rendering."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from utils.logging_setup import run_parameters_block

from .pricing import PricingProvider
from .types import Usage

_log = logging.getLogger(__name__)
Writer = Union[Callable[[str], None], Path]


@dataclass
class UsageTracker:
    """Per-run replacement for the global api_stats."""
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0
    retries: int = 0
    processing_times: List[float] = field(default_factory=list)

    def record(self, usage: Usage, batch: bool = False, elapsed: Optional[float] = None) -> None:
        """Record one logical call (call once per call, not once per retry)."""
        self.total_requests += 1
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_cached_tokens += usage.cached_tokens
        if elapsed is not None:
            self.processing_times.append(elapsed)

    def record_retry(self, count: int = 1) -> None:
        self.retries += count

    @property
    def usage(self) -> Usage:
        return Usage(self.total_prompt_tokens, self.total_completion_tokens,
                     self.total_cached_tokens)

    def summary(self) -> Dict[str, Any]:
        n = len(self.processing_times)
        return {
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "retries": self.retries,
            "total_time": sum(self.processing_times),
            "average_time": (sum(self.processing_times) / n) if n else 0.0,
        }


class RunLogs:
    """The per-step token-usage summary and full-responses log pair
    (``<stem>_token_usage_log.txt`` / ``<stem>_full_responses_log.txt``).

    Logging is informational: any failure is reported as a warning and never
    fails the step. The responses file is recreated on the first response of
    each run rather than appended across runs.
    """

    def __init__(self, pricing: PricingProvider, logs_dir: Path, stem: str,
                 provider_label: str = "OpenAI",
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.stem = stem
        self.logs_dir = Path(logs_dir)
        self.summary_path = self.logs_dir / f"{stem}_token_usage_log.txt"
        self.responses_path = self.logs_dir / f"{stem}_full_responses_log.txt"
        self._summary = UsageLogger(pricing, provider_label, self.summary_path, clock)
        self._responses = UsageLogger(pricing, provider_label, self.responses_path, clock)
        self._started = False

    def _guard(self, what: str, fn, *a, **kw) -> None:
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            fn(*a, **kw)
        except Exception as e:  # never fail a step over its usage logs
            _log.warning("Could not write %s log (%s): %s", self.stem, what, e)

    def response(self, row_number: Any, label: Any, response_text: str, model: str,
                 usage: Usage, elapsed: float, batch: bool = False,
                 additional_info: Optional[Mapping[str, Any]] = None) -> None:
        def _write():
            first = not self._started
            if first:
                self.responses_path.unlink(missing_ok=True)
                self._started = True
            self._responses.log_response(
                self.stem, row_number, label, response_text, model, usage, elapsed,
                batch=batch, additional_info=additional_info, include_header=first)
        self._guard("full-responses", _write)

    def summary(self, model: str, total_items: int, items_with_issues: int,
                total_time: float, usage: Usage, batch: bool = False,
                additional_metrics: Optional[Mapping[str, Any]] = None) -> None:
        self._guard("token-usage", self._summary.log_summary, self.stem, model,
                    total_items, items_with_issues, total_time, usage, batch,
                    additional_metrics)
        _log.info("Token usage log written to %s", self.summary_path)


def _emit(writer: Writer, text: str, append: bool) -> None:
    if callable(writer):
        writer(text)
        return
    path = Path(writer)
    with open(path, "a" if append else "w", encoding="utf-8") as fh:
        fh.write(text)


class UsageLogger:
    """Renders the legacy token_logging text formats to an injected writer."""

    def __init__(self, pricing: PricingProvider, provider_label: str, writer: Writer,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.pricing = pricing
        self.provider_label = provider_label
        self.writer = writer
        self.clock = clock

    def _now(self) -> str:
        return self.clock().strftime('%Y-%m-%d %H:%M:%S')

    def log_summary(self, script_name: str, model_name: str, total_items: int,
                    items_with_issues: int, total_time: float, usage: Usage,
                    batch: bool = False,
                    additional_metrics: Optional[Mapping[str, Any]] = None) -> str:
        p = self.pricing.resolve(model_name)
        total_tokens = usage.total
        total_cost = self.pricing.cost(usage, model_name, batch=batch)
        input_cost = (usage.prompt_tokens / 1000) * p.input_per_1k
        output_cost = (usage.completion_tokens / 1000) * p.output_per_1k
        if batch:
            input_cost *= p.batch_discount
            output_cost *= p.batch_discount
        ok = total_items - items_with_issues
        avg_time = total_time / total_items if total_items > 0 else 0
        avg_tokens = total_tokens / ok if ok > 0 else 0
        avg_cost = total_cost / ok if ok > 0 else 0
        suffix = " (batch discounted)" if batch else ""

        o: List[str] = []
        o.append(f"{self.provider_label} API Usage Log - {script_name.replace('_', ' ').title()}\n")
        o.append("=" * 60 + "\n")
        o.append(f"Processing completed at: {self._now()}\n\n")
        o.append(run_parameters_block(60))
        o.append("PROCESSING SUMMARY:\n" + "-" * 30 + "\n")
        o.append(f"Total items processed: {total_items}\n")
        o.append(f"Successful items: {ok}\n")
        o.append(f"Items with issues: {items_with_issues}\n")
        o.append(f"Success rate: {(ok / total_items) * 100:.1f}%\n" if total_items > 0
                 else "Success rate: 0%\n")
        o.append(f"Total processing time: {total_time:.2f} seconds\n")
        o.append(f"Average time per item: {avg_time:.2f} seconds\n\n")
        o.append("MODEL INFORMATION:\n" + "-" * 30 + "\n")
        o.append(f"Model used: {model_name}\n")
        o.append(f"Input token rate: ${p.input_per_1k:.5f} per 1K tokens\n")
        o.append(f"Output token rate: ${p.output_per_1k:.5f} per 1K tokens\n")
        if batch:
            o.append(f"Batch discount applied: {p.batch_discount * 100:.0f}%\n")
        o.append("\n")
        o.append("TOKEN USAGE:\n" + "-" * 30 + "\n")
        o.append(f"Total prompt tokens: {usage.prompt_tokens:,}\n")
        o.append(f"Total completion tokens: {usage.completion_tokens:,}\n")
        if usage.cached_tokens > 0:
            o.append(f"Total cached tokens: {usage.cached_tokens:,}\n")
        o.append(f"Total tokens: {total_tokens:,}\n")
        o.append(f"Average tokens per successful item: {avg_tokens:.1f}\n\n")
        o.append("COST BREAKDOWN:\n" + "-" * 30 + "\n")
        o.append(f"Input token cost: ${input_cost:.4f}{suffix}\n")
        o.append(f"Output token cost: ${output_cost:.4f}{suffix}\n")
        o.append(f"Total actual cost: ${total_cost:.4f}\n")
        o.append(f"Average cost per successful item: ${avg_cost:.4f}\n")
        if batch:
            regular = self.pricing.cost(usage, model_name, batch=False)
            o.append(f"Regular API cost would have been: ${regular:.4f}\n")
            o.append(f"Batch processing savings: ${regular - total_cost:.4f}\n")
        o.append("\n")
        if additional_metrics:
            o.append("ADDITIONAL METRICS:\n" + "-" * 30 + "\n")
            for k, v in additional_metrics.items():
                o.append(f"{k}: {v}\n")
            o.append("\n")
        o.append("EFFICIENCY METRICS:\n" + "-" * 30 + "\n")
        tps = total_tokens / total_time if total_time > 0 else 0
        cpm = (total_cost / total_time) * 60 if total_time > 0 else 0
        o.append(f"Tokens processed per second: {tps:.1f}\n")
        o.append(f"Cost per minute of processing: ${cpm:.4f}\n")
        if ok > 0:
            ipm = (ok / total_time) * 60 if total_time > 0 else 0
            o.append(f"Items processed per minute: {ipm:.1f}\n")
        text = "".join(o)
        _emit(self.writer, text, append=False)
        return text

    def log_response(self, script_name: str, row_number: Any, barcode: Any,
                     response_text: str, model_name: str, usage: Usage,
                     processing_time: float, batch: bool = False,
                     additional_info: Optional[Mapping[str, Any]] = None,
                     include_header: bool = False) -> str:
        cost = self.pricing.cost(usage, model_name, batch=batch)
        total = usage.prompt_tokens + usage.completion_tokens + usage.cached_tokens
        o: List[str] = []
        if include_header:
            o.append(f"LLM Full Responses Log - {script_name.replace('_', ' ').title()}\n")
            o.append(f"Created at: {self._now()}\n")
            o.append("=" * 80 + "\n\n")
            o.append(run_parameters_block(80))
        o.append(f"Row {row_number} - Barcode {barcode} - {self._now()}\n")
        o.append("-" * 80 + "\n")
        o.append(f"MODEL: {model_name}\n")
        o.append(f"PROCESSING TIME: {processing_time:.2f}s\n")
        o.append(f"TOKENS: {total:,} (Prompt: {usage.prompt_tokens:,}, "
                 f"Completion: {usage.completion_tokens:,}")
        if usage.cached_tokens > 0:
            o.append(f", Cached: {usage.cached_tokens:,}")
        o.append(")\n")
        o.append(f"ESTIMATED COST: ${cost:.4f}\n")
        if additional_info:
            for k, v in additional_info.items():
                o.append(f"{k.upper()}: {v}\n")
        o.append(f"\nLLM RESPONSE:\n{response_text}\n\n")
        o.append("=" * 80 + "\n\n")
        text = "".join(o)
        _emit(self.writer, text, append=True)
        return text
