"""In-memory query cache keyed by (service, query), optionally persisted."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from metadata_standard import Term


class QueryCache:
    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._data: dict[tuple[str, str], list[Term]] = {}
        self.path = Path(path) if path else None
        if self.path and self.path.exists():
            self._load()

    def get(self, service: str, query: str) -> Optional[list[Term]]:
        hit = self._data.get((service, query))
        return None if hit is None else list(hit)

    def put(self, service: str, query: str, terms: list[Term]) -> None:
        self._data[(service, query)] = list(terms)

    def __len__(self) -> int:
        return len(self._data)

    def save(self) -> None:
        if not self.path:
            return
        payload = [{"service": s, "query": q, "terms": [t.to_dict() for t in ts]}
                   for (s, q), ts in self._data.items()]
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        try:
            for e in json.loads(self.path.read_text(encoding="utf-8")):
                self._data[(e["service"], e["query"])] = [
                    Term.from_dict(t) for t in e["terms"]]
        except (OSError, ValueError, KeyError, TypeError):
            self._data.clear()  # unreadable cache file: start empty
