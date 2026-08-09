targetScope = 'resourceGroup'

param namePrefix string
param location string = resourceGroup().location
param tags object = {}
param vnetId string
param subnetId string
param keyVaultId string
param storageAccountId string
param openAiAccountId string
param searchServiceId string

var definitions = [
  {
    key: 'kv'
    zone: 'privatelink.vaultcore.azure.net'
    targetId: keyVaultId
    groupId: 'vault'
  }
  {
    key: 'file'
    zone: 'privatelink.file.'
    targetId: storageAccountId
    groupId: 'file'
  }
  {
    key: 'openai'
    zone: 'privatelink.openai.azure.com'
    targetId: openAiAccountId
    groupId: 'account'
  }
  {
    key: 'search'
    zone: 'privatelink.search.windows.net'
    targetId: searchServiceId
    groupId: 'searchService'
  }
]

resource privateDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for definition in definitions: {
  name: definition.zone
  location: 'global'
  tags: tags
}]

resource vnetLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (definition, index) in definitions: {
  parent: privateDnsZones[index]
  name: '${namePrefix}-${definition.key}-vnet-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}]

resource privateEndpoints 'Microsoft.Network/privateEndpoints@2024-05-01' = [for definition in definitions: {
  name: '${namePrefix}-${definition.key}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${definition.key}-connection'
        properties: {
          privateLinkServiceId: definition.targetId
          groupIds: [definition.groupId]
          privateLinkServiceConnectionState: {
            status: 'Approved'
            description: 'Approved by deployment.'
            actionsRequired: 'None'
          }
        }
      }
    ]
  }
}]

resource zoneGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = [for (definition, index) in definitions: {
  parent: privateEndpoints[index]
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: definition.key
        properties: {
          privateDnsZoneId: privateDnsZones[index].id
        }
      }
    ]
  }
  dependsOn: [vnetLinks[index]]
}]

output privateEndpointIds array = [for (definition, index) in definitions: privateEndpoints[index].id]
output privateDnsZoneIds array = [for (definition, index) in definitions: privateDnsZones[index].id]
