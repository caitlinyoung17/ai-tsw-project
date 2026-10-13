"""Apply reprocessed metadata to the workflow JSON and workbook (saved once)."""
from __future__ import annotations

from typing import Dict

from utils import schema
from utils.workflow_store import Workflow, WorkflowStore

from processors.metadata_extraction.results import ExtractionResult
from processors.metadata_extraction.writer import ANALYSIS_HEADERS, analysis_row


class CleanupWriter:
    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    def apply(self, workflow: Workflow, fixes: Dict[int, ExtractionResult]) -> None:
        """Update items in `workflow` in place, then save JSON and workbook once."""
        if not fixes:
            return
        wb = self.store.open_workbook()
        analysis_ws = wb["Analysis"] if "Analysis" in wb.sheetnames else wb.active
        raw_ws = wb["Raw Responses"] if "Raw Responses" in wb.sheetnames else None
        fn_col = self.store.column_index(analysis_ws, "Filename")
        rows = {str(analysis_ws.cell(row=r, column=fn_col).value): r
                for r in range(2, analysis_ws.max_row + 1)}
        cols = {h: self.store.column_index(analysis_ws, h) for h in ANALYSIS_HEADERS}
        raw_rows = {}
        if raw_ws is not None:
            rc = self.store.column_index(raw_ws, "Filename")
            ac = self.store.column_index(raw_ws, "API Response")
            raw_rows = {str(raw_ws.cell(row=r, column=rc).value): (r, ac)
                        for r in range(2, raw_ws.max_row + 1)}
        for index, result in fixes.items():
            item = workflow.items[index]
            analysis = schema.to_snake(result.metadata)
            analysis["raw_response"] = result.raw
            item["analysis"] = analysis
            name = item.get("filename", "")
            row = rows.get(name)
            if row is not None:
                for header, value in zip(ANALYSIS_HEADERS,
                                         analysis_row(name, result.metadata)):
                    analysis_ws.cell(row=row, column=cols[header]).value = value
            if name in raw_rows:
                r, c = raw_rows[name]
                raw_ws.cell(row=r, column=c).value = result.raw
        self.store.save(workflow)
        self.store.save_workbook(wb)
