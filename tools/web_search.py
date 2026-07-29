import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Function declaration for Gemini function calling API
web_search_declaration = {
    "name": "web_search",
    "description": "Searches the web for empirical facts, statistics, historical dates, or verifiable data to back up arguments.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "The search query string to look up facts or evidence."
            }
        },
        "required": ["query"]
    }
}


def web_search(query: str, max_results: int = 4) -> str:
    """
    Performs a web search using DuckDuckGo and returns a formatted snippet string.
    Includes robust exception handling for network issues or rate limiting.
    """
    if not query or not query.strip():
        return "Search error: Query cannot be empty."

    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query.strip(), max_results=max_results))
        
        if not results:
            return f"Search result for '{query}': No relevant web results found."

        formatted_snippets: List[str] = []
        for i, res in enumerate(results, 1):
            title = res.get("title", "No Title")
            snippet = res.get("body", "No Snippet")
            href = res.get("href", "")
            formatted_snippets.append(f"[{i}] {title}\n    Snippet: {snippet}\n    Source: {href}")

        return f"Web Search Results for '{query}':\n\n" + "\n\n".join(formatted_snippets)

    except Exception as e:
        logger.warning(f"web_search failed for query '{query}': {e}")
        return f"Search notice: Web search service temporarily unavailable ({type(e).__name__}). Proceed using logical reasoning and general knowledge, clearly identifying unsupported assumptions."
