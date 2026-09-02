[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-AzdValue {
    param([Parameter(Mandatory)][string]$Name)
    $value = & azd env get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    return ($value | Out-String).Trim()
}

function Set-AzdValueIfMissing {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Default = '',
        [switch]$Required,
        [switch]$Secret
    )

    $existing = Get-AzdValue $Name
    if ($existing) { return $existing }

    if ($Secret) {
        $secure = Read-Host $Prompt -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    } else {
        $suffix = if ($Default) { " [$Default]" } else { '' }
        $value = Read-Host "$Prompt$suffix"
        if (-not $value) { $value = $Default }
    }

    if ($Required -and -not $value) { throw "$Name is required." }
    & azd env set $Name $value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not set azd value $Name." }
    return $value
}

if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
    throw 'Azure Developer CLI (azd) is required.'
}

$environmentName = Get-AzdValue 'AZURE_ENV_NAME'
if (-not $environmentName) {
    throw 'Create or select an azd environment before provisioning (azd env new <name> or azd up).'
}

# These choices are prompted explicitly. Remaining non-secret settings take the
# documented baseline unless the operator set an azd value beforehand.
$interactiveNames = @(
    'AZURE_RESOURCE_PREFIX',
    'POSTGRES_SKU_NAME',
    'POSTGRES_TIER',
    'AZURE_SEARCH_SKU',
    'AZURE_CONTAINER_REGISTRY_SKU',
    'AZURE_STORAGE_SKU',
    'AZURE_ENABLE_ENTRA_AUTH',
    'AZURE_VNET_ADDRESS_PREFIX',
    'AZURE_CONTAINER_APPS_SUBNET_PREFIX',
    'AZURE_POSTGRES_SUBNET_PREFIX',
    'AZURE_PRIVATE_ENDPOINTS_SUBNET_PREFIX'
)
$baselinePath = Join-Path $PSScriptRoot '..\parameters\baseline.env.example'
foreach ($line in Get-Content $baselinePath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    $name, $value = $trimmed -split '=', 2
    if ($name -in $interactiveNames) { continue }
    if (-not (Get-AzdValue $name)) {
        & azd env set $name $value | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not set baseline azd value $name." }
    }
}

Set-AzdValueIfMissing -Name 'AZURE_RESOURCE_GROUP' -Prompt 'Azure resource group name' -Default "rg-$environmentName" -Required | Out-Null
$prefix = Set-AzdValueIfMissing -Name 'AZURE_RESOURCE_PREFIX' -Prompt 'Short resource-name prefix (letters, numbers, hyphens)' -Default $environmentName -Required
if ($prefix -notmatch '^[A-Za-z][A-Za-z0-9-]{1,19}$') {
    throw 'AZURE_RESOURCE_PREFIX must start with a letter and contain 2-20 letters, numbers, or hyphens.'
}

Set-AzdValueIfMissing -Name 'POSTGRES_SKU_NAME' -Prompt 'PostgreSQL Flexible Server SKU' -Default 'Standard_B1ms' -Required | Out-Null
Set-AzdValueIfMissing -Name 'POSTGRES_TIER' -Prompt 'PostgreSQL tier (Burstable, GeneralPurpose, MemoryOptimized)' -Default 'Burstable' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_SEARCH_SKU' -Prompt 'Azure AI Search SKU' -Default 'standard' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_CONTAINER_REGISTRY_SKU' -Prompt 'Azure Container Registry SKU' -Default 'Standard' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_STORAGE_SKU' -Prompt 'Azure Storage SKU' -Default 'Standard_LRS' -Required | Out-Null

Set-AzdValueIfMissing -Name 'AZURE_VNET_ADDRESS_PREFIX' -Prompt 'VNet address prefix' -Default '10.20.0.0/16' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_CONTAINER_APPS_SUBNET_PREFIX' -Prompt 'Container Apps subnet prefix' -Default '10.20.0.0/23' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_POSTGRES_SUBNET_PREFIX' -Prompt 'PostgreSQL delegated subnet prefix' -Default '10.20.4.0/24' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_PRIVATE_ENDPOINTS_SUBNET_PREFIX' -Prompt 'Private endpoints subnet prefix' -Default '10.20.5.0/24' -Required | Out-Null

$tenantId = if (Get-Command az -ErrorAction SilentlyContinue) {
    (& az account show --query tenantId -o tsv 2>$null | Out-String).Trim()
} else { '' }
Set-AzdValueIfMissing -Name 'AZURE_ENTRA_TENANT_ID' -Prompt 'Microsoft Entra tenant ID' -Default $tenantId -Required | Out-Null
$entraSetting = Set-AzdValueIfMissing -Name 'AZURE_ENABLE_ENTRA_AUTH' -Prompt 'Enable Microsoft Entra authentication (true/false)' -Default 'true' -Required
if ($entraSetting.ToLowerInvariant() -notin @('true', 'false')) {
    throw 'AZURE_ENABLE_ENTRA_AUTH must be true or false.'
}

Set-AzdValueIfMissing -Name 'POSTGRES_ADMIN_LOGIN' -Prompt 'PostgreSQL administrator login' -Default 'policyadmin' -Required | Out-Null
$password = Set-AzdValueIfMissing -Name 'POSTGRES_ADMIN_PASSWORD' -Prompt 'PostgreSQL administrator password (20+ URI-safe characters: A-Z, a-z, 0-9, _, -, ., ~)' -Required -Secret
if ($password.Length -lt 20 -or $password -notmatch '^[A-Za-z0-9_.~-]+$') {
    throw 'POSTGRES_ADMIN_PASSWORD must be at least 20 URI-safe characters and contain only A-Z, a-z, 0-9, _, -, . or ~.'
}

if ($entraSetting.ToLowerInvariant() -eq 'true') {
    Set-AzdValueIfMissing -Name 'AZURE_ENTRA_CLIENT_ID' -Prompt 'Microsoft Entra application client ID' -Required | Out-Null
    Set-AzdValueIfMissing -Name 'AZURE_ENTRA_CLIENT_SECRET' -Prompt 'Microsoft Entra application client secret' -Required -Secret | Out-Null
} else {
    & azd env set AZURE_ENTRA_CLIENT_ID '' | Out-Null
    & azd env set AZURE_ENTRA_CLIENT_SECRET '' | Out-Null
}

Set-AzdValueIfMissing -Name 'AZURE_OPENAI_DEPLOYMENT' -Prompt 'Reasoning deployment name' -Default 'policy-reasoning' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_REASONING_MODEL' -Prompt 'Reasoning model name available in the selected region' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_REASONING_MODEL_VERSION' -Prompt 'Reasoning model version' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_SECONDARY_DEPLOYMENT' -Prompt 'Secondary reasoning deployment name' -Default 'policy-secondary' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_SECONDARY_MODEL' -Prompt 'Secondary reasoning model name available in the selected region' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_SECONDARY_MODEL_VERSION' -Prompt 'Secondary reasoning model version' -Required | Out-Null
Set-AzdValueIfMissing -Name 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT' -Prompt 'Embedding deployment name' -Default 'policy-embedding' -Required | Out-Null

Write-Host 'azd environment values are complete. No Azure resources were created.'
