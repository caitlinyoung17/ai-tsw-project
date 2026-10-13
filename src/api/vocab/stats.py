"""Per-run statistics; vocabulary names are registered dynamically."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Callable


def _blank() -> dict:
    return {"requests": 0, "successful": 0, "failed": 0, "total_time": 0.0,
            "terms_found": 0, "cache_hits": 0}


class VocabStatsTracker:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self.start_time = clock()
        self.api_breakdown: dict[str, dict] = {}
        self.subject_results: dict[str, dict] = {}

    def _subject(self, subject: str) -> dict:
        return self.subject_results.setdefault(subject, {
            "total_terms": 0, "terms_by_api": defaultdict(int),
            "processing_time": 0.0})

    def record_call(self, vocab: str, subject: str, success: bool,
                    elapsed: float, terms_found: int) -> None:
        s = self.api_breakdown.setdefault(vocab, _blank())
        s["requests"] += 1
        s["total_time"] += elapsed
        if success:
            s["successful"] += 1
            s["terms_found"] += terms_found
        else:
            s["failed"] += 1
        r = self._subject(subject)
        r["terms_by_api"][vocab] += terms_found if success else 0
        r["total_terms"] += terms_found if success else 0
        r["processing_time"] += elapsed

    def record_cache_hit(self, vocab: str, subject: str, terms_found: int) -> None:
        s = self.api_breakdown.setdefault(vocab, _blank())
        s["cache_hits"] += 1
        r = self._subject(subject)
        r["terms_by_api"][vocab] += terms_found
        r["total_terms"] += terms_found

    def summary(self, total_subjects: int = 0) -> dict[str, Any]:
        """New dict each call; internal state is never mutated."""
        total_time = self._clock() - self.start_time
        breakdown = {}
        for name, s in self.api_breakdown.items():
            n = s["requests"]
            breakdown[name] = {
                **s,
                "success_rate": s["successful"] / n * 100 if n else 0,
                "avg_time": s["total_time"] / n if n else 0,
            }
        return {
            "total_requests": sum(s["requests"] for s in self.api_breakdown.values()),
            "total_cache_hits": sum(s["cache_hits"] for s in self.api_breakdown.values()),
            "total_time": total_time,
            "avg_time_per_subject": total_time / total_subjects if total_subjects else 0,
            "subject_results": {
                k: {**v, "terms_by_api": dict(v["terms_by_api"])}
                for k, v in self.subject_results.items()},
            "api_breakdown": breakdown,
        }
