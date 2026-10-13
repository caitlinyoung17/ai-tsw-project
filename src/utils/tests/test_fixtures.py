import json
from pathlib import Path

import openpyxl

META = Path(__file__).resolve().parents[2] / "test_documents/metadata/collection_metadata"


def test_sample_workflow_json():
    data = json.loads((META / "text_workflow.json").read_text(encoding="utf-8"))
    assert len(data) == 3
    assert "api_stats" in data[-1]
    assert all("analysis" in d for d in data[:-1])


def test_sample_workflow_xlsx():
    ws = openpyxl.load_workbook(META / "text_workflow.xlsx").active
    assert ws.max_row == 3
