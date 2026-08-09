targetScope = 'resourceGroup'

param vaultName string
param postgresServerFqdn string
param postgresAdministratorLogin string
@secure()
param postgresAdministratorPassword string
param postgresDatabaseName string
param openAiAccountName string
param searchServiceName string
param enableEntraAuthentication bool
@secure()
param entraClientSecret string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
}

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

resource search 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: searchServiceName
}

var asyncDatabaseUrl = 'postgresql+asyncpg://${postgresAdministratorLogin}:${postgresAdministratorPassword}@${postgresServerFqdn}:5432/${postgresDatabaseName}?ssl=require'
var syncDatabaseUrl = 'postgresql+psycopg://${postgresAdministratorLogin}:${postgresAdministratorPassword}@${postgresServerFqdn}:5432/${postgresDatabaseName}?sslmode=require'

resource postgresPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'postgres-admin-password'
  properties: {
    value: postgresAdministratorPassword
    contentType: 'text/plain'
  }
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: asyncDatabaseUrl
    contentType: 'text/plain'
  }
}

resource alembicDatabaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'alembic-database-url'
  properties: {
    value: syncDatabaseUrl
    contentType: 'text/plain'
  }
}

resource openAiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'azure-openai-api-key'
  properties: {
    value: openAi.listKeys().key1
    contentType: 'text/plain'
  }
}

resource searchKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'azure-search-api-key'
  properties: {
    value: search.listAdminKeys().primaryKey
    contentType: 'text/plain'
  }
}

resource entraSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (enableEntraAuthentication) {
  parent: vault
  name: 'entra-client-secret'
  properties: {
    value: entraClientSecret
    contentType: 'text/plain'
  }
}

output databaseUrlSecretUri string = '${vault.properties.vaultUri}secrets/${databaseUrlSecret.name}'
output alembicDatabaseUrlSecretUri string = '${vault.properties.vaultUri}secrets/${alembicDatabaseUrlSecret.name}'
#disable-next-line outputs-should-not-contain-secrets
output postgresPasswordSecretUri string = '${vault.properties.vaultUri}secrets/${postgresPasswordSecret.name}'
output openAiKeySecretUri string = '${vault.properties.vaultUri}secrets/${openAiKeySecret.name}'
output searchKeySecretUri string = '${vault.properties.vaultUri}secrets/${searchKeySecret.name}'
output entraClientSecretUri string = enableEntraAuthentication ? '${vault.properties.vaultUri}secrets/${entraSecret.name}' : ''
