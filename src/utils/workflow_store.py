"""Load/save text_workflow.json (items + api_stats trailer) and xlsx helpers."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

import openpyxl

from utils.exceptions import WorkflowFilesNotFound, WorkflowFormatError
from utils.run_folder import RunFolder


@dataclass
class Workflow:
    items: list[dict] = field(default_factory=list)
    api_stats: dict = field(default_factory=dict)


class WorkflowStore:
    def __init__(self, run_folder: RunFolder) -> None:
        self.run_folder = run_folder

    def load(self) -> Workflow:
        path = self.run_folder.json_path
        if not path.exists():
            raise WorkflowFilesNotFound(f"Missing {path}", path=str(path))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise WorkflowFormatError(f"Malformed JSON in {path}",
                                      path=str(path), cause=e)
        if not isinstance(data, list):
            raise WorkflowFormatError("Workflow JSON must be a list",
                                      path=str(path))
        # The single place the api_stats trailer is split off.
        if data and isinstance(data[-1], dict) and "api_stats" in data[-1]:
            return Workflow(items=data[:-1], api_stats=data[-1]["api_stats"])
        return Workflow(items=list(data), api_stats={})

    def save(self, workflow: Workflow) -> None:
        path = self.run_folder.json_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # The single place the trailer is re-attached.
        data: list[Any] = list(workflow.items)
        if workflow.api_stats:
            data.append({"api_stats": workflow.api_stats})
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---- Excel ----
    def open_workbook(self) -> openpyxl.Workbook:
        path = self.run_folder.xlsx_path
        if not path.exists():
            raise WorkflowFilesNotFound(f"Missing {path}", path=str(path))
        try:
            return openpyxl.load_workbook(path)
        except Exception as e:
            raise WorkflowFormatError(f"Cannot open {path}",
                                      path=str(path), cause=e)

    @staticmethod
    def column_index(sheet, header_substring: str) -> int:
        """1-based column whose header contains header_substring (case-insensitive)."""
        needle = header_substring.lower()
        for cell in sheet[1]:
            if cell.value is not None and needle in str(cell.value).lower():
                return cell.column
        raise WorkflowFormatError(
            f"Header containing '{header_substring}' not found in sheet "
            f"'{sheet.title}'")

    def save_workbook(self, wb: openpyxl.Workbook) -> None:
        wb.save(self.run_folder.xlsx_path)
