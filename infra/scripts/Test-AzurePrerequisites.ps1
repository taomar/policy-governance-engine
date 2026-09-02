[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not installed or not on PATH."
    }
}

function Get-AzdValue {
    param([Parameter(Mandatory)][string]$Name)
    $value = & azd env get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    return ($value | Out-String).Trim()
}

function ConvertTo-CidrRange {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Cidr
    )

    if ($Cidr -notmatch '^([^/]+)/([0-9]{1,2})$') { throw "$Name is not an IPv4 CIDR: $Cidr" }
    $address = $null
    if (-not [Net.IPAddress]::TryParse($Matches[1], [ref]$address) -or $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw "$Name is not an IPv4 CIDR: $Cidr"
    }
    $prefix = [int]$Matches[2]
    if ($prefix -lt 0 -or $prefix -gt 32) { throw "$Name has an invalid prefix length: $Cidr" }

    [uint64]$value = 0
    foreach ($byte in $address.GetAddressBytes()) { $value = ($value -shl 8) -bor $byte }
    [uint64]$size = [math]::Pow(2, 32 - $prefix)
    [uint64]$start = [math]::Floor($value / $size) * $size
    [pscustomobject]@{
        Name = $Name
        Cidr = $Cidr
        Prefix = $prefix
        Start = $start
        End = $start + $size - 1
    }
}

function Test-ProviderLocation {
    param(
        [Parameter(Mandatory)][string]$Provider,
        [Parameter(Mandatory)][string]$ResourceType,
        [Parameter(Mandatory)][string]$DisplayName
    )
    $locations = @(& az provider show --namespace $Provider --query "resourceTypes[?resourceType=='$ResourceType'].locations[]" -o tsv 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not ($locations | Where-Object { $_ -ieq $DisplayName })) {
        throw "$Provider/$ResourceType is not listed in $DisplayName."
    }
}

Require-Command az
Require-Command azd
Require-Command docker

$account = & az account show --output json 2>$null | ConvertFrom-Json
if (-not $account) { throw 'Azure CLI is not authenticated. Run az login.' }

$subscriptionId = Get-AzdValue 'AZURE_SUBSCRIPTION_ID'
$location = Get-AzdValue 'AZURE_LOCATION'
if (-not $subscriptionId) { throw 'AZURE_SUBSCRIPTION_ID is not selected.' }
if (-not $location) { throw 'AZURE_LOCATION is not selected.' }
if ($account.id -ne $subscriptionId) {
    throw "Azure CLI subscription $($account.id) does not match azd subscription $subscriptionId."
}

$locationObject = & az account list-locations --query "[?name=='$location'] | [0]" -o json | ConvertFrom-Json
if (-not $locationObject) { throw "Azure location '$location' is not available to this subscription." }
$displayName = $locationObject.displayName

$providers = @(
    'Microsoft.App',
    'Microsoft.Authorization',
    'Microsoft.CognitiveServices',
    'Microsoft.ContainerRegistry',
    'Microsoft.DBforPostgreSQL',
    'Microsoft.Insights',
    'Microsoft.KeyVault',
    'Microsoft.ManagedIdentity',
    'Microsoft.Network',
    'Microsoft.OperationalInsights',
    'Microsoft.Search',
    'Microsoft.Storage'
)
$unregistered = @()
foreach ($provider in $providers) {
    $state = & az provider show --namespace $provider --query registrationState -o tsv 2>$null
    if ($state -ne 'Registered') { $unregistered += $provider }
}
if ($unregistered) {
    throw "Register these resource providers before azd up: $($unregistered -join ', ')."
}

Test-ProviderLocation -Provider 'Microsoft.App' -ResourceType 'managedEnvironments' -DisplayName $displayName
Test-ProviderLocation -Provider 'Microsoft.DBforPostgreSQL' -ResourceType 'flexibleServers' -DisplayName $displayName
Test-ProviderLocation -Provider 'Microsoft.Search' -ResourceType 'searchServices' -DisplayName $displayName
Test-ProviderLocation -Provider 'Microsoft.CognitiveServices' -ResourceType 'accounts' -DisplayName $displayName
Test-ProviderLocation -Provider 'Microsoft.ContainerRegistry' -ResourceType 'registries' -DisplayName $displayName
Test-ProviderLocation -Provider 'Microsoft.Storage' -ResourceType 'storageAccounts' -DisplayName $displayName

$quotaExtension = & az extension show --name quota --query name -o tsv 2>$null
if (-not $quotaExtension) {
    throw 'Azure CLI quota extension is required: az extension add --name quota'
}
$scope = "/subscriptions/$subscriptionId/providers/Microsoft.App/locations/$location"
& az quota list --scope $scope --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Container Apps quota could not be read for $location. Verify Microsoft.Quota registration and Reader permissions."
}

$postgresSku = Get-AzdValue 'POSTGRES_SKU_NAME'
$postgresSkus = & az postgres flexible-server list-skus --location $location --output json 2>$null | ConvertFrom-Json
$postgresSkuMatch = @($postgresSkus | Where-Object { $_.name -eq $postgresSku -or $_.supportedTier -contains $postgresSku })
if (-not $postgresSkuMatch -and (($postgresSkus | ConvertTo-Json -Depth 20) -notmatch [regex]::Escape($postgresSku))) {
    throw "PostgreSQL SKU $postgresSku is not listed for $location."
}

$models = & az cognitiveservices model list --location $location --output json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $models) {
    throw "Azure OpenAI model availability could not be read for $location."
}
$modelObjects = $models | ConvertFrom-Json
$deployments = @(
    @{ Label = 'reasoning'; Model = 'AZURE_OPENAI_REASONING_MODEL'; Version = 'AZURE_OPENAI_REASONING_MODEL_VERSION'; Sku = 'AZURE_OPENAI_REASONING_SKU' },
    @{ Label = 'secondary'; Model = 'AZURE_OPENAI_SECONDARY_MODEL'; Version = 'AZURE_OPENAI_SECONDARY_MODEL_VERSION'; Sku = 'AZURE_OPENAI_SECONDARY_SKU' },
    @{ Label = 'embedding'; Model = 'AZURE_OPENAI_EMBEDDING_MODEL'; Version = 'AZURE_OPENAI_EMBEDDING_MODEL_VERSION'; Sku = 'AZURE_OPENAI_EMBEDDING_SKU' }
)
foreach ($deployment in $deployments) {
    $name = Get-AzdValue $deployment.Model
    $version = Get-AzdValue $deployment.Version
    $sku = Get-AzdValue $deployment.Sku
    $matches = @($modelObjects | Where-Object { $_.model.name -eq $name -and $_.model.version -eq $version })
    if (-not $matches) { throw "The $($deployment.Label) model $name version $version is not listed for $location." }
    $skuNames = @($matches | ForEach-Object { $_.skus } | ForEach-Object { $_.name } | Where-Object { $_ })
    if ($skuNames -and $sku -notin $skuNames) {
        throw "The $($deployment.Label) model $name $version does not list deployment SKU $sku in $location. Available: $($skuNames -join ', ')."
    }
}
& az cognitiveservices usage list --location $location --output none 2>$null
if ($LASTEXITCODE -ne 0) { throw "Azure OpenAI quota usage could not be read for $location." }

$vnet = ConvertTo-CidrRange -Name 'AZURE_VNET_ADDRESS_PREFIX' -Cidr (Get-AzdValue 'AZURE_VNET_ADDRESS_PREFIX')
$subnets = @(
    ConvertTo-CidrRange -Name 'AZURE_CONTAINER_APPS_SUBNET_PREFIX' -Cidr (Get-AzdValue 'AZURE_CONTAINER_APPS_SUBNET_PREFIX')
    ConvertTo-CidrRange -Name 'AZURE_POSTGRES_SUBNET_PREFIX' -Cidr (Get-AzdValue 'AZURE_POSTGRES_SUBNET_PREFIX')
    ConvertTo-CidrRange -Name 'AZURE_PRIVATE_ENDPOINTS_SUBNET_PREFIX' -Cidr (Get-AzdValue 'AZURE_PRIVATE_ENDPOINTS_SUBNET_PREFIX')
)
foreach ($subnet in $subnets) {
    if ($subnet.Start -lt $vnet.Start -or $subnet.End -gt $vnet.End) {
        throw "$($subnet.Name) ($($subnet.Cidr)) is outside $($vnet.Cidr)."
    }
}
for ($left = 0; $left -lt $subnets.Count; $left++) {
    for ($right = $left + 1; $right -lt $subnets.Count; $right++) {
        if ($subnets[$left].Start -le $subnets[$right].End -and $subnets[$right].Start -le $subnets[$left].End) {
            throw "$($subnets[$left].Name) overlaps $($subnets[$right].Name)."
        }
    }
}
if ($subnets[0].Prefix -gt 27) { throw 'The Container Apps subnet must be /27 or larger.' }
if ($subnets[1].Prefix -gt 28) { throw 'The PostgreSQL delegated subnet must be /28 or larger.' }
if ($subnets[2].Prefix -gt 27) { throw 'The private-endpoints subnet must be /27 or larger for this design.' }

Write-Host "Azure prerequisite checks passed for subscription '$($account.name)' in '$location'."
Write-Host 'This script performed read-only checks and created no Azure resources.'
