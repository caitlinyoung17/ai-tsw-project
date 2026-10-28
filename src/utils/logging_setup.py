"""Central logging configuration. Never called at import time."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Mapping, Optional

_NOISY_LOGGERS = ("httpx", "httpcore", "openai", "urllib3", "portkey_ai")
_MARKER = "_tsw_handler"
_current_step: ContextVar[str] = ContextVar("tsw_current_step", default="")

_SECRET_HINTS = ("key", "token", "secret", "password")
_run_parameters: Dict[str, str] = {}


def set_run_parameters(params: Mapping[str, Any]) -> None:
    """Record the inputs of this run; every log file header and the console
    log report them. Unset values show as "(default)"; secrets are masked."""
    _run_parameters.clear()
    for k, v in params.items():
        if v is None or v == "":
            shown = "(default)"
        elif any(h in k.lower() for h in _SECRET_HINTS):
            shown = "****"
        else:
            shown = str(v)
        _run_parameters[k] = shown


def run_parameters() -> Dict[str, str]:
    return dict(_run_parameters)


def run_parameters_block(width: int = 60) -> str:
    """Text block for the top of a log file; empty when nothing was recorded."""
    if not _run_parameters:
        return ""
    lines = ["RUN PARAMETERS:", "-" * 30]
    lines += [f"{k}: {v}" for k, v in _run_parameters.items()]
    return "\n".join(lines) + "\n" + "=" * width + "\n\n"


@contextmanager
def step_context(label: str) -> Iterator[None]:
    """Tag every log record emitted inside the block with ``[label]``."""
    token = _current_step.set(label)
    try:
        yield
    finally:
        _current_step.reset(token)


class _StepFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        label = _current_step.get()
        record.step_prefix = f"[{label}] " if label else ""
        return True


def configure_logging(level: int = logging.INFO,
                      log_file: Optional[str] = None,
                      run_parameters: Optional[Mapping[str, Any]] = None) -> None:
    """Configure the root logger. Idempotent: repeated calls do not add
    duplicate handlers."""
    if run_parameters is not None:
        set_run_parameters(run_parameters)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(step_prefix)s%(message)s")

    def _has(kind) -> bool:
        return any(getattr(h, _MARKER, None) == kind for h in root.handlers)

    if not _has("console"):
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        h.addFilter(_StepFilter())
        setattr(h, _MARKER, "console")
        root.addHandler(h)

    if log_file is not None:
        kind = f"file:{log_file}"
        if not _has(kind):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            fh.addFilter(_StepFilter())
            setattr(fh, _MARKER, kind)
            root.addHandler(fh)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
