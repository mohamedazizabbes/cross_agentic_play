# Changelog

All notable changes to AI Debate Arena are documented here.

## [Unreleased]

### Added
- **Live co-judge mode**: `--co-judge` fact-checks each claim in real time as the round runs, then has the LLM draft a verdict ballot for a **human judge to review and submit** (approve as-is, edit a score, override the winner, rewrite reasoning, or request a redraft). The AI never decides on its own — cancelling aborts the run with no verdict. Submitted verdicts are tagged `reviewed_by_human` in the JSON log and exports.
- **Provider fallback**: `utils/llm.py` now retries a quota/429-exhausted call on the next configured provider (Gemini → Groq → OpenRouter, limited to providers with keys set) instead of crashing. New `QuotaExceededError` drives the chain.
- **Exponential retry with backoff** for transient 429 / 5xx errors from any provider (2–3 attempts, `retry_delay * 2^n`).
- **Local quota tracking**: per-provider/per-day call counts in a flat JSON file (`.quota_state.json`), with a summary line printed before each run (e.g. `Gemini: 14/20 used today`). Limit configurable via `QUOTA_DAILY_LIMIT`.
- **On-disk response cache**: LLM responses cached by hash of `(provider, model, system, messages)` under `.cache/` so repeated dev/test runs don't burn API quota. Bypass per-run with the new `--no-cache` flag (or `LLM_CACHE_ENABLED=0`). Tool-calling calls are not cached.
- **Multi-judge panel**: `--multi-judge` asks every configured provider for an independent verdict and aggregates them (averaged scores, majority-vote winner, deduplicated fallacies/unverified claims) via `aggregate_verdicts()`.
- **Human-vs-AI mode**: `--human PRO|CON` lets a human type a side's rebuttals in place of the LLM, slotting into the existing debate loop (empty input falls back to the AI).
- **Transcript export**: `--export <path>` writes the full debate (arguments, claims + citations, verdict, scorecard, reasoning) as Markdown or HTML (by file extension).
- **Secret scanning**: `gitleaks` pre-commit hook (`hooks/pre-commit`, installable via `scripts/install-hooks.sh` / `.ps1`) plus a CI step in `.github/workflows/tests.yml` to catch accidentally committed keys.
- **Docs**: `CHANGELOG.md` and `docs/ARCHITECTURE.md` describing the `llm.py → debater → judge/fact-checker` flow.

### Changed
- `Config` gains `model_for(provider)`, `configured_providers()`, and quota/cache settings (`QUOTA_STATE_FILE`, `QUOTA_DAILY_LIMIT`, `LLM_CACHE_DIR`, `LLM_CACHE_ENABLED`).
- `llm.complete()` accepts optional `provider`, `fallback`, and `use_cache` keyword arguments (existing call signatures unchanged; the `LLM_PROVIDER=gemini|groq|openrouter` contract is preserved).
- `JudgeAgent.evaluate_debate()` accepts an optional `multi_judge` override.

### Fixed
- **CI unit suite passes offline**: `tests/test_llm.py` stubs the Gemini client, so `GeminiProvider` no longer requires a `GOOGLE_API_KEY` in test environments. The `Tests` GitHub Actions workflow (which had been red since the LLM provider abstraction landed) is green again.
