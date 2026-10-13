"""The only module that talks to the network (``requests`` lives here)."""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import requests

from utils.exceptions import VocabHttpError, VocabParseError

USER_AGENT = "Python-Vocab-Term-Finder/1.0 (Educational/Research Use)"


class HttpClient:
    def __init__(self, session: Optional[Any] = None, timeout: float = 10,
                 user_agent: str = USER_AGENT,
                 sleep: Callable[[float], None] = time.sleep,
                 delay: float = 0.5) -> None:
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}
        self.sleep = sleep
        self.delay = delay

    def _get(self, url: str, params: Optional[dict]) -> Any:
        try:
            resp = self.session.get(url, params=params, headers=self.headers,
                                    timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            status = getattr(getattr(e, "response", None), "status_src", None)
            raise VocabHttpError(
                f"GET {url} failed (status={status}): {e}", path=url, cause=e)
        finally:
            # Politeness delay after every real request, via injected sleep.
            self.sleep(self.delay)
        return resp

    def get_json(self, url: str, params: Optional[dict] = None) -> Any:
        resp = self._get(url, params)
        try:
            return resp.json()
        except ValueError as e:
            raise VocabParseError(f"Invalid JSON from {url}", path=url, cause=e)

    def get_text(self, url: str, params: Optional[dict] = None) -> str:
        return self._get(url, params).text
