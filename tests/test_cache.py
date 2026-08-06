from utils.cache import ResponseCache


def test_roundtrip(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    messages = [{"role": "user", "content": "hi"}]
    assert cache.get("gemini", "m", "sys", messages) is None
    cache.set("gemini", "m", "sys", messages, "response text")
    assert cache.get("gemini", "m", "sys", messages) == "response text"


def test_key_differs_by_provider_and_prompt(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    cache.set("gemini", "m", None, [{"role": "user", "content": "a"}], "one")

    assert cache.get("gemini", "m", None, [{"role": "user", "content": "a"}]) == "one"
    assert cache.get("gemini", "m", None, [{"role": "user", "content": "b"}]) is None
    assert cache.get("groq", "m", None, [{"role": "user", "content": "a"}]) is None
    assert cache.get("gemini", "other-model", None, [{"role": "user", "content": "a"}]) is None


def test_json_mode_and_schema_part_of_key(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    messages = [{"role": "user", "content": "judge"}]
    schema = {"type": "object", "properties": {"winner": {"type": "string"}}}

    cache.set("gemini", "m", None, messages, "a", json_mode=True, response_schema=schema)
    assert cache.get("gemini", "m", None, messages, json_mode=False) is None
    assert cache.get("gemini", "m", None, messages, json_mode=True) is None
    assert cache.get("gemini", "m", None, messages, json_mode=True, response_schema=schema) == "a"
