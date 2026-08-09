targetScope = 'resourceGroup'

param name string
param location string = resourceGroup().location
param tags object = {}
@allowed(['Standard_LRS', 'Standard_ZRS'])
param skuName string = 'Standard_LRS'
param shareName string = 'documents'
param shareQuotaGb int = 10

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: true
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: {
    accessTier: 'TransactionOptimized'
    enabledProtocols: 'SMB'
    shareQuota: shareQuotaGb
  }
}

output id string = storage.id
output name string = storage.name
output fileEndpoint string = storage.properties.primaryEndpoints.file
output shareName string = fileShare.name
@secure()
output accessKey string = storage.listKeys().keys[0].value
