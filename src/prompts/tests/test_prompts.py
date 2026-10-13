from pathlib import Path

import pytest

from api.llm_core import truncate_for_prompt
from prompts import (ALL_FIELDS, FULL_TEXT_FIELDS,
                     abstract_completion_template, chunk_entities_template,
                     front_matter_template, metadata_extraction_template,
                     render_vocab_selection, EXTRACTION, CHUNK, CLEANUP, SELECTION)
from utils.exceptions import PayloadValidationError

HERE = Path(__file__).parent


def test_golden_metadata_system():
    t = metadata_extraction_template()
    golden = (HERE / "golden_metadata_system.txt").read_text()
    assert t.render(text="x")[0].content == golden


def test_golden_vocab_system():
    golden = (HERE / "golden_vocab_system.txt").read_text()
    msgs = render_vocab_selection("T", "A", "sections")
    assert msgs[0].content == golden
    assert "sections" in msgs[1].content and "Title: T" in msgs[1].content


def test_all_fields_in_schema():
    sys = metadata_extraction_template().render(text="x")[0].content
    for f in ALL_FIELDS:
        assert f'"{f.name}"' in sys


def test_missing_variable():
    with pytest.raises(PayloadValidationError):
        metadata_extraction_template().render()


def test_chunk_template_only_full_text_fields():
    sys = chunk_entities_template().render(text="x")[0].content
    assert "partial excerpt" in sys
    for f in FULL_TEXT_FIELDS:
        assert f'"{f.name}"' in sys
    for n in ("title", "creator", "department", "abstract"):
        assert f'"{n}"' not in sys


def test_front_matter_and_abstract():
    assert '"title"' in front_matter_template().render(text="x")[0].content
    assert "abstract" in abstract_completion_template().render(text="x")[0].content


def test_text_with_dollar_is_literal():
    assert "$5 and $x" in metadata_extraction_template().render(text="$5 and $x")[1].content


def test_truncation_and_params():
    assert len(truncate_for_prompt("a" * 100, 20)) == 20
    assert len(render_vocab_selection("t" * 9999, "", "s")[1].content) < 9999
    assert EXTRACTION.max_tokens == 8000 and CHUNK and CLEANUP and SELECTION
