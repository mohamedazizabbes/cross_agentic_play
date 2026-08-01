import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI, APIError as OpenAIAPIError
from google.genai import types as genai_types
from google.genai import errors as genai_errors

from config import Config
from utils.gemini import get_client as get_gemini_client

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def _status_code(e: BaseException) -> Optional[int]:
    for attr in ("status_code", "code"):
        val = getattr(e, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_retryable(e: BaseException) -> bool:
    code = _status_code(e)
    if code is not None:
        return code == 429 or 500 <= code < 600
    return "Rate limit" in str(e) or "quota" in str(e).lower()


def send_with_retry(sender: Callable[[], Any], label: str = "request", max_retries: int = 3) -> Any:
    """Invokes `sender()`, retrying on 429 rate limits and transient 5xx errors with backoff."""
    for attempt in range(max_retries):
        try:
            return sender()
        except (genai_errors.APIError, OpenAIAPIError) as e:
            if not _is_retryable(e):
                raise
            wait_sec = 15 * (attempt + 1)
            logger.warning(
                f"Rate limit/transient error for {label}. Waiting {wait_sec}s before retry "
                f"(attempt {attempt+1}/{max_retries})..."
            )
            time.sleep(wait_sec)
    # Final fallback attempt; propagates the error if it still fails.
    return sender()


def _to_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    props = {k: _to_schema(v) for k, v in schema.get("properties", {}).items()}
    kwargs: Dict[str, Any] = {}
    if props:
        kwargs["properties"] = props
    if schema.get("required"):
        kwargs["required"] = schema["required"]
    if schema.get("description"):
        kwargs["description"] = schema["description"]
    t = schema.get("type")
    if t:
        kwargs["type"] = genai_types.Type(t.upper())
    return genai_types.Schema(**kwargs)


class GeminiProvider:
    def __init__(self):
        self.client = get_gemini_client()

    @staticmethod
    def _to_content(message: Dict[str, Any]) -> genai_types.Content:
        role = message.get("role")
        if role == "system":
            return None
        if role in ("tool",):
            return None
        content = message.get("content") or ""
        genai_role = "user" if role in ("user", "tool") else "model"
        return genai_types.Content(role=genai_role, parts=[genai_types.Part.from_text(text=content)])

    def _to_tools(self, tools: List[dict]) -> List[genai_types.Tool]:
        declarations = []
        for tool in tools:
            fn = tool.get("function", tool)
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=_to_schema(fn.get("parameters", {})),
                )
            )
        return [genai_types.Tool(function_declarations=declarations)]

    def complete(
        self,
        model: str,
        messages: List[dict],
        system: Optional[str] = None,
        tools: Optional[List[dict]] = None,
        execute_tool: Optional[Callable] = None,
        json_mode: bool = False,
        response_schema: Any = None,
        max_tool_calls: int = 5,
    ) -> str:
        contents = [c for c in (self._to_content(m) for m in messages) if c is not None]

        config_kwargs: Dict[str, Any] = {}
        if system:
            config_kwargs["system_instruction"] = system
        if tools:
            config_kwargs["tools"] = self._to_tools(tools)
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            if response_schema is not None:
                config_kwargs["response_schema"] = response_schema
        config = genai_types.GenerateContentConfig(**config_kwargs)

        response = send_with_retry(
            lambda: self.client.models.generate_content(model=model, contents=contents, config=config),
            label="chat",
        )

        for _ in range(max_tool_calls):
            parts = list((response.candidates[0].content.parts or [])) if response and response.candidates else []
            calls = [p.function_call for p in parts if p.function_call]
            if not calls:
                return response.text.strip() if response and response.text else ""

            function_responses = []
            for fc in calls:
                args = dict(fc.args or {})
                logger.info(f"Executing tool call: {fc.name}({args})")
                result = execute_tool(**args) if execute_tool else {"error": "no_tool_executor"}
                function_responses.append(
                    genai_types.Part(
                        function_response=genai_types.FunctionResponse(name=fc.name, response={"result": result})
                    )
                )
            contents.append(genai_types.Content(role="user", parts=function_responses))
            response = send_with_retry(
                lambda: self.client.models.generate_content(model=model, contents=contents, config=config),
                label="chat (tool results)",
            )

        return response.text.strip() if response and response.text else ""


class OpenAICompatProvider:
    BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    API_KEY_ATTRS = {
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    def __init__(self, provider: str):
        self.provider = provider
        api_key = getattr(Config, self.API_KEY_ATTRS[provider])
        if not api_key:
            raise LLMError(f"{provider}: API key not set. Set {self.API_KEY_ATTRS[provider]} in your .env file.")
        self.client = OpenAI(base_url=self.BASE_URLS[provider], api_key=api_key)

    @staticmethod
    def _dump_tool_call(tc) -> dict:
        return {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
        }

    def _create(self, model: str, messages: List[dict], kwargs: Dict[str, Any], label: str = "chat"):
        return send_with_retry(
            lambda: self.client.chat.completions.create(model=model, messages=messages, **kwargs),
            label=label,
        )

    def complete(
        self,
        model: str,
        messages: List[dict],
        system: Optional[str] = None,
        tools: Optional[List[dict]] = None,
        execute_tool: Optional[Callable] = None,
        json_mode: bool = False,
        response_schema: Any = None,
        max_tool_calls: int = 5,
    ) -> str:
        msgs: List[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        kwargs: Dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        if json_mode:
            schema = response_schema.model_json_schema() if hasattr(response_schema, "model_json_schema") else response_schema
            if schema:
                kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "verdict", "schema": schema}}
            else:
                kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._create(model, msgs, kwargs)
        except OpenAIAPIError as e:
            if tools and _status_code(e) == 400:
                logger.warning(
                    f"{self.provider}: model '{model}' rejected function calling ({e}); "
                    "falling back to a debate without live web search."
                )
                kwargs.pop("tools", None)
                response = self._create(model, msgs, kwargs)
            elif json_mode and _status_code(e) == 400:
                logger.warning(
                    f"{self.provider}: model '{model}' rejected json_schema ({e}); "
                    "falling back to plain json_object mode."
                )
                kwargs["response_format"] = {"type": "json_object"}
                response = self._create(model, msgs, kwargs)
            else:
                raise

        for _ in range(max_tool_calls):
            msg = response.choices[0].message
            if msg.tool_calls and execute_tool:
                msgs.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [self._dump_tool_call(tc) for tc in msg.tool_calls],
                    }
                )
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    logger.info(f"Executing tool call: {tc.function.name}({args})")
                    result = execute_tool(**args)
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"result": result})})
                response = self._create(model, msgs, kwargs, label="chat (tool results)")
            else:
                return (msg.content or "").strip()

        return (response.choices[0].message.content or "").strip()


_providers: Dict[str, Any] = {}


def _get_provider() -> Any:
    provider = Config.LLM_PROVIDER
    if provider not in _providers:
        if provider == "gemini":
            _providers[provider] = GeminiProvider()
        elif provider in ("groq", "openrouter"):
            _providers[provider] = OpenAICompatProvider(provider)
        else:
            raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Choose from: gemini, groq, openrouter.")
    return _providers[provider]


def complete(
    model: str,
    messages: List[dict],
    system: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    execute_tool: Optional[Callable] = None,
    json_mode: bool = False,
    response_schema: Any = None,
    max_tool_calls: int = 5,
) -> str:
    """Sends a chat request through the configured LLM provider (gemini | groq | openrouter).

    - `messages`: OpenAI-style list of `{"role": "user"|"assistant"|"system", "content": str}` dicts.
    - `tools`: OpenAI-style tool definitions (`{"type": "function", "function": {...}}`).
    - `execute_tool`: if provided, tool calls are executed in a loop until the model replies.
    - `json_mode`: request a JSON-encoded response (`response_schema` enforced where the provider supports it).
    """
    return _get_provider().complete(
        model=model,
        messages=messages,
        system=system,
        tools=tools,
        execute_tool=execute_tool,
        json_mode=json_mode,
        response_schema=response_schema,
        max_tool_calls=max_tool_calls,
    )
