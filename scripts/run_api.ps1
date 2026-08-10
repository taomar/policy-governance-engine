# Starts the API with a clean Azure environment.
#
# pydantic-settings gives ambient process environment variables priority over
# .env, so a stale AZURE_OPENAI_ENDPOINT left in the shell silently pairs an
# endpoint from one resource with the key from another. That surfaces as a bare
# 401 from Azure, which reads like a bad key rather than a mismatched pair and
# has cost real debugging time twice.
#
# Clearing them here lets .env be the single source of truth for credentials.
param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

foreach ($name in @(
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION")) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}

# Read the port from .env rather than hardcoding one, so the script and the
# documented API_PORT cannot drift apart. An explicit -Port still wins, which is
# what a second checkout on the same machine needs.
if ($Port -eq 0) {
    $envFile = Join-Path $root ".env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern '^\s*API_PORT\s*=\s*(\d+)' | Select-Object -First 1
        if ($match) { $Port = [int]$match.Matches[0].Groups[1].Value }
    }
    if ($Port -eq 0) { $Port = 8010 }
}

# Prefer .venv, the documented environment. .venv-graph additionally carries the
# Docling stack and resolves httpx above the API's own pin, so it is a fallback
# for a checkout set up for conversion work rather than the default.
$python = $null
foreach ($candidate in @(".venv", ".venv-graph")) {
    $exe = Join-Path $root "$candidate\Scripts\python.exe"
    if (Test-Path $exe) { $python = $exe; break }
}
if (-not $python) {
    throw "No virtual environment found. Create one with: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
}

# Bound to 0.0.0.0 by default, not 127.0.0.1: browsers resolve localhost to ::1
# first, and an IPv4-only bind then fails in the browser while curl still
# succeeds — which makes the fault look like a CORS or application error.
Write-Host "API on http://127.0.0.1:$Port (bind $BindHost) using $(Split-Path -Leaf (Split-Path -Parent (Split-Path -Parent $python)))"

$env:PYTHONPATH = Join-Path $root "src"
& $python -m uvicorn policy_platform.api.app:app --host $BindHost --port $Port
