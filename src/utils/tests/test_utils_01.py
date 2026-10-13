import json
from datetime import datetime

import openpyxl
import pytest

from utils import schema
from utils.exceptions import WorkflowFilesNotFound, WorkflowFormatError
from utils.run_folder import RunFolder
from utils.subjects import parse_subject_list
from utils.text import (dedupe_preserve_order, normalize_for_comparison,
                        normalize_label_for_matching, preprocess_ocr_text)
from utils.workflow_store import Workflow, WorkflowStore


def test_run_folder_create_and_paths(tmp_path):
    rf = RunFolder.create(tmp_path, lambda: datetime(2024, 1, 2, 3, 4, 5))
    assert rf.root.name == "Dissertation_Metadata_Created_2024-01-02_Time_03-04-05"
    assert rf.metadata_dir.is_dir() and rf.logs_dir.is_dir()
    assert rf.json_path.name == "text_workflow.json"
    assert rf.xlsx_path.name == "text_workflow.xlsx"
    with pytest.raises(WorkflowFilesNotFound):
        rf.require_workflow_files()
    rf.json_path.write_text("[]")
    rf.xlsx_path.write_text("x")
    rf.require_workflow_files()


def test_newest(tmp_path):
    with pytest.raises(WorkflowFilesNotFound):
        RunFolder.newest(tmp_path / "nope")
    with pytest.raises(WorkflowFilesNotFound):
        RunFolder.newest(tmp_path)
    import os
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    os.utime(a, (1, 1))
    assert RunFolder.newest(tmp_path).root == b


def test_store_roundtrip_and_errors(tmp_path):
    rf = RunFolder.create(tmp_path)
    store = WorkflowStore(rf)
    with pytest.raises(WorkflowFilesNotFound):
        store.load()
    wf = Workflow(items=[{"analysis": {"title": "é"}}], api_stats={"n": 1})
    store.save(wf)
    raw = json.loads(rf.json_path.read_text(encoding="utf-8"))
    assert raw[-1] == {"api_stats": {"n": 1}} and "é" in rf.json_path.read_text(encoding="utf-8")
    assert store.load() == wf
    rf.json_path.write_text("{bad")
    with pytest.raises(WorkflowFormatError):
        store.load()


def test_atomic_save_failure_keeps_original(tmp_path):
    rf = RunFolder.create(tmp_path)
    store = WorkflowStore(rf)
    store.save(Workflow(items=[{"a": 1}]))
    with pytest.raises(TypeError):
        store.save(Workflow(items=[{"a": object()}]))
    assert store.load().items == [{"a": 1}]
    assert [p.name for p in rf.metadata_dir.iterdir()] == ["text_workflow.json"]


def test_excel_headers(tmp_path):
    rf = RunFolder.create(tmp_path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Title", "Subject Terms (LLM)"])
    wb.save(rf.xlsx_path)
    store = WorkflowStore(rf)
    wb2 = store.open_workbook()
    assert store.column_index(wb2.active, "subject terms") == 2
    with pytest.raises(WorkflowFormatError):
        store.column_index(wb2.active, "missing")
    store.save_workbook(wb2)


def test_empty_metadata_keys_and_snake():
    m = schema.empty_metadata()
    assert m is not schema.empty_metadata()
    assert m["subjects"] is not schema.empty_metadata()["subjects"]
    assert {"namedEntities", "geographicEntities", "contentWarning"} <= set(m)
    assert schema.to_camel(schema.to_snake(m)) == m
    assert "geographic_entities" in schema.to_snake(m)


def test_text():
    assert preprocess_ocr_text("a b  c\n\n\n\nd") == "a b c\n\nd"
    assert normalize_for_comparison("  Café, Déjà-Vu!! 12 ") == "cafe dejavu"
    assert normalize_label_for_matching("  Foo   Bar. ") == "foo bar"
    assert dedupe_preserve_order(["B", "a", "b.", "A"]) == ["B", "a"]


@pytest.mark.parametrize("v,exp", [
    (["a", " b ", ""], ["a", "b"]), ("a, b;c", ["a", "b", "c"]),
    ("", []), (None, []), ("  ", []), ([], []),
])
def test_subjects(v, exp):
    assert parse_subject_list(v) == exp
