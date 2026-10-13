import json
from types import SimpleNamespace

import pytest

from api.llm_core.testing import FakeProvider
from metadata_standard import Term
from pipeline import Pipeline, PipelineConfig, PipelineContext, StepSummary, default_steps
from pipeline.cli import build_parser, exit_src_for, main, parse_steps, run_cli
from pipeline.report import FAILED, NOT_RUN, OK
from processors.base import ProcessorStep
from processors.vocab_enhancement.lookup import VocabLookupService
from utils.exceptions import (ConfigError, LLMResponseError, StepFailedError,
                              WorkflowFilesNotFound)
from utils.run_folder import RunFolder

GOOD = json.dumps({"title": "T", "creator": "C", "subjects": ["rivers", "maps"],
                   "namedEntities": ["Austin Texas"], "geographicEntities": ["Texas"]})


class StubClient:
    def __init__(self, name):
        self.name = self.group = name

    def search(self, q, subject=""):
        return [Term(f"{q} term", f"http://x/{self.name}/{q}", self.name)]


def factory(rf):
    return VocabLookupService([StubClient("LCSH"), StubClient("FAST")],
                              [StubClient("FAST Geographic")])


def make_ctx(responses, rf=None, tmp_path=None, **cfg):
    config = PipelineConfig(output_root=tmp_path / "out", model="fake-model",
                            use_batch=False, **cfg)
    return PipelineContext(rf, FakeProvider(responses), factory, config, sleep=lambda s: None)


class Rec(ProcessorStep):
    def __init__(self, name, deps=(), fail=None):
        self.name, self.depends_on, self.fail, self.ran = name, deps, fail, False

    def run(self, ctx):
        self.ran = True
        if self.fail:
            raise self.fail
        return StepSummary(OK)


def _ctx_stub(tmp_path, **cfg):
    return make_ctx([], RunFolder(tmp_path), tmp_path, **cfg)


def test_order_start_stop(tmp_path):
    steps = [Rec("a"), Rec("b"), Rec("c")]
    r = Pipeline(steps).run(_ctx_stub(tmp_path), start_at="b", stop_after="b")
    assert [s.step for s in r.steps] == ["b"] and not steps[0].ran


def test_failure_stops_chain(tmp_path):
    steps = [Rec("a"), Rec("b", fail=LLMResponseError("x")), Rec("c")]
    r = Pipeline(steps).run(_ctx_stub(tmp_path))
    assert r.failed.step == "b" and not steps[2].ran
    assert isinstance(r.failed.error, StepFailedError) and exit_src_for(r.failed.error) == 4


def test_keep_going_skips_dependents_only(tmp_path):
    steps = [Rec("a", fail=LLMResponseError("x")), Rec("b", ("a",)), Rec("c")]
    r = Pipeline(steps).run(_ctx_stub(tmp_path, keep_going=True))
    assert [s.status for s in r.steps] == [FAILED, NOT_RUN, OK] and steps[2].ran


def test_missing_folder_exit_3(tmp_path):
    args = build_parser().parse_args(["--folder", str(tmp_path / "nope")])
    assert run_cli(args, make_ctx([], RunFolder(tmp_path / "nope"), tmp_path)) == 3


def test_cli_parsing_and_exit_srcs(tmp_path):
    a = build_parser().parse_args(["--input", "d", "--no-batch", "--steps", "1,2",
                                   "--full-text-scan", "--chunk-size", "100"])
    assert a.batch is False and a.full_text_scan and a.chunk_size == 100
    assert parse_steps("1,2") == ["1", "2"]
    with pytest.raises(ConfigError):
        parse_steps("9")
    assert exit_src_for(ConfigError("x")) == 2
    assert exit_src_for(WorkflowFilesNotFound("x")) == 3
    assert exit_src_for(StepFailedError("x", step="1", cause=LLMResponseError("y"))) == 4
    assert exit_src_for(StepFailedError("x", step="1", cause=ConfigError("y"))) == 2
    assert main(["--steps", "9"]) == 2


def test_full_run_and_resume(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("A dissertation about rivers in Texas.")
    sel = json.dumps({"selected_terms": [{"label": "rivers term"}]})
    ctx = make_ctx([GOOD, sel], tmp_path=tmp_path)
    ctx.config.input_folder = docs
    report = Pipeline(default_steps()).run(ctx)
    assert report.ok, report.render()
    st = {s.step: s.status for s in report.steps}
    assert st["1.5"] == "skipped" and st["4"] == "ok"
    rf = ctx.run_folder
    data = json.loads(rf.json_path.read_text())
    analysis = data[0]["analysis"]
    assert analysis["vocabulary_search_results"]
    assert "final_selected_terms" in json.dumps(data)
    assert (rf.metadata_dir / "entity_authority_file.json").exists() or \
        list(rf.metadata_dir.glob("*authority*.json"))
    # resume: only step 4 against the existing folder
    ctx2 = make_ctx([], RunFolder(rf.root), tmp_path)
    r2 = Pipeline(default_steps()).run(ctx2, only=["4"])
    assert [s.step for s in r2.steps] == ["4"] and r2.ok
    assert ctx2.provider.requests == []
