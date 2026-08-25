import os
from dotenv import load_dotenv

load_dotenv()

PROVIDERS = ("gemini", "openai", "anthropic", "groq", "openrouter")

# Maps provider name -> Config attribute holding its API key.
PROVIDER_API_KEYS = {
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class Config:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
    DEFAULT_REBUTTAL_ROUNDS = int(os.getenv("DEFAULT_REBUTTAL_ROUNDS", "2"))
    LOG_DIR = os.getenv("LOG_DIR", "logs")

    # Local quota tracking (per-provider, per-day)
    QUOTA_STATE_FILE = os.getenv("QUOTA_STATE_FILE", ".quota_state.json")
    QUOTA_DAILY_LIMIT = int(os.getenv("QUOTA_DAILY_LIMIT", "20"))

    # On-disk response cache
    LLM_CACHE_DIR = os.getenv("LLM_CACHE_DIR", ".cache")
    LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")

    @classmethod
    def model_for(cls, provider):
        return {
            "gemini": cls.GEMINI_MODEL,
            "openai": cls.OPENAI_MODEL,
            "anthropic": cls.ANTHROPIC_MODEL,
            "groq": cls.GROQ_MODEL,
            "openrouter": cls.OPENROUTER_MODEL,
        }.get(provider, cls.GEMINI_MODEL)

    @classmethod
    def llm_model(cls):
        return cls.model_for(cls.LLM_PROVIDER)

    @classmethod
    def configured_providers(cls):
        """Providers in canonical order that currently have an API key set."""
        return [p for p in PROVIDERS if getattr(cls, PROVIDER_API_KEYS[p])]

    @classmethod
    def validate(cls):
        if cls.LLM_PROVIDER not in PROVIDERS:
            raise ValueError(f"LLM_PROVIDER must be one of {PROVIDERS}, got '{cls.LLM_PROVIDER}'.")
        required_key = {
            "gemini": "GOOGLE_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(cls.LLM_PROVIDER)
        api_key = getattr(cls, required_key, "")
        if not api_key:
            raise ValueError(
                f"{required_key} environment variable is required when LLM_PROVIDER={cls.LLM_PROVIDER}. "
                "Please set it in your .env file."
            )
