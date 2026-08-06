# Installs the repo's gitleaks pre-commit hook into .git/hooks/pre-commit.
# Run from PowerShell:  .\scripts\install-hooks.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$hookSrc = Join-Path $root "hooks\pre-commit"
$hookDst = Join-Path $root ".git\hooks\pre-commit"

if (-not (Test-Path $hookDst)) {
    if (-not (Test-Path (Split-Path $hookDst))) {
        throw ".git/hooks directory not found; are you in a git repository?"
    }
}

Copy-Item -LiteralPath $hookSrc -Destination $hookDst -Force
Write-Host "Installed gitleaks pre-commit hook -> $hookDst"
Write-Host "Make sure the gitleaks binary is on your PATH (https://github.com/gitleaks/gitleaks)."
