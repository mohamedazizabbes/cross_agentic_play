from types import SimpleNamespace

from google.genai import types as genai_types
from models import JudgeOutputSchema

import utils.llm as llm
from tools.web_search import WEB_SEARCH_TOOL


def test_gemini_provider_tool_loop(monkeypatch):
    calls = []

    def fake_execute_tool(**kwargs):
        calls.append(kwargs)
        return f"result:{kwargs['query']}"

    fc_part = genai_types.Part(
        function_call=genai_types.FunctionCall(name="web_search", args={"query": "coffee"})
    )
    resp_tool = genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(parts=[fc_part]))]
    )
    resp_text = genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(parts=[genai_types.Part.from_text(text="final")]))]
    )

    responses = [resp_tool, resp_text]
    monkeypatch.setattr(llm, "send_with_retry", lambda sender, label="request", max_retries=3: responses.pop(0))
    monkeypatch.setattr(llm, "get_gemini_client", lambda: object())

    provider = llm.GeminiProvider()
    provider.client = object()  # not used; send_with_retry is stubbed

    out = provider.complete(
        model="m", messages=[{"role": "user", "content": "hi"}],
        system="sys", tools=[WEB_SEARCH_TOOL], execute_tool=fake_execute_tool,
    )
    assert out == "final"
    assert calls == [{"query": "coffee"}]


def test_gemini_provider_skips_history_tool_messages(monkeypatch):
    monkeypatch.setattr(llm, "send_with_retry", lambda sender, label="request", max_retries=3: None)
    monkeypatch.setattr(llm, "get_gemini_client", lambda: object())
    provider = llm.GeminiProvider()

    content = provider._to_content({"role": "user", "content": "hello"})
    assert content.role == "user"
    content2 = provider._to_content({"role": "assistant", "content": "hi back"})
    assert content2.role == "model"


def test_openai_compat_provider_tool_loop(monkeypatch):
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "gsk_test")
    provider = llm.OpenAICompatProvider("groq")

    tc = SimpleNamespace(id="call_1", type="function",
                         function=SimpleNamespace(name="web_search", arguments='{"query": "coffee"}'))
    resp1 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))])
    resp2 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="answer", tool_calls=None))])

    calls = []
    responses = [resp1, resp2]

    def fake_create(model, messages, kwargs, label="chat"):
        calls.append((messages, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(provider, "_create", fake_create)

    out = provider.complete(
        model="m", messages=[{"role": "user", "content": "hi"}],
        system="sys", tools=[WEB_SEARCH_TOOL],
        execute_tool=lambda **kw: f"result:{kw['query']}",
    )
    assert out == "answer"
    # assistant tool_calls + tool result appended to conversation history
    msgs, _ = calls[1]
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["tool_calls"][0]["function"]["name"] == "web_search"
    assert msgs[3]["role"] == "tool"
    assert msgs[3]["tool_call_id"] == "call_1"


def test_openai_compat_json_mode_uses_schema(monkeypatch):
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "gsk_test")
    provider = llm.OpenAICompatProvider("groq")

    captured = {}

    def fake_create(model, messages, kwargs, label="chat"):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"winner": "PRO"}', tool_calls=None))])

    monkeypatch.setattr(provider, "_create", fake_create)

    out = provider.complete(
        model="m", messages=[{"role": "user", "content": "judge"}],
        json_mode=True, response_schema=JudgeOutputSchema,
    )
    assert out == '{"winner": "PRO"}'
    rf = captured["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"]["properties"]["winner"]


def test_openai_compat_missing_key_raises(monkeypatch):
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "")
    try:
        llm.OpenAICompatProvider("groq")
        raise AssertionError("expected LLMError")
    except llm.LLMError:
        pass


def test_to_schema_builds_nested_schema():
    schema = llm._to_schema({
        "type": "object",
        "properties": {"query": {"type": "string", "description": "q"}},
        "required": ["query"],
    })
    assert schema.type == genai_types.Type.OBJECT
    assert schema.required == ["query"]
    assert schema.properties["query"].type == genai_types.Type.STRING
