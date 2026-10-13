import json

import pytest

from api.llm_core.testing import FakeProvider
from processors.batch_cleanup import (BatchCleanupProcessor, CleanupStatus,
                                      FailureReason, ItemReprocessor,
                                      detect_failed_items)
from processors.batch_cleanup.detection import (has_extreme_repetition,
                                                is_completely_broken_json,
                                                max_char_dominance)
from processors.metadata_extraction import MetadataExtractor, WorkflowWriter
from processors.metadata_extraction.collector import Document
from processors.metadata_extraction.results import Succeeded, summarize, ExtractionResult
from api.llm_core.types import Usage
from utils import schema
from utils.exceptions import EmptyDocumentError, LLMResponseError, WorkflowFilesNotFound
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

GOOD = json.dumps({"title": "T", "abstract": "A", "creator": "C", "subjects": ["a"],
                   "namedEntities": [], "geographicEntities": []})


def good_item(name="a.txt"):
    a = schema.to_snake(schema.empty_metadata())
    a.update(title="T", abstract="A", raw_response=GOOD)
    return {"filename": name, "file_path": f"/x/{name}", "analysis": a}


def bad_item(name="b.txt", raw=""):
    a = schema.to_snake(schema.empty_metadata())
    a["raw_response"] = raw
    return {"filename": name, "file_path": f"/x/{name}", "analysis": a}


def test_detection_primitives():
    assert has_extreme_repetition("word " * 600)
    assert has_extreme_repetition("." * 3000)
    assert not has_extreme_repetition("a normal sentence " * 10)
    assert is_completely_broken_json("just some text no braces")
    assert is_completely_broken_json('{"a": ' + "{" * 20)
    assert not is_completely_broken_json(GOOD)
    assert max_char_dominance("aaaaab") > 0.8


def test_detect_reasons():
    items = [good_item(), bad_item(raw=""), bad_item(raw="Processing error: x"),
             bad_item(raw="no json here at all"), bad_item(raw="w " * 600 + "{}"),
             {"filename": "z"}]
    items[3]["analysis"]["title"] = "T"
    reasons = [f.reason for f in detect_failed_items(items)]
    assert reasons == [FailureReason.EMPTY_RESPONSE, FailureReason.EXPLICIT_ERROR,
                       FailureReason.BROKEN_JSON, FailureReason.REPETITION,
                       FailureReason.NO_ANALYSIS]


def test_missing_fields_and_healthy():
    it = good_item()
    del it["analysis"]["publisher"]
    assert detect_failed_items([good_item()]) == []
    assert detect_failed_items([it])[0].reason == FailureReason.MISSING_FIELDS


def reproc(provider, loader=lambda p: "source text", **kw):
    return ItemReprocessor(MetadataExtractor(provider, "fake-model"), loader,
                           sleep=lambda s: None, **kw)


def test_reprocessor_success_failure_missing():
    r = reproc(FakeProvider([GOOD]))
    assert r.reprocess(bad_item()).metadata["title"] == "T"
    p = FakeProvider([LLMResponseError("x")] * 3)
    with pytest.raises(LLMResponseError):
        reproc(p).reprocess(bad_item())
    assert len(p.requests) == 3

    def missing(path):
        raise FileNotFoundError(path)
    p2 = FakeProvider([GOOD])
    with pytest.raises(EmptyDocumentError):
        reproc(p2, missing).reprocess(bad_item())
    assert p2.requests == []


def make_run(tmp_path, items, mode="BATCH"):
    rf = RunFolder(tmp_path / "run")
    docs = [Document(i["filename"], i["filename"], i["file_path"], "t") for i in items]
    outcomes = {d.doc_id: Succeeded(ExtractionResult(
        d.doc_id, schema.empty_metadata(), Usage(1, 1), "")) for d in docs}
    summ = summarize(outcomes, mode)
    w = WorkflowWriter(WorkflowStore(rf))
    w.write(docs, outcomes, summ)
    store = WorkflowStore(rf)
    wf = store.load()
    wf.items = items
    store.save(wf)
    return rf


class CountingStore(WorkflowStore):
    wb_saves = 0

    def save_workbook(self, wb):
        CountingStore.wb_saves += 1
        super().save_workbook(wb)


def test_processor_mixed(tmp_path):
    rf = make_run(tmp_path, [good_item("a.txt"), bad_item("b.txt"), bad_item("c.txt")])
    loader = lambda p: "" if p.endswith("c.txt") else "text"
    proc = BatchCleanupProcessor(reproc(FakeProvider([GOOD]), loader))
    CountingStore.wb_saves = 0
    s = proc.run(rf, CountingStore(rf))
    assert (s.status, s.n_fixed, s.n_still_failed) == (CleanupStatus.CLEANED, 1, 1)
    assert CountingStore.wb_saves == 1
    wf = WorkflowStore(rf).load()
    assert wf.items[1]["analysis"]["title"] == "T"
    assert wf.api_stats["processing_mode"] == "BATCH"
    wb = WorkflowStore(rf).open_workbook()
    assert wb["Analysis"].cell(row=3, column=2).value == "T"
    assert (rf.metadata_dir / "step1_5_cleanup_report.txt").read_text().startswith("TSW")


def test_processor_noop_states(tmp_path):
    rf = make_run(tmp_path, [bad_item()], mode="INDIVIDUAL")
    p = BatchCleanupProcessor(reproc(FakeProvider([])))
    assert p.run(rf).status == CleanupStatus.NOT_A_BATCH_RUN
    rf2 = make_run(tmp_path / "2", [good_item()])
    assert p.run(rf2).status == CleanupStatus.NOTHING_TO_CLEAN


def test_processor_load_error_raises(tmp_path):
    p = BatchCleanupProcessor(reproc(FakeProvider([])))
    with pytest.raises(WorkflowFilesNotFound):
        p.run(RunFolder(tmp_path / "none"))
