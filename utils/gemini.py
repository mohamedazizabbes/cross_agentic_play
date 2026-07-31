import logging
import time
from typing import Any, Callable
from google import genai
from google.genai import types, errors
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


def _content_parts(response) -> list:
    if not response or not response.candidates:
        return []
    return list(response.candidates[0].content.parts or [])


def send_message_with_function_calling(chat, message, execute_tool, max_function_calls: int = 5) -> types.GenerateContentResponse:
    """Sends a chat message, automatically executing any tool (function_call) parts the model emits.

    The google-genai SDK does not auto-execute local Python tools, so we loop manually:
    for every function_call part the model emits, run the tool and feed the result back as a
    function_response until the model returns a final (text) answer.
    """
    response = send_with_retry(lambda: chat.send_message(message), label="chat")

    for _ in range(max_function_calls):
        parts = _content_parts(response)
        calls = [p.function_call for p in parts if p.function_call]
        if not calls:
            return response

        function_responses = []
        for fc in calls:
            args = dict(fc.args or {})
            logger.info(f"Executing tool call: {fc.name}({args})")
            result = execute_tool(**args)
            function_responses.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": result},
                    )
                )
            )

        response = send_with_retry(
            lambda: chat.send_message(types.Content(parts=function_responses)),
            label="chat (tool results)",
        )

    return response
