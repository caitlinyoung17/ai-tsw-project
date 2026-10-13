import importlib.util
import json
import time

import pytest

from processors.entity_authority.authority_file import (
    build_authority_file, generate_statistics, render_report)
from processors.entity_authority.clustering import (
    build_entities, cluster_entities, default_similarity)
from processors.entity_authority.entities import (
    classify_entity_fallback, normalize_entity_name, parse_typed_entity)
from processors.entity_authority.extraction import extract_all_entities
from processors.entity_authority.processor import EntityAuthorityProcessor
from utils.exceptions import ConfigError, WorkflowFilesNotFound
from utils.run_folder import RunFolder

HAS_RF = importlib.util.find_spec("rapidfuzz") is not None


def exact_or_prefix(a, b):
    return 100 if a == b or a.startswith(b) or b.startswith(a) else 0


def test_parse_typed():
    assert parse_typed_entity("John F. Staub (Architect)") == ("John F. Staub", "architect")
    assert parse_typed_entity("Atlanta, Ga. (location)") == ("Atlanta, Ga.", "location")


@pytest.mark.parametrize("s,t", [
    ("University of Texas", "institution"), ("Acme Inc.", "organization"),
    ("Water Study", "project"), ("E. R. Denmark", "person"),
    ("Laurence H. Fowler", "person"), ("the county", "location"),
    ("zebra", "unknown")])
def test_classify(s, t):
    assert classify_entity_fallback(s) == t


def test_normalize():
    assert normalize_entity_name("Acme Co.") == "Acme Co."  # legacy quirk: no \\b after trailing dot
    assert normalize_entity_name("  A  &  B Co.x Inc.y ") == "A and B Companyx Incorporatedy"


def test_cluster_counts_and_canonical():
    ents = cluster_entities(["Smith", "Smith", "Smithe", "Jones"], exact_or_prefix, 50)
    by = {e.name: e for e in ents}
    assert set(by) == {"Smith", "Jones"}
    assert by["Smith"].count == 3 and by["Smith"].variants == ["Smith", "Smithe"]


def test_cluster_performance():
    raw = [f"Entity number {i % 500:04d}" for i in range(5000)]
    sim, _ = default_similarity()
    t = time.time()
    ents = cluster_entities(raw, sim, 99)
    assert len(ents) == 500 and time.time() - t < 10
    assert all(e.count == 10 for e in ents)


@pytest.mark.skipif(not HAS_RF, reason="rapidfuzz missing")
def test_rapidfuzz_merge():
    sim, lib = default_similarity()
    assert lib == "rapidfuzz"
    assert len(cluster_entities(["Jon Smith", "John Smith"], sim, 85)) == 1


def test_require_rapidfuzz_missing(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("rapidfuzz"):
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(ConfigError):
        default_similarity(require_rapidfuzz=True)
    sim, lib = default_similarity()
    assert lib is None and sim("abc", "abc") == 100


ITEMS = [
    {"filename": "a.txt", "analysis": {"title": "T", "abstract": "A",
     "namedEntities": ["John Smith (person)", "UT Austin (institution)"]}},
    {"filename": "b.txt", "analysis": {"named_entities": "John Smith (person), XY"}},
    {"filename": "c.txt"},
]


def test_extract_and_authority_golden():
    raws = extract_all_entities(ITEMS)
    assert [r.name for r in raws] == ["John Smith", "UT Austin", "John Smith", "XY"]
    assert raws[0].context == "t a" and raws[0].source == "a.txt"
    ents = build_entities(raws, exact_or_prefix, 90)
    data = build_authority_file(ents, created="2026-01-01T00:00:00")
    js = data["entities"]["John Smith"]
    assert js == {"appearances": ["a.txt", "b.txt"], "contexts": ["t a", ""],
                  "entity_type": "person", "original_forms": ["John Smith (person)"],
                  "clustered_variants": ["John Smith"], "frequency": 2}
    assert data["metadata"]["total_entities"] == 3
    assert data["metadata"]["fuzzy_matching"]["enabled"] is False
    stats = data["statistics"]
    assert stats["by_type"] == {"person": 1, "institution": 1, "unknown": 1}
    assert stats["by_frequency"] == {"low_frequency": 1, "single_mention": 2}
    rep = render_report(stats, ents, generated="G")
    assert rep.startswith("DISSERTATION ENTITY AUTHORITY REPORT\n" + "=" * 50)
    assert "  John Smith\n    Frequency: 2 appearances\n    Appearances: a.txt, b.txt" in rep
    assert "Fuzzy Matching: Disabled" in rep


def test_empty_is_valid():
    data = build_authority_file([], created="x")
    assert data["entities"] == {} and generate_statistics([])["by_type"] == {}


def _make(tmp_path, items):
    rf = RunFolder(tmp_path / "run")
    rf.ensure_dirs()
    rf.json_path.write_text(json.dumps(items + [{"api_stats": {"n": 1}}]))
    rf.xlsx_path.write_bytes(b"")
    return rf


def test_processor_end_to_end(tmp_path):
    rf = _make(tmp_path, ITEMS)
    from datetime import datetime
    out = EntityAuthorityProcessor(rf, similarity=exact_or_prefix, threshold=90,
                                   clock=lambda: datetime(2026, 1, 1)).run()
    written = json.loads((rf.metadata_dir / "dissertation_entity_authority.json").read_text())
    assert written == out and len(written["entities"]) == 3
    assert (rf.metadata_dir / "entity_authority_report.txt").exists()


def test_processor_no_entities(tmp_path):
    rf = _make(tmp_path, [{"filename": "a", "analysis": {}}])
    out = EntityAuthorityProcessor(rf, similarity=exact_or_prefix).run()
    assert out["entities"] == {}


def test_processor_missing_files(tmp_path):
    with pytest.raises(WorkflowFilesNotFound):
        EntityAuthorityProcessor(RunFolder(tmp_path / "none"), similarity=exact_or_prefix).run()
