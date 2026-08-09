[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-AzdValue {
    param([Parameter(Mandatory)][string]$Name)
    $value = & azd env get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    return ($value | Out-String).Trim()
}

if ((Get-AzdValue 'AZURE_ENABLE_ENTRA_AUTH').ToLowerInvariant() -ne 'true') {
    Write-Host 'Microsoft Entra authentication is disabled; redirect URI configuration skipped.'
    exit 0
}

$clientId = Get-AzdValue 'AZURE_ENTRA_CLIENT_ID'
$webUrl = Get-AzdValue 'WEB_URL'
if (-not $clientId -or -not $webUrl) { throw 'AZURE_ENTRA_CLIENT_ID and WEB_URL are required.' }

$callback = "$($webUrl.TrimEnd('/'))/.auth/login/aad/callback"
$app = & az ad app show --id $clientId --output json 2>$null | ConvertFrom-Json
if (-not $app) { throw "The current identity cannot read Entra application $clientId." }

$redirectUris = @($app.web.redirectUris)
if ($redirectUris -notcontains $callback) {
    $redirectUris += $callback
    & az ad app update --id $app.id --web-redirect-uris $redirectUris --output none
    if ($LASTEXITCODE -ne 0) { throw "Could not add Entra redirect URI $callback." }
    Write-Host "Added Entra redirect URI $callback"
} else {
    Write-Host "Entra redirect URI already configured: $callback"
}
