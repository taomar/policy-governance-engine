targetScope = 'resourceGroup'

param openAiName string
param searchName string
param location string = resourceGroup().location
param tags object = {}
param searchSkuName string = 'standard'
param searchReplicaCount int = 1
param searchPartitionCount int = 1
param reasoningDeploymentName string
param reasoningModelName string
param reasoningModelVersion string
param reasoningDeploymentSku string
param reasoningCapacity int
param secondaryDeploymentName string
param secondaryModelName string
param secondaryModelVersion string
param secondaryDeploymentSku string
param secondaryCapacity int
param embeddingDeploymentName string
param embeddingModelName string
param embeddingModelVersion string
param embeddingDeploymentSku string
param embeddingCapacity int

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchName
  location: location
  tags: tags
  sku: {
    name: searchSkuName
  }
  properties: {
    authOptions: {
      apiKeyOnly: {}
    }
    disableLocalAuth: false
    encryptionWithCmk: {
      enforcement: 'Unspecified'
    }
    hostingMode: 'default'
    networkRuleSet: {
      ipRules: []
    }
    partitionCount: searchPartitionCount
    publicNetworkAccess: 'disabled'
    replicaCount: searchReplicaCount
    semanticSearch: 'free'
  }
}

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: openAiName
    disableLocalAuth: false
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

resource reasoningDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: reasoningDeploymentName
  sku: {
    name: reasoningDeploymentSku
    capacity: reasoningCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: reasoningModelName
      version: reasoningModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

resource secondaryDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: secondaryDeploymentName
  sku: {
    name: secondaryDeploymentSku
    capacity: secondaryCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: secondaryModelName
      version: secondaryModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: embeddingDeploymentName
  sku: {
    name: embeddingDeploymentSku
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

output openAiId string = openAi.id
output openAiName string = openAi.name
output openAiEndpoint string = openAi.properties.endpoint
output searchId string = search.id
output searchName string = search.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
