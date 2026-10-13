import pytest
import requests

from api.vocab.http import HttpClient
from utils.exceptions import VocabHttpError, VocabParseError


class Resp:
    def __init__(self, status=200, js=None, text=""):
        self.status_src, self._js, self.text = status, js, text

    def raise_for_status(self):
        if self.status_src >= 400:
            raise requests.exceptions.HTTPError("bad", response=self)

    def json(self):
        if self._js is None:
            raise ValueError("no json")
        return self._js


class Sess:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url, **kw):
        return self.resp


def test_sleep_injected_and_errors():
    slept = []
    h = HttpClient(Sess(Resp(js={"a": 1})), sleep=slept.append, delay=0.1)
    assert h.get_json("http://x") == {"a": 1} and slept == [0.1]
    with pytest.raises(VocabHttpError) as ei:
        HttpClient(Sess(Resp(500)), sleep=lambda s: None).get_text("http://x")
    assert "500" in str(ei.value) and "http://x" in str(ei.value) and ei.value.cause
    with pytest.raises(VocabParseError):
        HttpClient(Sess(Resp()), sleep=lambda s: None).get_json("http://x")
