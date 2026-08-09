targetScope = 'resourceGroup'

param environmentName string
param location string = resourceGroup().location
param resourceNamePrefix string
param tags object = {}
@secure()
param postgresAdministratorPassword string
param postgresAdministratorLogin string
param postgresDatabaseName string
param postgresSkuName string
param postgresTier string
param postgresStorageSizeGb int
param postgresBackupRetentionDays int
param postgresZoneRedundantHa bool
param searchSkuName string
param searchReplicaCount int
param searchPartitionCount int
param searchAuthoringIndexName string
param searchEvidenceIndexName string
param containerRegistrySku string
param storageSkuName string
param documentShareQuotaGb int
param logRetentionDays int
param vnetAddressPrefix string
param containerAppsSubnetPrefix string
param postgresSubnetPrefix string
param privateEndpointsSubnetPrefix string
param allowedIngressCidrs string
param enableEntraAuthentication bool
param entraTenantId string
param entraClientId string
@secure()
param entraClientSecret string
param openAiReasoningDeploymentName string
param openAiReasoningModelName string
param openAiReasoningModelVersion string
param openAiReasoningDeploymentSku string
param openAiReasoningCapacity int
param openAiFastDeploymentName string
param openAiFastModelName string
param openAiFastModelVersion string
param openAiFastDeploymentSku string
param openAiFastCapacity int
param openAiEmbeddingDeploymentName string
param openAiEmbeddingModelName string
param openAiEmbeddingModelVersion string
param openAiEmbeddingDeploymentSku string
param openAiEmbeddingCapacity int
param openAiEmbeddingDimensions int
param openAiApiVersion string
param searchApiVersion string
param webMinReplicas int
param webMaxReplicas int
param apiMinReplicas int
param apiMaxReplicas int

var suffix = take(uniqueString(subscription().id, resourceGroup().id, environmentName), 6)
var normalizedPrefix = toLower(replace(replace(resourceNamePrefix, '-', ''), '_', ''))
var shortPrefix = take(normalizedPrefix, 10)
var names = {
  vnet: 'vnet-${shortPrefix}-${suffix}'
  log: 'log-${shortPrefix}-${suffix}'
  registry: take('cr${normalizedPrefix}${suffix}', 50)
  storage: take('st${normalizedPrefix}${suffix}', 24)
  vault: take('kv-${shortPrefix}-${suffix}', 24)
  postgres: take('psql-${shortPrefix}-${suffix}', 63)
  openAi: take('oai-${shortPrefix}-${suffix}', 64)
  search: take('srch-${shortPrefix}-${suffix}', 60)
  containerEnvironment: take('cae-${shortPrefix}-${suffix}', 60)
  apiIdentity: take('id-${shortPrefix}-api-${suffix}', 128)
  webIdentity: take('id-${shortPrefix}-web-${suffix}', 128)
  api: take('ca-${shortPrefix}-api-${suffix}', 32)
  web: take('ca-${shortPrefix}-web-${suffix}', 32)
  bootstrapJob: take('caj-${shortPrefix}-init-${suffix}', 32)
}

module observability './observability.bicep' = {
  name: 'observability'
  params: {
    name: names.log
    location: location
    tags: tags
    retentionInDays: logRetentionDays
  }
}

module identities './identities.bicep' = {
  name: 'identities'
  params: {
    apiIdentityName: names.apiIdentity
    webIdentityName: names.webIdentity
    location: location
    tags: tags
  }
}

module registry './registry.bicep' = {
  name: 'registry'
  params: {
    name: names.registry
    location: location
    tags: tags
    skuName: containerRegistrySku
  }
}

module network './network.bicep' = {
  name: 'network'
  params: {
    name: names.vnet
    location: location
    tags: tags
    vnetAddressPrefix: vnetAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
    privateEndpointsSubnetPrefix: privateEndpointsSubnetPrefix
  }
}

module storage './storage.bicep' = {
  name: 'storage'
  params: {
    name: names.storage
    location: location
    tags: tags
    skuName: storageSkuName
    shareName: 'documents'
    shareQuotaGb: documentShareQuotaGb
  }
}

module postgres './postgres.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
    delegatedSubnetId: network.outputs.postgresSubnetId
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    databaseName: postgresDatabaseName
    skuName: postgresSkuName
    tier: postgresTier
    storageSizeGb: postgresStorageSizeGb
    backupRetentionDays: postgresBackupRetentionDays
    zoneRedundantHa: postgresZoneRedundantHa
  }
}

module aiServices './ai-services.bicep' = {
  name: 'ai-services'
  params: {
    openAiName: names.openAi
    searchName: names.search
    location: location
    tags: tags
    searchSkuName: searchSkuName
    searchReplicaCount: searchReplicaCount
    searchPartitionCount: searchPartitionCount
    reasoningDeploymentName: openAiReasoningDeploymentName
    reasoningModelName: openAiReasoningModelName
    reasoningModelVersion: openAiReasoningModelVersion
    reasoningDeploymentSku: openAiReasoningDeploymentSku
    reasoningCapacity: openAiReasoningCapacity
    fastDeploymentName: openAiFastDeploymentName
    fastModelName: openAiFastModelName
    fastModelVersion: openAiFastModelVersion
    fastDeploymentSku: openAiFastDeploymentSku
    fastCapacity: openAiFastCapacity
    embeddingDeploymentName: openAiEmbeddingDeploymentName
    embeddingModelName: openAiEmbeddingModelName
    embeddingModelVersion: openAiEmbeddingModelVersion
    embeddingDeploymentSku: openAiEmbeddingDeploymentSku
    embeddingCapacity: openAiEmbeddingCapacity
  }
}

module keyVault './key-vault.bicep' = {
  name: 'key-vault'
  params: {
    name: names.vault
    location: location
    tags: tags
  }
}

module privateEndpoints './private-endpoints.bicep' = {
  name: 'private-endpoints'
  params: {
    namePrefix: shortPrefix
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
    subnetId: network.outputs.privateEndpointsSubnetId
    keyVaultId: keyVault.outputs.id
    storageAccountId: storage.outputs.id
    openAiAccountId: aiServices.outputs.openAiId
    searchServiceId: aiServices.outputs.searchId
  }
}

module keyVaultAccess './key-vault-access.bicep' = {
  name: 'key-vault-access'
  params: {
    keyVaultName: keyVault.outputs.name
    apiIdentityPrincipalId: identities.outputs.apiIdentityPrincipalId
    webIdentityPrincipalId: identities.outputs.webIdentityPrincipalId
  }
}

module keyVaultSecrets './key-vault-secrets.bicep' = {
  name: 'key-vault-secrets'
  params: {
    vaultName: keyVault.outputs.name
    postgresServerFqdn: postgres.outputs.fqdn
    postgresAdministratorLogin: postgresAdministratorLogin
    postgresAdministratorPassword: postgresAdministratorPassword
    postgresDatabaseName: postgresDatabaseName
    openAiAccountName: aiServices.outputs.openAiName
    searchServiceName: aiServices.outputs.searchName
    enableEntraAuthentication: enableEntraAuthentication
    entraClientSecret: entraClientSecret
  }
}

module containerEnvironment './container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  params: {
    name: names.containerEnvironment
    location: location
    tags: tags
    infrastructureSubnetId: network.outputs.containerAppsSubnetId
    logAnalyticsCustomerId: observability.outputs.workspaceCustomerId
    logAnalyticsSharedKey: observability.outputs.workspaceSharedKey
    storageName: storage.outputs.name
    storageAccessKey: storage.outputs.accessKey
    storageShareName: storage.outputs.shareName
    storageMountName: 'documents-storage'
  }
  dependsOn: [privateEndpoints]
}

module containerApps './container-apps.bicep' = {
  name: 'container-apps'
  params: {
    environmentId: containerEnvironment.outputs.id
    storageMountName: containerEnvironment.outputs.storageMountName
    containerRegistryServer: registry.outputs.loginServer
    location: location
    tags: tags
    apiName: names.api
    webName: names.web
    bootstrapJobName: names.bootstrapJob
    apiIdentityId: identities.outputs.apiIdentityId
    apiIdentityClientId: identities.outputs.apiIdentityClientId
    webIdentityId: identities.outputs.webIdentityId
    webIdentityClientId: identities.outputs.webIdentityClientId
    applicationInsightsConnectionString: observability.outputs.applicationInsightsConnectionString
    databaseUrlSecretUri: keyVaultSecrets.outputs.databaseUrlSecretUri
    alembicDatabaseUrlSecretUri: keyVaultSecrets.outputs.alembicDatabaseUrlSecretUri
    postgresPasswordSecretUri: keyVaultSecrets.outputs.postgresPasswordSecretUri
    openAiKeySecretUri: keyVaultSecrets.outputs.openAiKeySecretUri
    searchKeySecretUri: keyVaultSecrets.outputs.searchKeySecretUri
    entraClientSecretUri: keyVaultSecrets.outputs.entraClientSecretUri
    enableEntraAuthentication: enableEntraAuthentication
    entraTenantId: entraTenantId
    entraClientId: entraClientId
    openAiEndpoint: aiServices.outputs.openAiEndpoint
    openAiApiVersion: openAiApiVersion
    openAiReasoningDeploymentName: openAiReasoningDeploymentName
    openAiFastDeploymentName: openAiFastDeploymentName
    openAiEmbeddingDeploymentName: openAiEmbeddingDeploymentName
    openAiEmbeddingModelName: openAiEmbeddingModelName
    openAiEmbeddingDimensions: openAiEmbeddingDimensions
    searchEndpoint: aiServices.outputs.searchEndpoint
    searchApiVersion: searchApiVersion
    searchAuthoringIndexName: searchAuthoringIndexName
    searchEvidenceIndexName: searchEvidenceIndexName
    postgresHost: postgres.outputs.fqdn
    postgresDatabaseName: postgresDatabaseName
    postgresAdministratorLogin: postgresAdministratorLogin
    allowedIngressCidrs: allowedIngressCidrs
    webMinReplicas: webMinReplicas
    webMaxReplicas: webMaxReplicas
    apiMinReplicas: apiMinReplicas
    apiMaxReplicas: apiMaxReplicas
  }
  dependsOn: [keyVaultAccess, privateEndpoints]
}

module acrPull './acr-pull.bicep' = {
  name: 'acr-pull'
  params: {
    containerRegistryName: registry.outputs.name
    apiPrincipalId: containerApps.outputs.apiPrincipalId
    webPrincipalId: containerApps.outputs.webPrincipalId
    bootstrapPrincipalId: identities.outputs.apiIdentityPrincipalId
  }
}

output containerRegistryEndpoint string = registry.outputs.loginServer
output containerRegistryName string = registry.outputs.name
output keyVaultName string = keyVault.outputs.name
output apiContainerAppName string = containerApps.outputs.apiName
output webContainerAppName string = containerApps.outputs.webName
output bootstrapJobName string = containerApps.outputs.bootstrapJobName
output apiUrl string = containerApps.outputs.apiUrl
output webUrl string = containerApps.outputs.webUrl
output openAiEndpoint string = aiServices.outputs.openAiEndpoint
output searchEndpoint string = aiServices.outputs.searchEndpoint
output postgresServerName string = postgres.outputs.name
