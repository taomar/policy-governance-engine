[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Configure-EntraRedirectUri.ps1')
& (Join-Path $PSScriptRoot 'Invoke-PostDeployBootstrap.ps1')
