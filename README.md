# AI Debate Arena

Two agents debate any proposition — PRO vs CON. A third agent independently fact-checks their claims with live web search, and a judge scores the round on four axes and names a winner. Works with Gemini, Groq, or OpenRouter (free keys supported).

The same fact-checking engine also runs standalone — as a local API, and as a browser extension that fact-checks any text you highlight on the web.

## What's included

1. **CLI — the core product.** Run a full PRO vs CON debate on any topic, fact-checked and judged.
2. **Fact-check API (`api.py`).** The debate engine's fact-checker exposed as a standalone `/verify` endpoint — point it at any text, not just a debate.
3. **Chrome extension.** A bonus feature built on top of the API — highlight text on any webpage, right-click, fact-check it inline.

## Why not just ask ChatGPT or Claude?

- Two agents arguing opposite sides produces sharper, more specific claims than one model reasoning alone — there's someone on the other side whose job is to find the weak point.
- Every factual claim gets checked by a separate pass against live search, not just accepted because it sounds confident.
- The judge scores across four separate axes and shows its reasoning before naming a winner — not a one-line vibe verdict.
- Every run logs to structured JSON — reproducible and diffable, not a chat reply that's gone once you close the tab.

## Quick start

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your API key (see Configuration below)
```

Run a debate:
```bash
python main.py "AI will replace all jobs" --rounds 1
python main.py "Coffee is the second most traded commodity after oil"
python main.py "Nuclear energy is the cleanest scalable power source" --co-judge
```

The CLI prints the full debate transcript, fact-check results, judge reasoning, scores, and winner. Logs are saved to `logs/debate_<timestamp>.json`.

## Running the fact-check API

Built on the same fact-checking engine as the CLI, exposed standalone:
```bash
python api.py
```
Runs on `http://localhost:5000`. Two endpoints:
- `POST /verify` — send `{ "text": "..." }` to extract and fact-check claims.
- `GET /health` — returns `{"status": "ok"}`.

## Browser extension

1. Start the API: `python api.py`
2. Open `chrome://extensions` in Chrome, enable **Developer mode**.
3. Click **Load unpacked** and select the `extension/` folder.
4. Highlight text on any page, right-click, select **Fact-check this**.

Local developer-mode extension only — requires `api.py` running on your machine. Not published to the Chrome Web Store.

## Configuration

The engine supports three LLM providers. Set `LLM_PROVIDER` in `.env` to choose one — only that provider's API key is required.

| Variable | Default | Required | Description |
|---|---|---|---|
| `LLM_PROVIDER` | `gemini` | No | Backend to use: `gemini`, `groq`, or `openrouter`. |
| `GOOGLE_API_KEY` | — | If using Gemini | Key from Google AI Studio. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | No | Gemini model name. |
| `GROQ_API_KEY` | — | If using Groq | Free key from console.groq.com. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | No | Groq model name. |
| `OPENROUTER_API_KEY` | — | If using OpenRouter | Free key from openrouter.ai. |
| `OPENROUTER_MODEL` | `deepseek/deepseek-chat-v3-0324:free` | No | OpenRouter model name; `:free` selects a no-cost tier. |
| `DEFAULT_REBUTTAL_ROUNDS` | `2` | No | Rebuttal rounds per debate when `--rounds` isn't passed. |
| `LOG_DIR` | `logs` | No | Directory where debate transcripts are written as JSON. |

Example configuration using Groq:
```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

## Testing

```bash
pytest                  # unit tests — fully offline, no API key required
pytest -m integration   # end-to-end tests against a live provider — requires a configured API key
```

Unit tests cover claim parsing, judge output validation, and orchestration logic against a stubbed LLM client. Integration tests run a real debate against whichever provider is configured in `.env`, and are excluded from the default run so CI stays fast and offline.
