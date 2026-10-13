import glob
import tempfile
from types import SimpleNamespace as NS

import pytest

from api.open_ai import (OpenAIBatchClient, OpenAIConfig, OpenAIPricing,
                         PortkeyOpenAIProvider, build_openai_provider)
from api.llm_core import BatchItem, CompletionRequest, Message, Usage
from utils.exceptions import (BatchError, ConfigError, LLMError,
                              LLMResponseError, LLMTransientError)

CFG = OpenAIConfig(api_key="k")
REQ = CompletionRequest("gpt-4o", (Message("user", "hi"),), 100, 0.0)


class RateLimitError(Exception):
    status_src = 429


class AuthError(Exception):
    status_src = 401


def resp(content="ok", usage="default", choices=True):
    u = NS(prompt_tokens=10, completion_tokens=5,
           prompt_tokens_details=NS(cached_tokens=4)) if usage == "default" else usage
    ch = [NS(message=NS(content=content), finish_reason="stop")] if choices else []
    return NS(choices=ch, usage=u, model="gpt-4o")


class FakeChat:
    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.completions = self

    def create(self, **kw):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def provider(script, sleeps=None):
    chat = FakeChat(script)
    p = PortkeyOpenAIProvider(CFG, client_factory=lambda c: NS(chat=chat),
                              sleep=(sleeps.append if sleeps is not None else lambda s: None))
    return p, chat


def test_success_with_cached_tokens():
    p, _ = provider([resp()])
    r = p.complete(REQ)
    assert r.content == "ok" and r.usage == Usage(10, 5, 4)


def test_empty_choices():
    p, _ = provider([resp(choices=False)])
    with pytest.raises(LLMResponseError):
        p.complete(REQ)


def test_usage_missing():
    p, _ = provider([resp(usage=None)])
    assert p.complete(REQ).usage == Usage()


def test_transient_retried():
    sleeps = []
    p, chat = provider([RateLimitError("x"), TimeoutError("t"), resp()], sleeps)
    assert p.complete(REQ).content == "ok"
    assert chat.calls == 3 and len(sleeps) == 2


def test_transient_exhausted():
    p, chat = provider([RateLimitError()] * 3)
    with pytest.raises(LLMTransientError):
        p.complete(REQ)
    assert chat.calls == 3


def test_auth_not_retried():
    p, chat = provider([AuthError("no")])
    with pytest.raises(LLMError) as e:
        p.complete(REQ)
    assert not isinstance(e.value, LLMTransientError) and chat.calls == 1


def test_client_lazy():
    made = []
    build_openai_provider(CFG, client_factory=lambda c: made.append(1))
    assert made == []


# batch ---------------------------------------------------------------
class FakeBatchClient:
    def __init__(self, statuses, output_lines=None, fail_create=False):
        self.statuses, self.output_lines = list(statuses), output_lines or []
        self.uploaded, self.polls, self.fail_create = [], 0, fail_create
        self.files = NS(create=self._create, content=self._content)
        self.batches = NS(create=self._bcreate, retrieve=self._retrieve)

    def _create(self, file, purpose):
        self.uploaded.append(file.name)
        self.body = file.read().decode()
        return NS(id="file1")

    def _bcreate(self, **kw):
        if self.fail_create:
            raise RuntimeError("boom")
        return NS(id="b1")

    def _retrieve(self, bid):
        self.polls += 1
        s = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return NS(status=s, output_file_id="out", error_file_id=None)

    def _content(self, fid):
        return NS(text="\n".join(self.output_lines))


def line(cid, ok=True):
    import json
    if ok:
        return json.dumps({"custom_id": cid, "response": {"status_src": 200, "body": {
            "model": "m", "choices": [{"message": {"content": "c-" + cid}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}}}})
    return json.dumps({"custom_id": cid, "response": None, "error": {"src": "bad"}})


def items(*ids):
    return [BatchItem(i, REQ) for i in ids]


def test_ids_preserved_with_gaps():
    fc = FakeBatchClient(["completed"], [line("doc_7"), line("doc_2")])
    c = OpenAIBatchClient(fc, CFG, sleep=lambda s: None)
    h = c.submit_batch(items("doc_2", "doc_7"))
    assert '"custom_id": "doc_2"' in fc.body and '"custom_id": "doc_7"' in fc.body
    out = c.collect_batch(h)
    assert set(out) == {"doc_2", "doc_7"} and out["doc_7"].result.content == "c-doc_7"
    assert out["doc_2"].result.usage == Usage(3, 2, 0)


def test_temp_file_removed():
    import os
    fc = FakeBatchClient(["completed"])
    OpenAIBatchClient(fc, CFG).submit_batch(items("a"))
    assert not os.path.exists(fc.uploaded[0])
    fc2 = FakeBatchClient(["completed"], fail_create=True)
    with pytest.raises(BatchError):
        OpenAIBatchClient(fc2, CFG).submit_batch(items("a"))
    assert not os.path.exists(fc2.uploaded[0])


def test_polling_interval_and_timeout():
    fc = FakeBatchClient(["in_progress", "in_progress", "completed"], [line("a")])
    sleeps = []
    c = OpenAIBatchClient(fc, CFG)
    c.collect_batch(c.submit_batch(items("a")), poll_interval=7, sleep=sleeps.append)
    assert sleeps == [7, 7]
    fc = FakeBatchClient(["in_progress"])
    c = OpenAIBatchClient(fc, CFG)
    with pytest.raises(BatchError):
        c.collect_batch(c.submit_batch(items("a")), timeout=20, poll_interval=10,
                        sleep=lambda s: None)


@pytest.mark.parametrize("st", ["expired", "failed", "cancelled"])
def test_bad_status(st):
    c = OpenAIBatchClient(FakeBatchClient([st]), CFG)
    with pytest.raises(BatchError):
        c.collect_batch(c.submit_batch(items("a")), sleep=lambda s: None)


def test_item_failure_is_data():
    fc = FakeBatchClient(["completed"], [line("a"), line("b", ok=False)])
    c = OpenAIBatchClient(fc, CFG)
    out = c.collect_batch(c.submit_batch(items("a", "b")))
    assert out["a"].result and out["b"].error and out["b"].result is None


def test_duplicate_ids_rejected():
    with pytest.raises(BatchError):
        OpenAIBatchClient(FakeBatchClient(["completed"]), CFG).submit_batch(items("a", "a"))


# config / pricing ----------------------------------------------------
def test_config_missing_key():
    with pytest.raises(ConfigError):
        OpenAIConfig.from_env({})
    c = OpenAIConfig.from_env({"PORTKEY_API_KEY": "k", "MODEL_NAME": "gpt-4.1"})
    assert c.default_model == "gpt-4.1" and c.portkey_provider == "@glib-achoate-openai"


def test_pricing():
    p = OpenAIPricing()
    u = Usage(1000, 1000)
    assert p.cost(u, "gpt-4o") == pytest.approx(0.0125)
    assert p.cost(u, "gpt-4o", batch=True) == pytest.approx(0.00625)
    with pytest.raises(Exception):
        p.cost(u, "nope")
    assert OpenAIPricing("gpt-4o-mini").cost(u, "nope") == pytest.approx(0.00075)
