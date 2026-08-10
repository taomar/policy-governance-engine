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
    [int]$Port = 8050
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

$env:PYTHONPATH = Join-Path $root "src"
& (Join-Path $root ".venv-graph\Scripts\python.exe") -m uvicorn policy_platform.api.app:app --host $BindHost --port $Port
