import httpx
import openai
import pytest
from google.genai import errors as genai_errors

import utils.llm as llm


def _http_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "http://localhost"))


def _rate_limit():
    return openai.RateLimitError("quota exceeded", response=_http_response(429), body=None)


def _server_error():
    return openai.InternalServerError("boom", response=_http_response(500), body=None)


def test_send_with_retry_success_first_try(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    assert llm.send_with_retry(lambda: "ok", label="t") == "ok"


def test_send_with_retry_raises_quota_exceeded_after_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"n": 0}

    def sender():
        calls["n"] += 1
        raise _rate_limit()

    with pytest.raises(llm.QuotaExceededError):
        llm.send_with_retry(sender, label="t", max_retries=2)
    assert calls["n"] == 2


def test_send_with_retry_exponential_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    calls = {"n": 0}

    def sender():
        calls["n"] += 1
        raise _server_error()

    with pytest.raises(openai.InternalServerError):
        llm.send_with_retry(sender, label="t", max_retries=3, retry_delay=1.0)
    assert sleeps == [1.0, 2.0]
    assert calls["n"] == 3


def test_send_with_retry_gemini_quota_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"n": 0}

    def sender():
        calls["n"] += 1
        raise genai_errors.APIError(code=429, response_json={}, response=None)

    with pytest.raises(llm.QuotaExceededError):
        llm.send_with_retry(sender, label="t", max_retries=2)
    assert calls["n"] == 2


def test_send_with_retry_propagates_non_retryable(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    err = openai.BadRequestError("bad request", response=_http_response(400), body=None)

    def sender():
        raise err

    with pytest.raises(openai.BadRequestError):
        llm.send_with_retry(sender, label="t")


def test_provider_chain_order_and_fallback(monkeypatch):
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "g")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")

    assert llm._provider_chain() == ["gemini", "groq"]
    assert llm._provider_chain(provider="groq") == ["groq", "gemini"]
    assert llm._provider_chain(fallback=False) == ["gemini"]


def test_complete_falls_back_on_quota(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "g")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")
    monkeypatch.setattr("config.Config.QUOTA_STATE_FILE", str(tmp_path / "q.json"))

    used = []

    class FakeProvider:
        def __init__(self, name):
            self.name = name

        def complete(self, **kwargs):
            used.append(self.name)
            if self.name == "gemini":
                raise llm.QuotaExceededError("out of quota")
            return "answer from groq"

    monkeypatch.setattr(llm, "_get_provider", lambda name: FakeProvider(name))

    out = llm.complete(model="m", messages=[{"role": "user", "content": "hi"}], use_cache=False)
    assert out == "answer from groq"
    assert used == ["gemini", "groq"]


def test_complete_all_providers_quota_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "g")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")
    monkeypatch.setattr("config.Config.QUOTA_STATE_FILE", str(tmp_path / "q.json"))

    class FakeProvider:
        def __init__(self, name):
            self.name = name

        def complete(self, **kwargs):
            raise llm.QuotaExceededError("out of quota")

    monkeypatch.setattr(llm, "_get_provider", lambda name: FakeProvider(name))

    with pytest.raises(llm.QuotaExceededError):
        llm.complete(model="m", messages=[{"role": "user", "content": "hi"}], use_cache=False)


def test_complete_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("config.Config.QUOTA_STATE_FILE", str(tmp_path / "q.json"))

    calls = {"n": 0}

    class FakeProvider:
        def complete(self, **kwargs):
            calls["n"] += 1
            return "cached-answer"

    monkeypatch.setattr(llm, "_get_provider", lambda name: FakeProvider())

    messages = [{"role": "user", "content": "hi"}]
    assert llm.complete(model="m", messages=messages, use_cache=True) == "cached-answer"
    assert llm.complete(model="m", messages=messages, use_cache=True) == "cached-answer"
    assert calls["n"] == 1

    assert llm.complete(model="m", messages=messages, use_cache=False) == "cached-answer"
    assert calls["n"] == 2


def test_complete_skips_cache_for_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("config.Config.QUOTA_STATE_FILE", str(tmp_path / "q.json"))

    calls = {"n": 0}

    class FakeProvider:
        def complete(self, **kwargs):
            calls["n"] += 1
            return "answer"

    monkeypatch.setattr(llm, "_get_provider", lambda name: FakeProvider())

    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    llm.complete(model="m", messages=messages, tools=tools, use_cache=True)
    llm.complete(model="m", messages=messages, tools=tools, use_cache=True)
    assert calls["n"] == 2
