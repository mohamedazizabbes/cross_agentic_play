import json
import logging
import os
from datetime import date
from typing import Dict, List

from config import Config, PROVIDER_API_KEYS, PROVIDERS

logger = logging.getLogger(__name__)


class QuotaTracker:
    """Lightweight local quota tracker backed by a flat JSON file.

    State shape: {provider: {YYYY-MM-DD: call_count, ...}, ...}
    Used purely for visibility (prints "Gemini: 14/20 used today") and to
    help developers spot runs that are burning API quota.
    """

    def __init__(self, path: str = None, daily_limit: int = None, today: str = None):
        self.path = path or Config.QUOTA_STATE_FILE
        self.daily_limit = daily_limit if daily_limit is not None else Config.QUOTA_DAILY_LIMIT
        self._today = today or date.today().isoformat()
        self._state: Dict[str, Dict[str, int]] = self._load()

    def _load(self) -> Dict[str, Dict[str, int]]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def increment(self, provider: str, count: int = 1) -> None:
        day = self._state.setdefault(provider, {})
        day[self._today] = day.get(self._today, 0) + count
        self._save()

    def used_today(self, provider: str) -> int:
        return self._state.get(provider, {}).get(self._today, 0)

    def summary_lines(self) -> List[str]:
        lines = []
        for provider in PROVIDERS:
            used = self.used_today(provider)
            if used or getattr(Config, PROVIDER_API_KEYS[provider], None):
                lines.append(f"{provider.capitalize()}: {used}/{self.daily_limit} used today")
        return lines

    @classmethod
    def print_summary(cls) -> None:
        tracker = cls()
        for line in tracker.summary_lines():
            print(line)
