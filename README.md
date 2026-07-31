# AI Debate Arena

A domain-agnostic multi-agent debate platform. Two AI debaters argue opposing stances on any
proposition, backed by live web search, an independent fact-checking pass, and a judge that
scores the debate on four axes and declares a winner.

Built with the Google **`google-genai`** SDK (Gemini) and DuckDuckGo for live evidence retrieval.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │            DebateOrchestrator              │
                    │  (single process · turn-based · stateless) │
                    └─────────────────────────────────────────────┘
                                     │
      ┌──────────────┬───────────────┼──────────────────┬────────────────┐
      ▼              ▼               ▼                  ▼                ▼
 ┌─────────┐   ┌─────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────┐
 │Debater A│   │Debater B│   │ FactChecker │   │  JudgeAgent  │   │  Logger  │
 │   PRO   │   │   CON   │   │            │   │              │   │          │
 └────┬────┘   └────┬────┘   └──────┬─────┘   └──────┬───────┘   └────┬─────┘
     │              │               │                │                │
     │  Gemini chat │               │  Gemini one-   │  Gemini        │  JSON log
     │  session +   │               │  shot + DDG    │  structured    │  → logs/
     │  web_search  │               │  search        │  output schema │  debate_*.json
     └──────────────┴───────────────┴────────────────┴────────────────┘
```

### How a debate flows

1. **Opening statements** — both debaters state their core positions.
2. **Rebuttal rounds** (`--rounds N`, default 2) — each debater responds directly to the opponent's
   latest turn, refuting specific claims by their exact claim ID (e.g. `CON-1-2`).
3. **Closing statements** — each debater synthesizes their case; no new arguments.
4. **Fact-checking pass** — a dedicated `FactChecker` verifies every factual claim that carries a
   source: it searches the web, asks Gemini whether the evidence supports/contradicts the claim,
   and annotates each claim as `verified` / `contradicted` / `unchecked` in place.
5. **Judging** — the `JudgeAgent` reviews the full annotated transcript, flags fallacies, scores
   both debaters on four axes, and returns a schema-validated verdict (`PRO` / `CON` / `TIE`).

Every turn appends a `[CLAIMS START]…[CLAIMS END]` block of structured claims (one per line,
`<number>|<FACTUAL|OPINION>|"<text>"|<sources>|<rebuts>`), so downstream agents can reference
specific claims instead of free text.

## Repository structure

```
agents/
  debater.py       DebaterAgent: Gemini chat session per debater + manual web_search tool loop
  fact_checker.py  FactChecker: verifies sourced factual claims before judging
  judge.py         JudgeAgent: structured-output verdict (Pydantic response_schema) + re-ask loop
  prompts.py       System prompts: debater search policy, claim output format, judge rubric
tools/
  web_search.py    web_search() (DuckDuckGo, retry + no-fabrication policy) and its Gemini
                   FunctionDeclaration / Tool definition
utils/
  gemini.py        Shared google-genai client singleton, send_with_retry (429/5xx backoff),
                   manual function-calling loop (send_message_with_function_calling)
  logger.py        Logging setup + structured JSON log writer
config.py          Env-driven config (API key, model, rounds, log dir)
models.py          Dataclasses (Claim, DebateTurn, DebateLog, JudgeVerdict), Pydantic
                   JudgeOutputSchema, claim parsing, transcript formatting
orchestrator.py    DebateOrchestrator: the turn-based pipeline state machine
main.py            CLI entry point: runs the pipeline, prints summary, saves JSON log
tests/             Unit tests + gated live integration tests
```

### Key design decisions

- **Single process, stateless, turn-based.** No MCP, no RAG, no agent-to-agent messaging. The
  orchestrator holds the full transcript and injects it into every prompt.
- **Full-transcript context.** Debaters see the entire debate so far (formatted with claim IDs) in
  every turn — no context loss across rounds.
- **Structured claims, tolerant parsing.** Claim blocks are parsed per-line; malformed lines are
  skipped with a warning rather than failing the turn.
- **Search policy.** `web_search` is only for FACTUAL claims; if search is unavailable the model is
  instructed to never fabricate URLs and to fall back to logical reasoning.
- **Judge output is schema-enforced.** Gemini returns the verdict via `response_schema`
  (`JudgeOutputSchema`); invalid JSON triggers a re-ask loop (up to 2), then a tolerant text fallback.
- **Resilience.** 429/5xx retries with backoff (`utils/gemini.py`), and `web_search` returns a
  structured error object instead of raising once retries are exhausted.

## Installation

1. Clone & create a virtual environment:
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment — copy `.env.example` to `.env`:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

| Variable | Default | Description |
| --- | --- | --- |
| `GOOGLE_API_KEY` | *(required)* | Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used by all agents |
| `DEFAULT_REBUTTAL_ROUNDS` | `2` | Rebuttal rounds when `--rounds` is not passed |
| `LOG_DIR` | `logs` | Directory for structured JSON debate logs |

> Note: the free Gemini tier limits requests per day per model (e.g. 20 req/day for
> `gemini-2.5-flash`). A full debate consumes several calls, so budget accordingly.

## Usage

```bash
python main.py "Universal Basic Income should be implemented globally"
python main.py "The Great Wall of China is visible from low Earth orbit" --rounds 1
```

The run prints a phase-by-phase transcript (speaker, phase, prose, and structured claims), the
judge's reasoning, flagged fallacies, per-axis scores, and the winner. A full structured log is
saved to `logs/debate_<timestamp>.json`:

```json
{
  "topic": "...",
  "timestamp": "...",
  "model_used": "gemini-2.5-flash",
  "turns": [ { "speaker": "Debater A (PRO)", "role": "PRO", "phase": "OPENING",
               "claims": [ { "claim_id": "PRO-1-1", "is_factual": true, "sources": ["..."],
                             "rebuts_claim_id": null, "verified": true,
                             "verification_note": "YES: ..." } ], "raw_text": "..." } ],
  "verdict": { "winner": "PRO", "scores": { "logical_coherence": {"A": 8.5, "B": 8.0}, ... },
               "reasoning": "...", "flagged_fallacies": [...],
               "unverified_or_contradicted_claims": [...] }
}
```

## Testing

```bash
pytest                    # unit tests (live API tests deselected by default)
pytest -m integration     # live end-to-end debate (calls Gemini + DuckDuckGo)
```

The live integration test (`tests/test_pipeline_golden.py`) runs the full
orchestrator → fact-check → judge → log pipeline on real APIs and is gated behind the
`integration` marker so unit runs stay fast and offline.
