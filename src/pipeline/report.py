"""Pipeline report: per-step status, timings, usage/cost, issue counts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from api.llm_core.types import Usage

OK, SKIPPED, FAILED, NOT_RUN = "ok", "skipped", "failed", "not_run"


@dataclass
class StepSummary:
    """Returned by every pipeline step adapter."""
    status: str = OK
    usage: Usage = field(default_factory=Usage)
    cost: float = 0.0
    issues: int = 0
    detail: str = ""


@dataclass
class StepReport:
    step: str
    status: str
    seconds: float = 0.0
    summary: Optional[StepSummary] = None
    error: Optional[BaseException] = None


@dataclass
class PipelineReport:
    steps: List[StepReport] = field(default_factory=list)

    @property
    def failed(self) -> Optional[StepReport]:
        return next((s for s in self.steps if s.status == FAILED), None)

    @property
    def ok(self) -> bool:
        return self.failed is None

    @property
    def total_cost(self) -> float:
        return sum(s.summary.cost for s in self.steps if s.summary)

    @property
    def total_usage(self) -> Usage:
        u = [s.summary.usage for s in self.steps if s.summary]
        return Usage(sum(x.prompt_tokens for x in u), sum(x.completion_tokens for x in u),
                     sum(x.cached_tokens for x in u))

    @property
    def total_issues(self) -> int:
        return sum(s.summary.issues for s in self.steps if s.summary)

    def render(self) -> str:
        lines = ["PIPELINE REPORT"]
        for s in self.steps:
            extra = ""
            if s.summary:
                extra = (f" tokens={s.summary.usage.total} cost=${s.summary.cost:.4f}"
                         f" issues={s.summary.issues} {s.summary.detail}")
            if s.error:
                extra += f" error={s.error}"
            lines.append(f"  step {s.step}: {s.status} ({s.seconds:.2f}s){extra}")
        lines.append(f"  total tokens={self.total_usage.total} cost=${self.total_cost:.4f}")
        return "\n".join(lines)
