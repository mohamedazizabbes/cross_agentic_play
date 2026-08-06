#!/bin/sh
# Installs the repo's gitleaks pre-commit hook into .git/hooks/pre-commit.
# Requires git bash on Windows. Run: bash scripts/install-hooks.sh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_SRC="$SCRIPT_DIR/hooks/pre-commit"
HOOK_DST="$SCRIPT_DIR/.git/hooks/pre-commit"

if [ ! -d "$SCRIPT_DIR/.git/hooks" ]; then
  echo "error: not a git repository: $SCRIPT_DIR/.git/hooks missing" >&2
  exit 1
fi

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "Installed gitleaks pre-commit hook -> $HOOK_DST"
echo "Make sure the gitleaks binary is on your PATH (https://github.com/gitleaks/gitleaks)."
