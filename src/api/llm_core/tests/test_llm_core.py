from datetime import datetime

import pytest

from api.llm_core import (CompletionRequest, LLMConfig, Message, ModelPrice, PromptTemplate,
                          RetryPolicy, Usage, UsageLogger, UsageTracker, call_with_retry,
                          parse_json_response, validate_request)
from api.llm_core.pricing import TablePricing
from api.llm_core.testing import FakeProvider
from utils.exceptions import (ConfigError, LLMResponseError, LLMTransientError,
                              PayloadValidationError, UnknownModelError)

PRICES = {"m": ModelPrice(0.001, 0.002, cached_per_1k=0.0005),
          "fb": ModelPrice(0.01, 0.02)}


def test_template_render_and_missing():
    t = PromptTemplate("sys $a", "user ${b} $$5")
    msgs = t.render(a="x", b="y")
    assert msgs == [Message("system", "sys x"), Message("user", "user y $5")]
    with pytest.raises(PayloadValidationError):
        t.render(a="x")


def test_parse_json():
    assert parse_json_response('```json\n{"a": 1,}\n```') == {"a": 1}
    assert parse_json_response("{}") == {}
    with pytest.raises(LLMResponseError):
        parse_json_response('{"a": "tru')
    with pytest.raises(LLMResponseError):
        parse_json_response("  ")


def test_retry():
    sleeps = []
    pol = RetryPolicy(3, 1.0, 10.0, sleep=sleeps.append)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise LLMTransientError("x")
        return "ok"
    assert call_with_retry(flaky, pol) == "ok"
    assert sleeps == [1.0, 2.0] and pol.retries == 2

    def always():
        raise LLMTransientError("x")
    with pytest.raises(LLMTransientError):
        call_with_retry(always, RetryPolicy(2, sleep=lambda s: None))

    n = []

    def bad():
        n.append(1)
        raise ValueError
    with pytest.raises(ValueError):
        call_with_retry(bad, RetryPolicy(5, sleep=lambda s: None))
    assert len(n) == 1


def test_pricing():
    p = TablePricing(PRICES)
    u = Usage(1000, 1000)
    assert p.cost(u, "m") == pytest.approx(0.003)
    assert p.cost(u, "m", batch=True) == pytest.approx(0.0015)
    assert p.cost(Usage(1000, 0, cached_tokens=1000), "m") == pytest.approx(0.0005)
    with pytest.raises(UnknownModelError):
        p.cost(u, "nope")
    assert TablePricing(PRICES, fallback_model="fb").cost(u, "nope") == pytest.approx(0.03)


def test_tracker():
    t = UsageTracker()
    t.record(Usage(10, 5, 2), elapsed=1.0)
    t.record(Usage(10, 5), batch=True, elapsed=3.0)
    s = t.summary()
    assert s["total_requests"] == 2 and s["total_tokens"] == 30
    assert s["total_cached_tokens"] == 2 and s["average_time"] == 2.0


def _logger(out):
    return UsageLogger(TablePricing(PRICES), "Acme", out.append,
                       clock=lambda: datetime(2026, 1, 2, 3, 4, 5))


def test_summary_golden():
    out = []
    text = _logger(out).log_summary("metadata_creation", "m", 2, 0, 10.0, Usage(1000, 1000))
    assert out == [text]
    assert text.startswith("Acme API Usage Log - Metadata Creation\n" + "=" * 60 + "\n"
                           "Processing completed at: 2026-01-02 03:04:05\n")
    assert "Input token cost: $0.0010\n" in text
    assert "Total actual cost: $0.0030\n" in text
    assert "batch" not in text.lower()
    assert "OpenAI" not in text


def test_summary_batch():
    out = []
    text = _logger(out).log_summary("s", "m", 1, 0, 1.0, Usage(1000, 1000), batch=True)
    assert "Batch discount applied: 50%\n" in text
    assert "Input token cost: $0.0005 (batch discounted)\n" in text
    assert "Total actual cost: $0.0015\n" in text
    assert "Batch processing savings: $0.0015\n" in text


def test_log_response(tmp_path):
    path = tmp_path / "r.txt"
    lg = UsageLogger(TablePricing(PRICES), "Acme", path, clock=lambda: datetime(2026, 1, 1))
    lg.log_response("s", 1, "b", "resp", "m", Usage(1000, 1000), 1.5, batch=True,
                    include_header=True)
    lg.log_response("s", 2, "b", "resp2", "m", Usage(1000, 1000), 1.5)
    txt = path.read_text()
    assert txt.count("LLM Full Responses Log") == 1
    assert "ESTIMATED COST: $0.0015" in txt and "ESTIMATED COST: $0.0030" in txt


def test_fake_provider():
    req = CompletionRequest("fake-model", (Message("user", "hi"),), 10, 0.0)
    validate_request(req)
    fp = FakeProvider(["a", LLMTransientError("boom")])
    assert fp.complete(req).content == "a"
    with pytest.raises(LLMTransientError):
        fp.complete(req)
    assert len(fp.requests) == 2
    assert not fp.supports_batch
    with pytest.raises(LLMResponseError):
        fp.complete(req)
    with pytest.raises(PayloadValidationError):
        validate_request(CompletionRequest("m", (), 10, 0.0))


def test_config_from_env():
    c = LLMConfig.from_env("X_", env={"X_MODEL": "m", "X_MAX_TOKENS": "5"})
    assert c.model == "m" and c.max_tokens == 5 and c.api_key is None
    with pytest.raises(ConfigError):
        LLMConfig.from_env("X_", env={})
    with pytest.raises(ConfigError):
        LLMConfig.from_env("X_", env={"X_MODEL": "m"}, require_api_key=True)
