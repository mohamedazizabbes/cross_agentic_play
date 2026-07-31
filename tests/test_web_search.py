from tools.web_search import web_search


def test_web_search_empty_query():
    result = web_search("")
    assert "empty_query" in result
    assert "cannot be empty" in result


def test_web_search_fallback_on_exception(monkeypatch):
    def mock_ddgs(*args, **kwargs):
        raise RuntimeError("Network timeout simulation")

    monkeypatch.setattr("duckduckgo_search.DDGS", mock_ddgs)

    result = web_search("test query")
    assert "search_unavailable" in result
    assert "temporarily unavailable" in result
    assert "fabricate" in result


def test_web_search_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class FlakyDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=4):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return [
                {"title": "Result Title", "body": "Result snippet body.", "href": "https://example.com"},
                {"title": "Second Result", "body": "Another snippet.", "href": "https://example.org"},
            ]

    monkeypatch.setattr("duckduckgo_search.DDGS", FlakyDDGS)

    result = web_search("retry query")

    assert calls["n"] == 2
    assert "Web Search Results" in result
    assert "Result Title" in result
    assert "https://example.com" in result


def test_web_search_no_results_message(monkeypatch):
    class EmptyDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=4):
            return []

    monkeypatch.setattr("duckduckgo_search.DDGS", EmptyDDGS)

    result = web_search("obscure query")
    assert "No relevant results found" in result
