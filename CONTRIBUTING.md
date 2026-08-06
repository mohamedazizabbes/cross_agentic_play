# Contributing

Thanks for wanting to contribute to AI Debate Arena! This project is small and deliberately simple, so the bar for a good PR is low.

## Set up the dev environment

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then add your GOOGLE_API_KEY
```

The only required secret is `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com). Everything else (model name, rebuttal rounds, log directory) is optional and configurable via `.env`.

## Running tests

```bash
pytest                # unit tests only — offline, fast, no API key needed
pytest -m integration # live end-to-end debate (calls Gemini + DuckDuckGo, needs GOOGLE_API_KEY)
```

The CI badge reflects `pytest` (unit tests only). The live integration suite in `tests/test_pipeline_golden.py` is gated behind the `integration` marker and is expected to be run locally before merging anything that touches the debate pipeline.

## Code style

- Format with `ruff format` and check with `ruff check` (see `[tool.ruff]` in `pyproject.toml`).
- Follow the existing module layout: agents / tools / utils, with Pydantic models and schemas in `models.py`.
- No comments unless they explain a non-obvious decision.

## Secret scanning (gitleaks)

A pre-commit hook scans staged changes for accidentally committed secrets (API keys, PATs).
Install it once:

```bash
bash scripts/install-hooks.sh   # or PowerShell: .\scripts\install-hooks.ps1
```

gitleaks must be on your PATH. The same scan runs in CI (`.github/workflows/tests.yml`),
so a secret slipped into a commit will fail the `secret-scan` job.

## CLI flags

- `--no-cache` — bypass the on-disk LLM response cache (`.cache/`).
- `--multi-judge` — ask every configured provider for a verdict and aggregate the results.
- `--human PRO|CON` — type rebuttals for a side instead of letting the AI generate them.
- `--export <path>` — write the debate transcript to Markdown/HTML (by file extension).

## Opening a PR

- New features should ship with a test, mirroring the existing `tests/` pattern (`tests/test_*.py`, offline by default).
- Run `pytest` and `ruff check .` before pushing — both should be clean.
- Keep the diff focused; if you're adding a feature, open one PR for the feature and one for unrelated cleanup.
