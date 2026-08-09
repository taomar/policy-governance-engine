[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Initialize-AzdEnvironment.ps1')
& (Join-Path $PSScriptRoot 'Test-AzurePrerequisites.ps1')
