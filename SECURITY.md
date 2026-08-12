# Security Policy

## Reporting a vulnerability

Please report security issues privately so they can be fixed before disclosure:

- **Email:** mohamedaziz.abbes@insat.ucar.tn
- **GitHub:** open a [private security advisory](https://github.com/mohamedazizabbes/cross_agentic_play/security/advisories/new)

Do not open a public issue for suspected vulnerabilities. Include the affected version(s), steps to reproduce, and (if possible) a minimal proof of concept. We aim to acknowledge reports within 3 business days.

## API keys

- **Never commit `.env`** or any file containing API keys. The repository's `.gitignore` excludes `.env`, and keys are read from environment variables at runtime (see `.env.example` for the required shape).
- Scope keys minimally: create API keys for this project only, and set per-key usage limits where your provider supports them.
- If a key is ever committed, pushed, or otherwise exposed, **rotate it immediately** at the provider console and delete the exposed copy from Git history.

## Safety net, not a guarantee

A `gitleaks` pre-commit hook (installed via `scripts/install-hooks.sh` / `.ps1`) and a gitleaks CI step in `.github/workflows/tests.yml` scan for committed secrets. They are a safety net, not a guarantee — always audit your own `git push` output and treat local state files (`.quota_state.json`, `.cache/`, `logs/`) as machine-local data that should never be committed.
