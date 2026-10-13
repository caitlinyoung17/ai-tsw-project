import pytest

from api.vocab import (FastClient, FastGeographicClient, GettyAATClient,
                       GettyTGNClient, LcshClient, QueryCache, VocabStatsTracker)
from utils.exceptions import VocabHttpError, VocabParseError


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.sleeps = 0

    def _next(self, url, params):
        self.calls.append((url, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    get_json = get_text = _next


FAST_OK = {"response": {"docs": [
    {"suggestall": ["Rivers"], "idroot": "fst1", "auth": "Rivers", "type": "auth"},
    {"suggestall": "Rivers x", "idroot": "fst1", "type": "auth"},  # dup uri
    {"suggestall": "Lakes", "idroot": "fst2", "auth": "Lakes"},
    {"suggestall": "NoId"},
]}}
GEO_OK = {"response": {"docs": [
    {"suggestall": "Texas", "idroot": "fst9", "auth": "Texas", "type": "Geographic",
     "tag": ["a", "b"]}]}}
XML = ("<R><Subject><Subject_ID>1</Subject_ID><Preferred_Term>Walls</Preferred_Term></Subject>"
       "<Subject><Subject_ID>2</Subject_ID></Subject>"
       "<Subject><Subject_ID>3</Subject_ID><Preferred_Term/></Subject></R>")


def test_fast_parse_dedupe_and_fields():
    c = FastClient(FakeHttp([FAST_OK]))
    terms = c.search("rivers")
    assert [t.label for t in terms] == ["Rivers", "Lakes"]
    assert terms[0].uri == "http://id.worldcat.org/fast/fst1" and terms[0].source == "FAST"


def test_fast_cap():
    c = FastClient(FakeHttp([FAST_OK]), max_results=1)
    assert len(c.search("rivers")) == 1


def test_fast_geo():
    t = FastGeographicClient(FakeHttp([GEO_OK])).search("Texas")[0]
    assert t.source == "FAST Geographic" and t.tag == "a, b"


def test_zero_hits_empty_and_fast_fallback_words():
    http = FakeHttp([{"response": {"docs": []}}, FAST_OK, FAST_OK])
    terms = FastClient(http).search("Texas rivers")
    assert [t.label for t in terms] == ["Rivers"]  # overlap filter
    assert len(http.calls) == 3


def test_http_error_raises_and_is_not_cached():
    http = FakeHttp([VocabHttpError("boom"), FAST_OK])
    cache, stats = QueryCache(), VocabStatsTracker()
    c = FastClient(http, cache=cache, stats=stats)
    with pytest.raises(VocabHttpError):
        c.search("rivers")
    assert len(c.search("rivers")) == 2
    assert stats.summary()["api_breakdown"]["FAST"]["failed"] == 1


@pytest.mark.parametrize("payload", ["x", [1], {"response": 5}])
def test_fast_malformed(payload):
    with pytest.raises(VocabParseError):
        FastClient(FakeHttp([payload])).search("q")


def test_getty_aat_missing_preferred_term():
    terms = GettyAATClient(FakeHttp([XML])).search("walls")
    assert [(t.label, t.uri) for t in terms] == [("Walls", "http://vocab.getty.edu/aat/1")]


def test_getty_tgn_and_bad_xml():
    assert GettyTGNClient(FakeHttp([XML])).search("x")[0].source == "Getty TGN"
    with pytest.raises(VocabParseError):
        GettyAATClient(FakeHttp(["<not xml"])).search("x")


def test_lcsh_parse_and_leftanchored_topup():
    http = FakeHttp([{"hits": [{"aLabel": "A", "uri": "u1"}, {"aLabel": "", "uri": "u"}]},
                     {"hits": [{"aLabel": "A", "uri": "u1"}, {"aLabel": "B", "uri": "u2"}]}])
    terms = LcshClient(http).search("a")
    assert [t.uri for t in terms] == ["u1", "u2"]
    assert http.calls[1][1]["searchtype"] == "leftanchored"


def test_lcsh_malformed():
    with pytest.raises(VocabParseError):
        LcshClient(FakeHttp([["x"]])).search("a")


def test_cache_hit_avoids_request():
    http = FakeHttp([{"hits": [{"aLabel": c, "uri": c} for c in "abc"]}])
    stats = VocabStatsTracker()
    c = LcshClient(http, stats=stats)
    c.search("a"); c.search("a")
    assert len(http.calls) == 1
    b = stats.summary()["api_breakdown"]["LCSH"]
    assert b["cache_hits"] == 1 and b["requests"] == 1


def test_stats_summary_does_not_mutate():
    s = VocabStatsTracker()
    s.record_call("X", "subj", True, 1.0, 2)
    a = s.summary(1)
    a["api_breakdown"]["X"]["requests"] = 99
    assert s.summary(1)["api_breakdown"]["X"]["requests"] == 1
    assert "success_rate" not in s.api_breakdown["X"]
