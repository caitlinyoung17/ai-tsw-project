import openpyxl
import pytest

from metadata_standard import MetadataStandard, Term
from utils.exceptions import (PayloadValidationError, VocabularyFormatError,
                              VocabularyLoadError)

DATA = {
    "pottery": [
        {"label": "Pottery", "uri": "u1", "source": "LCSH"},
        {"label": "Pottery", "uri": "u2", "source": "Getty AAT"},
        {"label": "Pottery", "uri": "u3", "source": "FAST"},
    ],
    "Texas": [{"label": "Texas", "uri": "t1", "source": "Getty TGN"},
              {"label": "Texas", "uri": "t2", "source": "FAST"}],
    "empty": [],
}


def test_round_trip():
    std = MetadataStandard.from_dict(DATA)
    out = std.to_json()
    assert out["pottery"][0]["label"] == "Pottery"
    assert MetadataStandard.from_dict(out).to_json() == out


@pytest.mark.parametrize("bad", [[], {"a": "x"}, {"a": [{"uri": "u", "source": "LCSH"}]}])
def test_invalid_shapes(bad):
    with pytest.raises(VocabularyFormatError):
        MetadataStandard.from_dict(bad)


def test_missing_file(tmp_path):
    with pytest.raises(VocabularyLoadError):
        MetadataStandard.load_from_json(tmp_path / "nope.json")


def test_load_json(tmp_path):
    import json
    p = tmp_path / "v.json"
    p.write_text(json.dumps(DATA))
    assert MetadataStandard.load_from_json(p).has_candidates()


def test_excel(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Analysis"
    ws.append(["Subjects", "Subject Vocabulary Terms"])
    ws.append(["pottery, clay", "Pottery (u1) [LCSH]; Clay [FAST]"])
    p = tmp_path / "a.xlsx"
    wb.save(p)
    std = MetadataStandard.load_from_excel(p)
    ts = std.terms_for("pottery, clay")
    assert [t.source for t in ts] == ["LCSH", "FAST"]
    assert ts[0].uri == "u1" and ts[1].uri == ""
    ws.title = "Other"
    wb.save(p)
    with pytest.raises(VocabularyFormatError):
        MetadataStandard.load_from_excel(p)


def test_render_golden():
    std = MetadataStandard.from_dict({"a": [{"label": "A", "uri": "u", "source": "LCSH"},
                                            {"label": "B", "uri": "", "source": "FAST"}],
                                      "b": []})
    assert std.render_for_prompt() == (
        "Subject: a\n  - A (u) [LCSH]\n  - B [FAST]\n\n"
        "Subject: b\n  (No candidate controlled terms)\n")
    assert MetadataStandard().render_for_prompt() == ""
    assert not MetadataStandard.from_dict({"b": []}).has_candidates()


def test_excel_strings():
    std = MetadataStandard.from_dict(DATA)
    assert std.to_excel_strings()["Texas"] == "Texas (t1) [Getty TGN]; Texas (t2) [FAST]"


def test_match_priority_and_dedupe():
    std = MetadataStandard.from_dict(DATA)
    got = std.match_selected_labels(["pottery", "POTTERY"])
    assert [t.uri for t in got] == ["u2"]  # AAT beats LCSH/FAST; deduped
    assert std.match_selected_labels(["Texas"])[0].uri == "t2"  # FAST(3) beats TGN(4)


def test_match_reorder_accents_unmatched():
    std = MetadataStandard.from_dict(
        {"s": [{"label": "Art, Mexican", "uri": "m", "source": "LCSH"},
               {"label": "Café", "uri": "c", "source": "FAST"}]})
    assert std.match_selected_labels(["Mexican Art"])[0].uri == "m"
    assert std.match_selected_labels(["Cafe"])[0].uri == "c"
    assert std.unmatched_labels(["Mexican Art", "Nothing"]) == ["Nothing"]


def test_cross_vocab_duplicate_uri():
    std = MetadataStandard.from_dict(
        {"a": [{"label": "X", "uri": "same", "source": "FAST"}],
         "b": [{"label": "X", "uri": "same", "source": "FAST"}]})
    assert len(std.match_selected_labels(["X", "X"])) == 1


def test_validate_selection():
    assert MetadataStandard.validate_selection({"selected_terms": []}) == []
    assert MetadataStandard.validate_selection(
        {"selected_terms": ["a", {"label": "b"}]}) == ["a", "b"]
    for bad in ({}, {"selected_terms": "x"}, {"selected_terms": [1]}):
        with pytest.raises(PayloadValidationError):
            MetadataStandard.validate_selection(bad)


def test_from_workflow_item():
    item = {"analysis": {"vocabulary_search_results": DATA}}
    assert MetadataStandard.from_workflow_item(item).has_candidates()
    with pytest.raises(VocabularyFormatError):
        MetadataStandard.from_workflow_item({})
