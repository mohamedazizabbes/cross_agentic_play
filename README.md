# AI Debate Arena

A domain-agnostic multi-agent debate platform powered by Google Gemini and live web search tools.

## Architecture

- **Debaters (PRO / CON)**: Autonomous AI agents that argue opposing stances on any given topic, utilizing live web search (`DuckDuckGo`) for fact-backed claims and responding directly to opponent rebuttals.
- **Fact-Checking Judge**: Independent judge agent that fact-checks claims made during the debate via live tool calls, evaluates performance on four separate axes (Logical Coherence, Evidence Accuracy, Responsiveness, Persuasiveness), and outputs Chain-of-Thought (CoT) reasoning before declaring a winner.
- **Orchestrator**: Turn-based state machine managing opening statements, rebuttal rounds, closing statements, and judging.
- **Structured JSON Logging**: Every debate is recorded with full transcript and multi-axis scorecards to `logs/debate_<timestamp>.json` for future analytics and ELO rating systems.

## Installation

1. Clone repository & set up environment:
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

3. Configure environment:
Create a `.env` file from `.env.example`:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

## Usage

Run a debate on any topic:
```bash
python main.py "Universal Basic Income should be implemented globally"
```

## Testing

Run unit tests:
```bash
pytest
```
