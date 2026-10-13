"""In-process pipeline: chains ProcessorSteps with explicit dependencies."""
from __future__ import annotations

import time
from typing import List, Optional

from processors.base import ProcessorStep
from utils.exceptions import StepFailedError, TswError, WorkflowFilesNotFound

from .context import PipelineContext
from .report import FAILED, NOT_RUN, OK, PipelineReport, StepReport


class Pipeline:
    def __init__(self, steps: List[ProcessorStep], sleep_clock=time.monotonic) -> None:
        self.steps = list(steps)
        self._now = sleep_clock

    def _select(self, start_at, stop_after) -> List[ProcessorStep]:
        names = [s.name for s in self.steps]
        for n in (start_at, stop_after):
            if n is not None and n not in names:
                raise ValueError(f"Unknown step {n!r}; choose from {names}")
        lo = names.index(start_at) if start_at else 0
        hi = names.index(stop_after) if stop_after else len(names) - 1
        return self.steps[lo:hi + 1]

    def run(self, context: PipelineContext, start_at: Optional[str] = None,
            stop_after: Optional[str] = None, only: Optional[List[str]] = None
            ) -> PipelineReport:
        selected = self._select(start_at, stop_after)
        if only is not None:
            selected = [s for s in selected if s.name in only]
        report = PipelineReport()
        failed: set = set()
        for step in selected:
            blocked = failed & set(getattr(step, "depends_on", ()))
            if blocked:
                report.steps.append(StepReport(step.name, NOT_RUN))
                failed.add(step.name)
                continue
            t0 = self._now()
            try:
                if context.run_folder is not None:
                    pass
                elif step.name != self.steps[0].name:
                    raise WorkflowFilesNotFound(
                        f"Step {step.name} needs an existing run folder (--folder)")
                summary = step.run(context)
            except TswError as e:
                err = StepFailedError(f"Step {step.name} failed: {e}", step=step.name, cause=e)
                report.steps.append(StepReport(step.name, FAILED, self._now() - t0, error=err))
                failed.add(step.name)
                if not context.config.keep_going:
                    break
                continue
            report.steps.append(StepReport(step.name, summary.status, self._now() - t0, summary))
            context.logger.info("step %s: %s %s", step.name, summary.status, summary.detail)
        return report
