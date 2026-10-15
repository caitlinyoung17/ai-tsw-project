"""In-process pipeline: chains ProcessorSteps with explicit dependencies."""
from __future__ import annotations

import time
from typing import List, Optional

from processors.base import ProcessorStep
from utils.exceptions import ConfigError, StepFailedError, TswError, WorkflowFilesNotFound

from utils.logging_setup import step_context

from .context import PipelineContext
from .report import FAILED, NOT_RUN, OK, PipelineReport, StepReport


def _label(step: ProcessorStep) -> str:
    return f"step {step.name}: {step.short_name}" if step.short_name else f"step {step.name}"


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

    def validate_selection(self, only: Optional[List[str]], resuming: bool) -> None:
        """Reject step selections whose dependencies cannot be satisfied.

        Fresh run (no existing run folder): every dependency of a selected step
        must also be selected. When resuming, earlier outputs live in the run
        folder, so dependencies may be omitted.
        """
        names = [s.name for s in self.steps]
        unknown = [n for n in (only or []) if n not in names]
        if unknown:
            raise ConfigError(f"Unknown steps {unknown}; choose from {names}")
        if only is None or resuming:
            return
        chosen = set(only)
        missing = {s.name: sorted(set(s.depends_on) - chosen)
                   for s in self.steps if s.name in chosen and set(s.depends_on) - chosen}
        if missing:
            detail = "; ".join(f"step {k} requires {v}" for k, v in missing.items())
            raise ConfigError(f"Incompatible --steps selection: {detail} "
                              "(add them, or pass --folder to resume an existing run)")

    def run(self, context: PipelineContext, start_at: Optional[str] = None,
            stop_after: Optional[str] = None, only: Optional[List[str]] = None
            ) -> PipelineReport:
        selected = self._select(start_at, stop_after)
        if only is not None:
            selected = [s for s in selected if s.name in only]
        report = PipelineReport()
        failed: set = set()
        log = context.logger
        total = len(selected)
        log.info("Pipeline starting: %d step(s) to run: %s", total,
                 ", ".join(_label(s) for s in selected))
        for n, step in enumerate(selected, 1):
            with step_context(_label(step)):
                blocked = failed & set(step.depends_on)
                if blocked:
                    log.warning("(%d/%d) SKIPPED: depends on failed step(s) %s",
                                n, total, sorted(blocked))
                    report.steps.append(StepReport(step.name, NOT_RUN))
                    failed.add(step.name)
                    continue
                t0 = self._now()
                log.info("(%d/%d) STARTING: %s", n, total, step.description)
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
                    log.error("FAILED after %.1fs: %s", self._now() - t0, e)
                    if not context.config.keep_going:
                        log.error("Stopping pipeline (use --keep-going to continue past failures)")
                        break
                    continue
                report.steps.append(StepReport(step.name, summary.status, self._now() - t0, summary))
                log.info("FINISHED in %.1fs: %s %s", self._now() - t0,
                         summary.status, summary.detail)
        return report
