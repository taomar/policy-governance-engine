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

Write-Host "API on http://127.0.0.1:$Port (bind $BindHost)"

$env:PYTHONPATH = Join-Path $root "src"
& (Join-Path $root ".venv-graph\Scripts\python.exe") -m uvicorn policy_platform.api.app:app --host $BindHost --port $Port
