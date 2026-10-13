"""Template-method base for vocabulary service clients."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from metadata_standard import MetadataStandard, Term
from utils.exceptions import VocabularyError

from .cache import QueryCache
from .http import HttpClient
from .stats import VocabStatsTracker

Request = tuple[str, dict]


class VocabularyClient:
    """Subclasses implement ``_build_request`` and ``_parse`` (and optionally
    the fallback hooks). Zero hits returns ``[]``; transport/parse failures
    raise ``VocabHttpError``/``VocabParseError``."""

    name = "Vocab"            # stats/cache service name
    group = "Vocab"           # per-vocabulary cap group used by lookup
    response_format = "json"  # or "text"

    def __init__(self, http: HttpClient, *, cache: Optional[QueryCache] = None,
                 stats: Optional[VocabStatsTracker] = None,
                 logger: Optional[logging.Logger] = None,
                 response_log: Any = None, max_results: int = 3,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.http = http
        self.cache = cache if cache is not None else QueryCache()
        self.stats = stats
        self.logger = logger or logging.getLogger(__name__)
        self.response_log = response_log
        self.max_results = max_results
        self._clock = clock

    # ---- to implement ----
    def _build_request(self, query: str) -> Request:
        raise NotImplementedError

    def _parse(self, payload: Any) -> list[Term]:
        raise NotImplementedError

    # ---- optional hooks ----
    def _fallback_requests(self, query: str) -> list[Request]:
        return []

    def _needs_fallback(self, terms: list[Term]) -> bool:
        return not terms

    def _accept_fallback(self, term: Term, query: str) -> bool:
        return True

    # ---- template ----
    def _fetch(self, request: Request) -> list[Term]:
        url, params = request
        payload = (self.http.get_text(url, params) if self.response_format == "text"
                   else self.http.get_json(url, params))
        return self._parse(payload)

    def search(self, query: str, subject: str = "") -> list[Term]:
        label = subject or query
        start = self._clock()
        cached = self.cache.get(self.name, query)
        if cached is not None:
            elapsed = self._clock() - start
            if self.stats:
                self.stats.record_cache_hit(self.name, label, len(cached))
            if self.response_log:
                self.response_log.record(self.name, label, query, cached,
                                         elapsed, cached=True)
            return cached
        try:
            terms = self._fetch(self._build_request(query))
            if self._needs_fallback(terms):
                for req in self._fallback_requests(query):
                    if len(self.dedupe(terms)) >= self.max_results:
                        break
                    try:
                        extra = self._fetch(req)
                    except VocabularyError as e:
                        self.logger.warning("%s fallback failed for %r: %s",
                                            self.name, query, e)
                        continue
                    terms = terms + [t for t in extra
                                     if self._accept_fallback(t, query)]
            result = self.dedupe(terms)[: self.max_results]
        except VocabularyError as e:
            elapsed = self._clock() - start
            if self.stats:
                self.stats.record_call(self.name, label, False, elapsed, 0)
            if self.response_log:
                self.response_log.record(self.name, label, query, [], elapsed,
                                         error=str(e))
            self.logger.warning("%s search failed for %r: %s", self.name, query, e)
            raise
        elapsed = self._clock() - start
        self.cache.put(self.name, query, result)
        if self.stats:
            self.stats.record_call(self.name, label, True, elapsed, len(result))
        if self.response_log:
            self.response_log.record(self.name, label, query, result, elapsed)
        self.logger.info("%s: %d terms for %r", self.name, len(result), query)
        return result

    @staticmethod
    def dedupe(terms: list[Term]) -> list[Term]:
        return MetadataStandard.dedupe(terms)
