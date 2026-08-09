[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-AzdValue {
    param([Parameter(Mandatory)][string]$Name)
    $value = & azd env get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $value) { throw "Missing azd output $Name." }
    return ($value | Out-String).Trim()
}

$resourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
$apiName = Get-AzdValue 'AZURE_CONTAINER_APP_API_NAME'
$jobName = Get-AzdValue 'AZURE_BOOTSTRAP_JOB_NAME'

$apiImage = & az containerapp show --resource-group $resourceGroup --name $apiName --query 'properties.template.containers[0].image' -o tsv
if ($LASTEXITCODE -ne 0 -or -not $apiImage) { throw 'Could not resolve the deployed API image.' }


Write-Host "Starting fresh-environment initialization with image $apiImage"
$executionName = & az containerapp job start `
    --resource-group $resourceGroup `
    --name $jobName `
    --image $apiImage `
    --query name -o tsv
if ($LASTEXITCODE -ne 0 -or -not $executionName) { throw 'Could not start the initialization job.' }

Write-Host "Waiting for initialization job execution $executionName"
$deadline = (Get-Date).AddMinutes(35)
do {
    Start-Sleep -Seconds 10
    $status = & az containerapp job execution show --resource-group $resourceGroup --name $jobName --job-execution-name $executionName --query properties.status -o tsv 2>$null
    if ($status -eq 'Succeeded') {
        Write-Host 'Fresh PostgreSQL schema and Azure AI Search indexes initialized. No policy data was loaded.'
        exit 0
    }
    if ($status -in @('Failed','Stopped','Degraded')) {
        throw "Initialization job ended with status $status. Inspect: az containerapp job logs show -g $resourceGroup -n $jobName --execution $executionName"
    }
} while ((Get-Date) -lt $deadline)

throw 'Initialization job did not complete within 35 minutes.'
