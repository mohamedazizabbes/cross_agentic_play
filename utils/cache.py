import hashlib
import json
import logging
import os
from typing import Any, List, Optional

from config import Config

logger = logging.getLogger(__name__)


class ResponseCache:
    """On-disk cache of LLM responses keyed by hash of (provider, model, system, messages).

    Lets repeated dev/test runs reuse prior answers instead of burning API quota.
    Only `complete()` calls without tool execution are cached, since tool results
    would otherwise go stale.
    """

    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or Config.LLM_CACHE_DIR

    @staticmethod
    def _key(
        provider: str, model: str, system: Optional[str], messages: List[dict], json_mode: bool, response_schema: Any
    ) -> str:
        payload = {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": messages,
            "json_mode": json_mode,
        }
        if response_schema is not None:
            schema = getattr(response_schema, "model_json_schema", lambda: response_schema)()
            payload["schema"] = schema
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.json")

    def get(
        self,
        provider: str,
        model: str,
        system: Optional[str],
        messages: List[dict],
        json_mode: bool = False,
        response_schema: Any = None,
    ) -> Optional[str]:
        path = self._path(self._key(provider, model, system, messages, json_mode, response_schema))
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("response")
        except (OSError, ValueError):
            return None

    def set(
        self,
        provider: str,
        model: str,
        system: Optional[str],
        messages: List[dict],
        response: str,
        json_mode: bool = False,
        response_schema: Any = None,
    ) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        path = self._path(self._key(provider, model, system, messages, json_mode, response_schema))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"response": response}, f, ensure_ascii=False)
