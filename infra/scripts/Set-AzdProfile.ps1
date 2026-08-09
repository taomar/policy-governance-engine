[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('baseline','resilient')]
    [string]$Profile
)

$ErrorActionPreference = 'Stop'
$file = Join-Path $PSScriptRoot "..\parameters\$Profile.env.example"
foreach ($line in Get-Content $file) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    $name, $value = $trimmed -split '=', 2
    & azd env set $name $value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not set $name." }
}
Write-Host "Applied non-secret '$Profile' parameter profile to the selected azd environment."
