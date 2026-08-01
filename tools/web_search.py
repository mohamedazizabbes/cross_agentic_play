import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Canonical (OpenAI-style) tool definition used by all LLM providers.
# Converted to a Gemini FunctionDeclaration by the Gemini provider internally.
WEB_SEARCH_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Searches the web for empirical facts, statistics, historical dates, or "
            "verifiable data to back up arguments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string to look up facts or evidence.",
                },
            },
            "required": ["query"],
        },
    },
}


def web_search(query: str, max_results: int = 4, max_retries: int = 2) -> str:
    """
    Performs a web search using DuckDuckGo and returns a formatted snippet string.

    Robustness:
    - Retries with exponential backoff (~1s, ~2s) on transient failures.
    - Returns a structured JSON error result (rather than raising) once retries are exhausted,
      so the calling model can fall back to reasoning without stalling the pipeline.
    """
    if not query or not query.strip():
        return '{"error": "empty_query", "message": "Search query cannot be empty."}'

    results: List[Dict[str, Any]] = []
    last_error: Exception = None

    for attempt in range(max_retries + 1):
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query.strip(), max_results=max_results))
            break
        except Exception as e:
            last_error = e
            if attempt >= max_retries:
                break
            wait_sec = 1 * (2 ** attempt)
            logger.warning(
                f"web_search attempt {attempt + 1}/{max_retries + 1} failed for query '{query}': {e}. "
                f"Retrying in {wait_sec}s..."
            )
            time.sleep(wait_sec)

    if last_error is not None and not results:
        logger.warning(f"web_search exhausted retries for query '{query}': {last_error}")
        return (
            '{"error": "search_unavailable", "message": "Web search is temporarily unavailable. '
            'Do NOT fabricate sources. Proceed using logical reasoning and mark factual claims without sources."}'
        )

    if not results:
        return f"Web search results for '{query}': No relevant results found."

    formatted_snippets: List[str] = []
    for i, res in enumerate(results, 1):
        title = res.get("title", "No Title")
        snippet = res.get("body", "No Snippet")
        href = res.get("href", "")
        formatted_snippets.append(f"[{i}] {title}\n    Snippet: {snippet}\n    Source: {href}")

    return f"Web Search Results for '{query}':\n\n" + "\n\n".join(formatted_snippets)
