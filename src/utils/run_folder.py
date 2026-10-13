"""Run-folder path handling. No I/O at import time."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Union

from utils.exceptions import WorkflowFilesNotFound

PREFIX = "Dissertation_Metadata_Created_"


class RunFolder:
    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)

    @property
    def metadata_dir(self) -> Path:
        return self.root / "metadata" / "collection_metadata"

    @property
    def json_path(self) -> Path:
        return self.metadata_dir / "text_workflow.json"

    @property
    def xlsx_path(self) -> Path:
        return self.metadata_dir / "text_workflow.xlsx"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def vocab_report_path(self) -> Path:
        return self.metadata_dir / "vocabulary_mapping_report.txt"

    @property
    def selection_report_path(self) -> Path:
        return self.metadata_dir / "vocabulary_selection_report.txt"

    @classmethod
    def create(cls, output_root: Union[str, Path],
               clock: Callable[[], datetime] = datetime.now) -> "RunFolder":
        now = clock()
        name = f"{PREFIX}{now:%Y-%m-%d}_Time_{now:%H-%M-%S}"
        folder = cls(Path(output_root) / name)
        folder.ensure_dirs()
        return folder

    @classmethod
    def newest(cls, output_root: Union[str, Path]) -> "RunFolder":
        root = Path(output_root)
        if not root.is_dir():
            raise WorkflowFilesNotFound(
                f"Output root does not exist: {root}", path=str(root))
        dirs = [d for d in root.iterdir() if d.is_dir()]
        if not dirs:
            raise WorkflowFilesNotFound(
                f"No run folders in {root}", path=str(root))
        return cls(max(dirs, key=lambda d: d.stat().st_mtime))

    def ensure_dirs(self) -> None:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def require_workflow_files(self) -> None:
        missing = [p for p in (self.json_path, self.xlsx_path) if not p.exists()]
        if missing:
            raise WorkflowFilesNotFound(
                "Missing workflow files: " + ", ".join(p.name for p in missing),
                path=str(self.metadata_dir))
