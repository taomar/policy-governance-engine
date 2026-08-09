targetScope = 'resourceGroup'

param name string
param location string = resourceGroup().location
param tags object = {}
param infrastructureSubnetId string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
param storageName string
@secure()
param storageAccessKey string
param storageShareName string
param storageMountName string = 'documents-storage'

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    peerAuthentication: {
      mtls: {
        enabled: false
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: storageMountName
  properties: {
    azureFile: {
      accountName: storageName
      accountKey: storageAccessKey
      shareName: storageShareName
      accessMode: 'ReadWrite'
    }
  }
}

output id string = environment.id
output name string = environment.name
output defaultDomain string = environment.properties.defaultDomain
output storageMountName string = environmentStorage.name
