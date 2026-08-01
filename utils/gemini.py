import logging
import time
from typing import Any, Callable
from google import genai
from google.genai import errors
from config import Config

logger = logging.getLogger(__name__)

_client: genai.Client = None


def get_client() -> genai.Client:
    """Returns a process-wide google-genai client (lazy singleton)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.GOOGLE_API_KEY)
    return _client


def send_with_retry(sender: Callable[[], Any], label: str = "Gemini", max_retries: int = 3) -> Any:
    """Invokes `sender()`, retrying on 429 rate limits and transient 5xx errors with backoff."""
    for attempt in range(max_retries):
        try:
            return sender()
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code != 429 and not isinstance(e, errors.ServerError):
                raise
            wait_sec = 15 * (attempt + 1)
            logger.warning(
                f"Rate limit/transient error for {label}. Waiting {wait_sec}s before retry "
                f"(attempt {attempt+1}/{max_retries})..."
            )
            time.sleep(wait_sec)
    # Final fallback attempt; propagates the error if it still fails.
    return sender()
