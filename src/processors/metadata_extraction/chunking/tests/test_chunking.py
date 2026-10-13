import json

import pytest

from api.llm_core.testing import FakeProvider
from api.llm_core.types import Usage
from utils.exceptions import ConfigError, LLMResponseError

from processors.metadata_extraction import Document, MetadataExtractor
from processors.metadata_extraction.chunking import (
    ChunkingConfig, ChunkingStrategyImpl, ChunkProcessor, ChunkResult,
    PaginatedProcessor, merge, needs_chunking, split_document)

FRONT = json.dumps({"title": "T", "creator": "C", "date": "2000", "abstract": "Short abstract.",
                    "type": "Thesis"})
FRONT_NOABS = json.dumps({"title": "T", "abstract": ""})


def chunk(subj=("a",), ne=(), geo=(), cw="None"):
    return json.dumps({"subjects": list(subj), "namedEntities": list(ne),
                       "geographicEntities": list(geo), "contentWarning": cw})


def abs_resp(text, complete):
    return json.dumps({"abstract_found": True, "abstract_complete": complete, "abstract": text})


def long_text(n):
    s = "This is a sentence about things. "
    return (s * (n // len(s) + 1))[:n]


# ---- config / size check
def test_config_validation():
    with pytest.raises(ConfigError):
        ChunkingConfig(overlap=100, chunk_size=100)
    with pytest.raises(ConfigError):
        ChunkingConfig(chunk_size=0)
    with pytest.raises(ConfigError):
        ChunkingConfig(abstract_scan_max_chunks=-1)


def test_needs_chunking_boundaries():
    c = ChunkingConfig(max_whole_document_chars=100)
    assert not needs_chunking("x" * 100, c)
    assert needs_chunking("x" * 101, c)
    assert not needs_chunking("x" * 1000, ChunkingConfig(enabled=False, max_whole_document_chars=100))
    ct = ChunkingConfig(max_whole_document_tokens=5)
    assert needs_chunking("a b c d e f", ct, lambda t: len(t.split()))
    assert not needs_chunking("a b c d e", ct, lambda t: len(t.split()))


# ---- split
def test_split_short_text():
    s = split_document("short.", ChunkingConfig())
    assert s.front_matter == "short." and s.chunks == []


def test_split_overlap_and_sentences():
    cfg = ChunkingConfig(front_matter_chars=100, chunk_size=500, overlap=50)
    text = long_text(3000)
    s = split_document(text, cfg)
    assert s.front_matter.endswith(". ")
    assert len(s.chunks) > 3
    body = text[len(s.front_matter):]
    assert s.chunks[0] == body[:len(s.chunks[0])]
    for c in s.chunks[:-1]:
        assert c.endswith(". ") and len(c) <= 500
    assert s.chunks[-1].endswith(body[-20:])
    # overlap: next chunk starts inside the previous one
    assert s.chunks[1][:20] in s.chunks[0]


def test_split_exact_multiple_and_no_sentence():
    cfg = ChunkingConfig(front_matter_chars=10, chunk_size=100, overlap=0)
    s = split_document("x" * 210, cfg)
    assert s.front_matter == "x" * 10
    assert [len(c) for c in s.chunks] == [100, 100]


# ---- paginated
def processor(responses, **cfgkw):
    p = FakeProvider(list(responses))
    cfg = ChunkingConfig(**cfgkw)
    return p, PaginatedProcessor(ChunkProcessor(p, "fake-model"), cfg)


def test_default_front_matter_only_one_call_1m_chars():
    p, pp = processor([FRONT])
    out = pp.run(long_text(1_000_000))
    assert len(p.requests) == 1
    assert out.metadata["title"] == "T" and out.metadata["subjects"] == []


def test_full_text_scan_max_chunks():
    p, pp = processor([FRONT] + [chunk((n,)) for n in ("sa", "sb")],
                      full_text_scan=True, max_chunks=2, chunk_size=1000, overlap=10,
                      abstract_scan_max_chunks=0)
    out = pp.run(long_text(20000))
    assert len(p.requests) == 3
    assert out.metadata["subjects"] == ["sa", "sb"]
    assert out.usage == Usage(30, 15)


def test_abstract_continuation_stops_when_complete():
    p, pp = processor([FRONT_NOABS, abs_resp("part one", False), abs_resp("part two", True)],
                      abstract_scan_max_chunks=5, chunk_size=1000, overlap=10)
    out = pp.run(long_text(20000))
    assert len(p.requests) == 3
    assert out.metadata["abstract"] == "part one part two"
    assert out.warnings == ()


def test_abstract_continuation_cap_warns():
    p, pp = processor([FRONT_NOABS, abs_resp("x", False), abs_resp("y", False)],
                      abstract_scan_max_chunks=2, chunk_size=1000, overlap=10)
    out = pp.run(long_text(20000))
    assert len(p.requests) == 3
    assert any("abstract" in w for w in out.warnings)


def test_abstract_scan_disabled():
    p, pp = processor([FRONT_NOABS], abstract_scan_max_chunks=0)
    pp.run(long_text(100000))
    assert len(p.requests) == 1


def test_chunk_failure_partial_warning_and_front_failure():
    p, pp = processor([FRONT, LLMResponseError("bad"), chunk(("ok",))],
                      full_text_scan=True, chunk_size=1000, overlap=10, max_chunks=2,
                      abstract_scan_max_chunks=0)
    out = pp.run(long_text(20000))
    assert out.metadata["subjects"] == ["ok"] and len(out.warnings) == 1
    p2, pp2 = processor([LLMResponseError("bad")])
    with pytest.raises(LLMResponseError):
        pp2.run(long_text(100000))


# ---- merge
def cr(subj=(), ne=(), geo=(), cw="None"):
    return ChunkResult(0, list(subj), list(ne), list(geo), cw, Usage(), "")


def test_merge_dedupe_and_precedence():
    front = {"title": "Front", "creator": "X"}
    m, cw = merge(front, [cr(ne=["Bogotá", "Lima"], subj=["Art"]),
                          cr(ne=["Bogota", "lima"], subj=["art", "Music"])])
    assert m["title"] == "Front"
    assert m["namedEntities"] == ["Bogotá", "Lima"]
    assert m["subjects"] == ["Art", "Music"]
    assert cw == {"flag": False, "reasons": []} and m["contentWarning"] == "None"


def test_merge_content_warning():
    m, cw = merge({}, [cr(cw="Violence."), cr(cw="None"), cr(cw="violence"),
                       cr(cw="Racist language")])
    assert cw["flag"] and cw["reasons"] == ["Violence", "Racist language"]
    assert m["contentWarning"] == "Violence; Racist language."


# ---- integration
def test_extractor_integration_chunked_and_whole():
    whole = json.dumps({"title": "W", "subjects": ["z"]})
    p = FakeProvider([FRONT, chunk(("a",)), chunk(("b",)), whole])
    cfg = ChunkingConfig(max_whole_document_chars=5000, full_text_scan=True,
                         chunk_size=2000, overlap=10, max_chunks=2,
                         abstract_scan_max_chunks=0)
    ex = MetadataExtractor(p, "fake-model", chunking=ChunkingStrategyImpl(p, "fake-model", cfg))
    r = ex.extract(Document("a.txt", "a.txt", "/a.txt", long_text(20000)))
    assert r.metadata["title"] == "T" and r.metadata["subjects"] == ["a", "b"]
    assert r.usage == Usage(30, 15)
    r2 = ex.extract(Document("b.txt", "b.txt", "/b.txt", "short text"))
    assert r2.metadata["title"] == "W" and len(p.requests) == 4
