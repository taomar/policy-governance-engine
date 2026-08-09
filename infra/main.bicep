targetScope = 'subscription'

@description('Short azd environment name used for naming and tags.')
@minLength(2)
@maxLength(20)
param environmentName string

@description('Azure region selected for this environment.')
param location string

@description('Resource group created for this environment.')
param resourceGroupName string

@description('Optional resource-name prefix. Defaults to the environment name.')
param resourceNamePrefix string = environmentName

@secure()
@description('PostgreSQL administrator password. Use URI-safe characters because the unchanged application consumes URL connection strings.')
param postgresAdministratorPassword string

@description('PostgreSQL administrator login.')
param postgresAdministratorLogin string = 'policyadmin'

@description('PostgreSQL database name.')
param postgresDatabaseName string = 'policy_platform'

@description('PostgreSQL Flexible Server compute SKU.')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL compute tier.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param postgresTier string = 'Burstable'

@description('PostgreSQL storage in GiB.')
param postgresStorageSizeGb string = '32'

@description('PostgreSQL backup retention in days.')
param postgresBackupRetentionDays string = '7'

@description('Enable zone-redundant PostgreSQL high availability.')
param postgresZoneRedundantHa string = 'false'

@description('Azure AI Search SKU.')
@allowed(['basic', 'standard', 'standard2', 'standard3'])
param searchSkuName string = 'standard'

param searchReplicaCount string = '1'

param searchPartitionCount string = '1'

param searchAuthoringIndexName string = 'policy-authoring'
param searchEvidenceIndexName string = 'policy-evidence'

@description('Azure Container Registry SKU.')
@allowed(['Basic', 'Standard', 'Premium'])
param containerRegistrySku string = 'Standard'

@description('Storage replication SKU for uploaded documents.')
@allowed(['Standard_LRS', 'Standard_ZRS'])
param storageSkuName string = 'Standard_LRS'

param documentShareQuotaGb string = '10'

@description('Log Analytics retention in days.')
param logRetentionDays string = '30'

param vnetAddressPrefix string = '10.20.0.0/16'
param containerAppsSubnetPrefix string = '10.20.0.0/23'
param postgresSubnetPrefix string = '10.20.4.0/24'
param privateEndpointsSubnetPrefix string = '10.20.5.0/24'

@description('Comma-separated public CIDRs allowed to reach the web app. Empty means no IP restriction.')
param allowedIngressCidrs string = ''

@description('Require Microsoft Entra authentication on public web ingress.')
param enableEntraAuthentication string = 'true'

param entraTenantId string = tenant().tenantId
param entraClientId string = ''

@secure()
param entraClientSecret string = ''

param openAiReasoningDeploymentName string = 'policy-reasoning'
param openAiReasoningModelName string
param openAiReasoningModelVersion string
param openAiReasoningDeploymentSku string = 'GlobalStandard'
param openAiReasoningCapacity string = '10'

param openAiFastDeploymentName string = 'policy-fast'
param openAiFastModelName string
param openAiFastModelVersion string
param openAiFastDeploymentSku string = 'GlobalStandard'
param openAiFastCapacity string = '10'

param openAiEmbeddingDeploymentName string = 'policy-embedding'
param openAiEmbeddingModelName string = 'text-embedding-3-large'
param openAiEmbeddingModelVersion string = '1'
param openAiEmbeddingDeploymentSku string = 'Standard'
param openAiEmbeddingCapacity string = '10'
@allowed(['1536', '3072'])
param openAiEmbeddingDimensions string = '3072'

@allowed(['2024-12-01-preview'])
param openAiApiVersion string = '2024-12-01-preview'
param searchApiVersion string = '2025-09-01'

param webMinReplicas string = '1'
param webMaxReplicas string = '2'
param apiMinReplicas string = '1'
param apiMaxReplicas string = '3'

var tags = {
  'azd-env-name': environmentName
  workload: 'policy-platform'
  managedBy: 'azd-bicep'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module platform './modules/platform.bicep' = {
  name: 'policy-platform-${environmentName}'
  scope: resourceGroup
  params: {
    environmentName: environmentName
    location: location
    resourceNamePrefix: resourceNamePrefix
    tags: tags
    postgresAdministratorPassword: postgresAdministratorPassword
    postgresAdministratorLogin: postgresAdministratorLogin
    postgresDatabaseName: postgresDatabaseName
    postgresSkuName: postgresSkuName
    postgresTier: postgresTier
    postgresStorageSizeGb: int(postgresStorageSizeGb)
    postgresBackupRetentionDays: int(postgresBackupRetentionDays)
    postgresZoneRedundantHa: toLower(postgresZoneRedundantHa) == 'true'
    searchSkuName: searchSkuName
    searchReplicaCount: int(searchReplicaCount)
    searchPartitionCount: int(searchPartitionCount)
    searchAuthoringIndexName: searchAuthoringIndexName
    searchEvidenceIndexName: searchEvidenceIndexName
    containerRegistrySku: containerRegistrySku
    storageSkuName: storageSkuName
    documentShareQuotaGb: int(documentShareQuotaGb)
    logRetentionDays: int(logRetentionDays)
    vnetAddressPrefix: vnetAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
    privateEndpointsSubnetPrefix: privateEndpointsSubnetPrefix
    allowedIngressCidrs: allowedIngressCidrs
    enableEntraAuthentication: toLower(enableEntraAuthentication) == 'true'
    entraTenantId: entraTenantId
    entraClientId: entraClientId
    entraClientSecret: entraClientSecret
    openAiReasoningDeploymentName: openAiReasoningDeploymentName
    openAiReasoningModelName: openAiReasoningModelName
    openAiReasoningModelVersion: openAiReasoningModelVersion
    openAiReasoningDeploymentSku: openAiReasoningDeploymentSku
    openAiReasoningCapacity: int(openAiReasoningCapacity)
    openAiFastDeploymentName: openAiFastDeploymentName
    openAiFastModelName: openAiFastModelName
    openAiFastModelVersion: openAiFastModelVersion
    openAiFastDeploymentSku: openAiFastDeploymentSku
    openAiFastCapacity: int(openAiFastCapacity)
    openAiEmbeddingDeploymentName: openAiEmbeddingDeploymentName
    openAiEmbeddingModelName: openAiEmbeddingModelName
    openAiEmbeddingModelVersion: openAiEmbeddingModelVersion
    openAiEmbeddingDeploymentSku: openAiEmbeddingDeploymentSku
    openAiEmbeddingCapacity: int(openAiEmbeddingCapacity)
    openAiEmbeddingDimensions: int(openAiEmbeddingDimensions)
    openAiApiVersion: openAiApiVersion
    searchApiVersion: searchApiVersion
    webMinReplicas: int(webMinReplicas)
    webMaxReplicas: int(webMaxReplicas)
    apiMinReplicas: int(apiMinReplicas)
    apiMaxReplicas: int(apiMaxReplicas)
  }
}

output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = platform.outputs.containerRegistryEndpoint
output AZURE_CONTAINER_REGISTRY_NAME string = platform.outputs.containerRegistryName
output AZURE_KEY_VAULT_NAME string = platform.outputs.keyVaultName
output AZURE_CONTAINER_APP_API_NAME string = platform.outputs.apiContainerAppName
output AZURE_CONTAINER_APP_WEB_NAME string = platform.outputs.webContainerAppName
output AZURE_BOOTSTRAP_JOB_NAME string = platform.outputs.bootstrapJobName
output API_URL string = platform.outputs.apiUrl
output WEB_URL string = platform.outputs.webUrl
output AZURE_OPENAI_ENDPOINT string = platform.outputs.openAiEndpoint
output AZURE_SEARCH_ENDPOINT string = platform.outputs.searchEndpoint
output AZURE_POSTGRESQL_SERVER_NAME string = platform.outputs.postgresServerName
