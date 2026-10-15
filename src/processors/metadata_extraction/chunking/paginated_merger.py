"""Substep 3: split, orchestrate and merge."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from api.llm_core.types import Usage
from utils.exceptions import LLMError
from utils.text import dedupe_preserve_order

from .chunk_processor import ChunkProcessor, ChunkResult, _add
from .config import ChunkingConfig

logger = logging.getLogger(__name__)

_BOUNDARY = re.compile(r"(?:[.!?][\"')\]]*\s)|\n\n")


@dataclass(frozen=True)
class Split:
    front_matter: str
    chunks: List[str]


def _cut(text: str, start: int, end: int) -> int:
    """Largest sentence boundary in the back half of [start, end]; else end."""
    if end >= len(text):
        return len(text)
    lo = start + (end - start) // 2
    last = -1
    for m in _BOUNDARY.finditer(text, lo, end):
        last = m.end()
    return last if last > 0 else end


def split_document(text: str, config: ChunkingConfig) -> Split:
    fm_end = _cut(text, 0, min(config.front_matter_chars, len(text)))
    front, body = text[:fm_end], text[fm_end:]
    chunks: List[str] = []
    start = 0
    while start < len(body):
        end = _cut(body, start, start + config.chunk_size)
        chunks.append(body[start:end])
        if end >= len(body):
            break
        start = max(end - config.overlap, start + 1)
    return Split(front, chunks)


@dataclass(frozen=True)
class MergedMetadata:
    metadata: dict
    usage: Usage
    raw: str
    warnings: Tuple[str, ...] = ()
    content_warning: Dict = field(default_factory=lambda: {"flag": False, "reasons": []})


def _is_none(s: str) -> bool:
    return not s or s.strip().rstrip(".").lower() == "none"


def render_content_warning(flag: bool, reasons: Sequence[str]) -> str:
    if not flag or not reasons:
        return "None"
    text = "; ".join(r.strip().rstrip(".") for r in reasons)
    return text[0].upper() + text[1:] + "."


def merge(front: dict, chunk_results: Sequence[ChunkResult]) -> Tuple[dict, dict]:
    merged = dict(front)
    merged["subjects"] = dedupe_preserve_order(
        s for c in chunk_results for s in c.subjects)
    merged["namedEntities"] = dedupe_preserve_order(
        s for c in chunk_results for s in c.named_entities)
    merged["geographicEntities"] = dedupe_preserve_order(
        s for c in chunk_results for s in c.geographic_entities)
    reasons = dedupe_preserve_order(
        (c.content_warning.strip().rstrip(".") for c in chunk_results
         if not _is_none(c.content_warning)))
    cw = {"flag": bool(reasons), "reasons": reasons}
    merged["contentWarning"] = render_content_warning(cw["flag"], reasons)
    return merged, cw


class PaginatedProcessor:
    def __init__(self, chunk_processor: ChunkProcessor, config: ChunkingConfig) -> None:
        self.cp = chunk_processor
        self.config = config

    def run(self, text: str, doc_id: str = "") -> MergedMetadata:
        cfg = self.config
        split = split_document(text, cfg)
        logger.info("%s: chunking: front matter + %d chunk(s)", doc_id, len(split.chunks))
        usage = Usage()
        raws: List[str] = []
        warnings: List[str] = []

        logger.info("%s: chunking sub-step: front matter", doc_id)
        front = self.cp.process_front_matter(split.front_matter)  # failure propagates
        usage = _add(usage, front.usage)
        raws.append(front.raw)
        front_meta = dict(front.metadata)

        if (not front.abstract_complete and cfg.abstract_scan_max_chunks > 0
                and split.chunks):
            parts = [front_meta.get("abstract", "")] if front_meta.get("abstract") else []
            done = False
            for i, chunk in enumerate(split.chunks[:cfg.abstract_scan_max_chunks]):
                logger.info("%s: abstract scan chunk %d/%d", doc_id, i + 1,
                            min(len(split.chunks), cfg.abstract_scan_max_chunks))
                try:
                    r = self.cp.process_abstract_chunk(chunk)
                except LLMError as e:
                    warnings.append(f"abstract scan failed on chunk {i}: {e}")
                    break
                usage = _add(usage, r.usage)
                raws.append(r.raw)
                if r.abstract:
                    parts.append(r.abstract)
                if r.complete:
                    done = True
                    break
            if parts:
                front_meta["abstract"] = " ".join(p.strip() for p in parts if p.strip())
            if not done:
                msg = (f"abstract not confirmed complete after "
                       f"{cfg.abstract_scan_max_chunks} chunk(s)")
                logger.warning("%s: %s", doc_id, msg)
                warnings.append(msg)

        results: List[ChunkResult] = []
        if cfg.full_text_scan:
            chunks = split.chunks
            if cfg.max_chunks is not None:
                chunks = chunks[:cfg.max_chunks]
            total = len(chunks)
            for i, chunk in enumerate(chunks):
                logger.info("%s: scanning chunk %d/%d", doc_id, i + 1, total)
                try:
                    r = self.cp.process_chunk(chunk, i, total)
                except LLMError as e:
                    msg = f"chunk {i + 1}/{total} failed: {e}"
                    logger.warning("%s: %s", doc_id, msg)
                    warnings.append(msg)
                    continue
                usage = _add(usage, r.usage)
                raws.append(r.raw)
                results.append(r)

        logger.info("%s: merging front matter and %d chunk result(s)", doc_id, len(results))
        metadata, cw = merge(front_meta, results)
        return MergedMetadata(metadata, usage, "\n---\n".join(raws),
                              tuple(warnings), cw)
