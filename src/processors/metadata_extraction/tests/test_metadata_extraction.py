import json

import pytest

from api.llm_core.testing import FakeProvider
from api.llm_core.types import BatchHandle, BatchOutcome, CompletionResult, Usage
from utils.exceptions import (BatchError, EmptyDocumentError, LLMResponseError,
                              WorkflowFilesNotFound)
from utils.run_folder import RunFolder
from utils.workflow_store import WorkflowStore

from processors.metadata_extraction import (BatchExtractor, Document,
                                            DocumentCollector, Failed,
                                            MetadataExtractionProcessor,
                                            MetadataExtractor, Succeeded,
                                            WorkflowWriter)
from processors.metadata_extraction.results import summarize

GOOD = json.dumps({"title": "T", "creator": "C", "subjects": ["a", "b"],
                   "namedEntities": ["Austin Texas"], "geographicEntities": []})


def doc(i, text="some text"):
    return Document(f"{i}.txt", f"{i}.txt", f"/x/{i}.txt", text)


def ext(provider):
    return MetadataExtractor(provider, "fake-model")


class FakeBatchProvider(FakeProvider):
    def __init__(self, fail=False, responses=()):
        super().__init__(list(responses))
        self.fail = fail
        self.submitted = []

    supports_batch = True

    def submit_batch(self, requests):
        if self.fail:
            raise BatchError("boom")
        self.submitted = requests
        return BatchHandle("b1")

    def collect_batch(self, handle, timeout=None, poll_interval=60.0, sleep=None):
        return {i.custom_id: BatchOutcome(i.custom_id, CompletionResult(
            GOOD, Usage(3, 2), "m")) for i in self.submitted}


# ---- collector
def test_collector(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.pdf").write_bytes(b"x")
    (tmp_path / "c.pdf").write_bytes(b"x")
    (tmp_path / "skip.md").write_text("no")

    def reader(p):
        if p.endswith("c.pdf"):
            raise RuntimeError("bad pdf")
        return "pdf text"
    r = DocumentCollector(reader).collect(tmp_path)
    assert [d.doc_id for d in r.documents] == ["a.txt", "b.pdf"]
    assert r.documents[1].text == "pdf text"
    assert len(r.skipped) == 1 and "bad pdf" in r.skipped[0].reason


# ---- extractor
def test_extract_good_and_fenced():
    p = FakeProvider([GOOD, "```json\n" + GOOD + "\n```"])
    e = ext(p)
    r = e.extract(doc(1))
    assert r.metadata["title"] == "T" and r.usage == Usage(10, 5)
    assert e.extract(doc(2)).metadata["creator"] == "C"
    assert p.requests[0].max_tokens == 8000


def test_extract_empty_text():
    with pytest.raises(EmptyDocumentError):
        ext(FakeProvider([])).extract(doc(1, "  \n "))


def test_extract_bad_responses():
    for bad in ["", '{"title": "unterminated']:
        with pytest.raises(LLMResponseError):
            ext(FakeProvider([bad])).extract(doc(1))


# ---- batch
def test_batch_empty_doc_does_not_shift_ids():
    p = FakeBatchProvider()
    out = BatchExtractor(p, ext(p)).run([doc("A"), doc("B", ""), doc("C")])
    assert [i.custom_id for i in p.submitted] == ["A.txt", "C.txt"]
    assert isinstance(out["A.txt"], Succeeded) and isinstance(out["C.txt"], Succeeded)
    assert isinstance(out["B.txt"], Failed)
    assert isinstance(out["B.txt"].error, EmptyDocumentError)
    assert list(out) == ["A.txt", "B.txt", "C.txt"]


def test_batch_failure_raise_and_individual():
    p = FakeBatchProvider(fail=True)
    with pytest.raises(BatchError):
        BatchExtractor(p, ext(p)).run([doc(1)])
    p = FakeBatchProvider(fail=True, responses=[GOOD])
    out = BatchExtractor(p, ext(p), on_batch_failure="individual").run([doc(1)])
    assert isinstance(out["1.txt"], Succeeded)


# ---- writer
def _outcomes():
    d1, d2 = doc(1), doc(2)
    res = ext(FakeProvider([GOOD])).extract(d1)
    return [d1, d2], {d1.doc_id: Succeeded(res),
                      d2.doc_id: Failed(d2.doc_id, LLMResponseError("bad"))}


def test_writer(tmp_path):
    rf = RunFolder(tmp_path / "run")
    docs, outcomes = _outcomes()
    summary = summarize(outcomes, "INDIVIDUAL")
    store = WorkflowStore(rf)
    WorkflowWriter(store).write(docs, outcomes, summary)
    wf = store.load()
    assert len(wf.items) == 2
    assert wf.items[0]["analysis"]["named_entities"] == ["Austin Texas"]
    assert wf.items[0]["analysis"]["raw_response"] == GOOD
    assert wf.items[1]["analysis"]["title"] == ""
    assert wf.api_stats["processing_mode"] == "INDIVIDUAL"
    wb = store.open_workbook()
    assert wb.sheetnames == ["Analysis", "Raw Responses", "Issues", "API Stats"]
    assert wb["Analysis"]["A1"].value == "Filename"
    assert wb["Analysis"].max_row == 3
    assert wb["Issues"]["A2"].value == "2.txt"


# ---- processor end to end
def test_processor_individual(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.txt").write_text("alpha")
    (tmp_path / "in" / "b.txt").write_text("   ")
    p = FakeProvider([GOOD])
    sleeps = []
    proc = MetadataExtractionProcessor(p, ext(p), sleep=sleeps.append)
    rf = RunFolder(tmp_path / "run")
    s = proc.run(tmp_path / "in", rf)
    assert (s.total, s.succeeded, s.failed, s.mode) == (2, 1, 1, "INDIVIDUAL")
    assert sleeps == [1.0]
    assert len(WorkflowStore(rf).load().items) == 2


def test_processor_batch_same_output_as_individual(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.txt").write_text("alpha")
    bp = FakeBatchProvider()
    rf = RunFolder(tmp_path / "run")
    s = MetadataExtractionProcessor(bp, ext(bp), use_batch=True).run(tmp_path / "in", rf)
    assert s.mode == "BATCH" and s.succeeded == 1
    ip = FakeProvider([GOOD])
    rf2 = RunFolder(tmp_path / "run2")
    MetadataExtractionProcessor(ip, ext(ip), sleep=lambda s: None).run(tmp_path / "in", rf2)
    a = WorkflowStore(rf).load().items
    b = WorkflowStore(rf2).load().items
    assert a == b


def test_processor_real_samples(tmp_path):
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "test_documents" / "dissertations"
    n = len(list(src.glob("*.txt")))
    p = FakeProvider([GOOD] * n)
    s = MetadataExtractionProcessor(p, ext(p), sleep=lambda s: None).run(
        src, RunFolder(tmp_path / "r"))
    assert s.succeeded == n >= 1
