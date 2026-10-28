"""Full-response log: overwritten at construction (not appended across runs)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence, Union

from metadata_standard import Term
from utils.logging_setup import run_parameters_block


class ResponseLog:
    def __init__(self, path: Union[str, Path],
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.path = Path(path)
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "DISSERTATION VOCABULARY API DETAILED RESPONSES LOG\n"
            + "=" * 60 + "\n\n" + run_parameters_block(60), encoding="utf-8")

    def record(self, vocab: str, subject: str, query: str,
               terms: Sequence[Term], elapsed: float, error: str = "",
               cached: bool = False) -> None:
        lines = [f"TIMESTAMP: {self._clock():%Y-%m-%d %H:%M:%S}",
                 f"SUBJECT: {subject}", f"API: {vocab}",
                 f"QUERY: {query}{' (CACHED)' if cached else ''}",
                 f"PROCESSING TIME: {elapsed:.3f}s"]
        if error:
            lines += [f"ERROR: {error}", "RESPONSE: Failed"]
        else:
            lines += [f"TERMS FOUND: {len(terms)}", "RESPONSE:"]
            for i, t in enumerate(terms, 1):
                lines += [f"  {i}. {t.label}", f"     URI: {t.uri}",
                          f"     Source: {t.source}"]
        lines += ["-" * 60, "", ""]
        with self.path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
