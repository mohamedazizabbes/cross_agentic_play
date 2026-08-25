# AI Debate Arena

Two agents debate any proposition — PRO vs CON. A third agent independently fact-checks their claims with live web search, and a judge scores the round on four axes and names a winner. Works with **Gemini, Groq, or OpenRouter** (free keys supported).

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

```bash
python api.py
```

Runs on `http://localhost:5000`. Two endpoints:

- **POST `/verify`** — send `{ "text": "..." }` to extract and fact-check claims.
- **GET `/health`** — returns `{"status": "ok"}`.

## Browser extension

1. Start the API: `python api.py`
2. Open `chrome://extensions` in Chrome, enable **Developer mode**.
3. Click **Load unpacked** and select the `extension/` folder.
4. Highlight text on any page, right-click, select **Fact-check this**.

> Local developer-mode extension only. Requires `api.py` running on your machine.

## Configuration

Set `LLM_PROVIDER` in your `.env` to pick the backend:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `groq`, or `openrouter` |
| `GOOGLE_API_KEY` | | Gemini key from [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | |
| `GROQ_API_KEY` | | Free key from [console.groq.com](https://console.groq.com/keys) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | |
| `OPENROUTER_API_KEY` | | Free key from [openrouter.ai](https://openrouter.ai/settings/keys) |
| `OPENROUTER_MODEL` | `deepseek/deepseek-chat-v3-0324:free` | `:free` = no-cost |
| `DEFAULT_REBUTTAL_ROUNDS` | `2` | |
| `LOG_DIR` | `logs` | |

Example for Groq:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

## Testing

```bash
pytest               # unit tests (no API key needed)
pytest -m integration # live end-to-end debate
```
