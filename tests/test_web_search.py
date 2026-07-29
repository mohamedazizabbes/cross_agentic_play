from tools.web_search import web_search


def test_web_search_empty_query():
    result = web_search("")
    assert "Search error" in result


def test_web_search_fallback_on_exception(monkeypatch):
    def mock_ddgs(*args, **kwargs):
        raise RuntimeError("Network timeout simulation")

    monkeypatch.setattr("duckduckgo_search.DDGS", mock_ddgs)
    
    result = web_search("test query")
    assert "Search notice" in result
    assert "temporarily unavailable" in result
