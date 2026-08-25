import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI, APIError as OpenAIAPIError
from google.genai import types as genai_types
from google.genai import errors as genai_errors
import anthropic

from config import Config
from utils.cache import ResponseCache
from utils.gemini import get_client as get_gemini_client
from utils.quota import QuotaTracker

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class QuotaExceededError(LLMError):
    """Raised when a provider keeps returning 429/quota errors after retries.

    `complete()` catches this to retry the same call on the next configured provider.
    """


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


def _is_quota_error(e: BaseException) -> bool:
    code = _status_code(e)
    if code is not None:
        return code == 429
    msg = str(e).lower()
    return "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg or "429" in msg


def send_with_retry(
    sender: Callable[[], Any],
    label: str = "request",
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> Any:
    """Invokes `sender()`, retrying 429 rate limits and transient 5xx errors with
    exponential backoff. If a quota/429 error still persists, raises QuotaExceededError
    so the caller can fall back to another provider. Other transient errors propagate
    as-is after retries are exhausted."""
    last_error: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return sender()
        except (genai_errors.APIError, OpenAIAPIError) as e:
            if not _is_retryable(e):
                raise
            last_error = e
            if attempt == max_retries - 1:
                break
            wait_sec = retry_delay * (2**attempt)
            logger.warning(
                f"Rate limit/transient error for {label}. Waiting {wait_sec:.0f}s before retry "
                f"(attempt {attempt + 1}/{max_retries})..."
            )
            time.sleep(wait_sec)
    if _is_quota_error(last_error):
        raise QuotaExceededError(f"Quota exceeded for {label}: {last_error}") from last_error
    raise last_error


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
            schema = (
                response_schema.model_json_schema()
                if hasattr(response_schema, "model_json_schema")
                else response_schema
            )
            if schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "verdict", "schema": schema},
                }
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


class OpenAIProvider:
    def __init__(self):
        api_key = Config.OPENAI_API_KEY
        if not api_key:
            raise LLMError("OpenAI API key not set. Set OPENAI_API_KEY in your .env file.")
        self.client = OpenAI(api_key=api_key)

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
            schema = (
                response_schema.model_json_schema()
                if hasattr(response_schema, "model_json_schema")
                else response_schema
            )
            if schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "verdict", "schema": schema},
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._create(model, msgs, kwargs)
        except OpenAIAPIError as e:
            if tools and _status_code(e) == 400:
                logger.warning(f"openai: model '{model}' rejected function calling; falling back to no tools.")
                kwargs.pop("tools", None)
                response = self._create(model, msgs, kwargs)
            elif json_mode and _status_code(e) == 400:
                logger.warning(f"openai: model '{model}' rejected json_schema; falling back to json_object.")
                kwargs["response_format"] = {"type": "json_object"}
                response = self._create(model, msgs, kwargs)
            else:
                raise

        for _ in range(max_tool_calls):
            msg = response.choices[0].message
            if msg.tool_calls and execute_tool:
                msgs.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [self._dump_tool_call(tc) for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    logger.info(f"Executing tool call: {tc.function.name}({args})")
                    result = execute_tool(**args)
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"result": result})})
                response = self._create(model, msgs, kwargs, label="chat (tool results)")
            else:
                return (msg.content or "").strip()

        return (response.choices[0].message.content or "").strip()


class AnthropicProvider:
    def __init__(self):
        api_key = Config.ANTHROPIC_API_KEY
        if not api_key:
            raise LLMError("Anthropic API key not set. Set ANTHROPIC_API_KEY in your .env file.")
        self.client = anthropic.Anthropic(api_key=api_key)

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
        kwargs: Dict[str, Any] = {"model": model, "max_tokens": 4096}
        if system:
            kwargs["system"] = system

        anthropic_msgs = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content") or ""
            if role in ("user", "assistant"):
                anthropic_msgs.append({"role": role, "content": content})

        if not anthropic_msgs:
            anthropic_msgs.append({"role": "user", "content": "hello"})

        kwargs["messages"] = anthropic_msgs

        if tools:
            kwargs["tools"] = [
                {
                    "name": t.get("function", {}).get("name", t.get("name", "")),
                    "description": t.get("function", {}).get("description", t.get("description", "")),
                    "input_schema": t.get("function", {}).get("parameters", t.get("parameters", {})),
                }
                for t in tools
            ]

        if json_mode:
            if system:
                kwargs["system"] = system + "\nRespond with valid JSON only."
            else:
                kwargs["system"] = "Respond with valid JSON only."

        def do_call():
            return self.client.messages.create(**kwargs)

        response = send_with_retry(do_call, label="chat")

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(block)

        for _ in range(max_tool_calls):
            if tool_calls and execute_tool:
                anthropic_msgs.append({"role": "assistant", "content": response.content})
                tool_results = []
                for tc in tool_calls:
                    logger.info(f"Executing tool call: {tc.name}({tc.input})")
                    result = execute_tool(**tc.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": json.dumps({"result": result}),
                    })
                anthropic_msgs.append({"role": "user", "content": tool_results})
                kwargs["messages"] = anthropic_msgs
                response = send_with_retry(do_call, label="chat (tool results)")
                text = ""
                tool_calls = []
                for block in response.content:
                    if block.type == "text":
                        text += block.text
                    elif block.type == "tool_use":
                        tool_calls.append(block)
            else:
                return text.strip()

        return text.strip()


_providers: Dict[str, Any] = {}
_cache_enabled: Optional[bool] = None


def set_cache_enabled(enabled: bool) -> None:
    """Globally toggles the on-disk response cache (used by the --no-cache CLI flag)."""
    global _cache_enabled
    _cache_enabled = enabled


def _cache_is_enabled() -> bool:
    if _cache_enabled is not None:
        return _cache_enabled
    return Config.LLM_CACHE_ENABLED


def _get_provider(name: str = None) -> Any:
    provider = name or Config.LLM_PROVIDER
    if provider not in _providers:
        if provider == "gemini":
            _providers[provider] = GeminiProvider()
        elif provider == "openai":
            _providers[provider] = OpenAIProvider()
        elif provider == "anthropic":
            _providers[provider] = AnthropicProvider()
        elif provider in ("groq", "openrouter"):
            _providers[provider] = OpenAICompatProvider(provider)
        else:
            raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Choose from: gemini, openai, anthropic, groq, openrouter.")
    return _providers[provider]


def _provider_chain(provider: Optional[str] = None, fallback: bool = True) -> List[str]:
    """Ordered list of providers to try for a call.

    Starts at `provider` (or Config.LLM_PROVIDER), then follows the canonical provider
    order limited to providers that have an API key configured. Cross-provider fallback
    is disabled when `fallback=False` (used by the multi-judge panel so each verdict is
    independent).
    """
    start = provider or Config.LLM_PROVIDER
    chain = [start]
    if fallback:
        chain.extend(p for p in Config.configured_providers() if p != start)
    return chain


def complete(
    model: str,
    messages: List[dict],
    system: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    execute_tool: Optional[Callable] = None,
    json_mode: bool = False,
    response_schema: Any = None,
    max_tool_calls: int = 5,
    provider: Optional[str] = None,
    fallback: bool = True,
    use_cache: Optional[bool] = None,
) -> str:
    """Sends a chat request through the configured LLM provider (gemini | groq | openrouter).

    - `messages`: OpenAI-style list of `{"role": "user"|"assistant"|"system", "content": str}` dicts.
    - `tools`: OpenAI-style tool definitions (`{"type": "function", "function": {...}}`).
    - `execute_tool`: if provided, tool calls are executed in a loop until the model replies.
    - `json_mode`: request a JSON-encoded response (`response_schema` enforced where the provider supports it).
    - `provider`: override the starting provider (must be in PROVIDERS).
    - `fallback`: if True (default), a persistent quota/429 error falls back to the next configured provider.
    - `use_cache`: override the on-disk response cache (defaults to Config.LLM_CACHE_ENABLED / --no-cache).
    """
    cache_enabled = use_cache if use_cache is not None else _cache_is_enabled()
    cache = ResponseCache() if cache_enabled else None
    quota = QuotaTracker()
    cacheable = cache_enabled and not tools

    last_error: Optional[BaseException] = None
    for pname in _provider_chain(provider, fallback):
        if cacheable:
            hit = cache.get(pname, model, system, messages, json_mode, response_schema)
            if hit is not None:
                logger.info(f"Cache hit for {pname}/{model}; skipping API call.")
                return hit
        try:
            out = _get_provider(pname).complete(
                model=model,
                messages=messages,
                system=system,
                tools=tools,
                execute_tool=execute_tool,
                json_mode=json_mode,
                response_schema=response_schema,
                max_tool_calls=max_tool_calls,
            )
        except QuotaExceededError as e:
            logger.warning(f"{pname}: quota exceeded ({e}); trying next provider.")
            last_error = e
            continue
        if cacheable:
            cache.set(pname, model, system, messages, out, json_mode, response_schema)
        quota.increment(pname)
        return out

    if last_error is not None:
        raise last_error
    raise LLMError(
        f"No LLM providers available (LLM_PROVIDER={Config.LLM_PROVIDER}, configured={Config.configured_providers()})."
    )
