# Architecture

Short tour of the data flow through the debate pipeline.

```
main.py (CLI)
   │  parses flags (--rounds, --no-cache, --multi-judge, --human, --export)
   ▼
orchestrator.py (DebateOrchestrator)
   │  drives the turn-based debate loop
   ├──► agents/debater.py  (DebaterAgent, PRO + CON)
   │        │  build prompt + maintain per-debater message history
   │        ▼
   │     utils/llm.py::complete()   ──►  provider (Gemini / Groq / OpenRouter)
   │        │   • response cache lookup (skip if --no-cache)
   │        │   • exponential retry + backoff on 429/5xx
   │        │   • fallback to next configured provider on quota/429
   │        │   • increments per-provider/per-day quota tracker
   │        └──► returns text; claims parsed via models.parse_claims()
   │
   ├──► agents/fact_checker.py (FactChecker)
   │        │  for each sourced FACTUAL claim: tools/web_search.py + llm.complete()
   │        └──► annotates Claim.verified / verification_note in place
   │
   └──► agents/judge.py (JudgeAgent)
            │  json_mode + response_schema (structured verdict), re-ask loop
            │  optional --multi-judge: one verdict per configured provider,
            │  combined by aggregate_verdicts() (averaged scores + majority winner)
            └──► models.JudgeVerdict
   ▼
models.py (DebateLog, turns, claims, verdict)
   ▼
utils/logger.py  → save_debate_log() (JSON in logs/) + export_debate() (Markdown/HTML)
```

## Key modules

- `utils/llm.py` — provider abstraction. `GeminiProvider` (google-genai) and
  `OpenAICompatProvider` (Groq / OpenRouter) expose the same `complete()` interface.
  `send_with_retry()` retries transient 429/5xx errors with exponential backoff and
  surfaces a persistent quota/429 as `QuotaExceededError`, which the module-level
  `complete()` uses to fail over to the next provider that has an API key configured.
- `utils/cache.py` — on-disk response cache keyed by hash of
  `(provider, model, system, messages, json_mode, schema)`. Tool-calling calls are
  never cached because live search results would go stale.
- `utils/quota.py` — flat-JSON per-provider/per-day usage counter that prints a
  summary line before each run.
- `agents/debater.py` — generates one turn per debater; with `human=True` the
  REBUTTAL phases read a typed rebuttal from stdin instead of calling the LLM.
- `agents/fact_checker.py` — verifies sourced factual claims using web search
  snippets, writing `YES/NO/PARTIAL` verdicts back onto each claim.
- `agents/judge.py` — produces a schema-validated `JudgeVerdict`; the multi-judge
  panel queries every configured provider and aggregates the results.
- `models.py` — dataclasses/Pydantic schemas shared across agents.

## Testing

Unit tests are offline (no API keys, no network): `pytest`. Live end-to-end runs are
gated behind the `integration` marker and need `GOOGLE_API_KEY`. The retry/cache/quota
paths are unit-tested against stub providers.
