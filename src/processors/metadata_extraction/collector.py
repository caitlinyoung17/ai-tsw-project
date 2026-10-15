"""Collect dissertation documents (.txt / .pdf) from a folder."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from utils.exceptions import ConfigError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    doc_id: str  # stable, unique within a run (the filename)
    filename: str
    path: str
    text: str


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str


@dataclass
class CollectionResult:
    documents: List[Document] = field(default_factory=list)
    skipped: List[SkippedFile] = field(default_factory=list)


def default_pdf_reader(path: str) -> str:
    from pdfminer.high_level import extract_text  # lazy: optional dependency
    return extract_text(path)


class DocumentCollector:
    def __init__(self, pdf_reader: Optional[Callable[[str], str]] = None) -> None:
        self.pdf_reader = pdf_reader or default_pdf_reader

    def collect(self, input_folder) -> CollectionResult:
        folder = Path(input_folder)
        if not folder.is_dir():
            raise ConfigError(f"Input folder does not exist: {folder}", path=str(folder))
        result = CollectionResult()
        for p in sorted(folder.iterdir()):
            suffix = p.suffix.lower()
            if suffix not in (".txt", ".pdf") or not p.is_file():
                continue
            logger.info("Reading %s", p.name)
            try:
                if suffix == ".txt":
                    text = p.read_text(encoding="utf-8")
                else:
                    text = self.pdf_reader(str(p))
            except Exception as e:  # unreadable input is reported, not fatal
                logger.error("Cannot read %s: %s", p, e)
                result.skipped.append(SkippedFile(str(p), f"{type(e).__name__}: {e}"))
                continue
            result.documents.append(Document(p.name, p.name, str(p), text or ""))
        return result
