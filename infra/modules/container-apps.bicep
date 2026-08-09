targetScope = 'resourceGroup'

param environmentId string
param storageMountName string
param containerRegistryServer string
param location string = resourceGroup().location
param tags object = {}
param apiName string
param webName string
param bootstrapJobName string
param apiIdentityId string
param apiIdentityClientId string
param webIdentityId string
param webIdentityClientId string
param applicationInsightsConnectionString string
param databaseUrlSecretUri string
param alembicDatabaseUrlSecretUri string
param postgresPasswordSecretUri string
param openAiKeySecretUri string
param searchKeySecretUri string
param entraClientSecretUri string
param enableEntraAuthentication bool
param entraTenantId string
param entraClientId string
param openAiEndpoint string
param openAiApiVersion string
param openAiReasoningDeploymentName string
param openAiFastDeploymentName string
param openAiEmbeddingDeploymentName string
param openAiEmbeddingModelName string
param openAiEmbeddingDimensions int
param searchEndpoint string
param searchApiVersion string
param searchAuthoringIndexName string
param searchEvidenceIndexName string
param postgresHost string
param postgresPort int = 5432
param postgresDatabaseName string
param postgresAdministratorLogin string
param allowedIngressCidrs string = ''
param webMinReplicas int = 1
param webMaxReplicas int = 2
param apiMinReplicas int = 1
param apiMaxReplicas int = 3

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var ingressCidrs = empty(trim(allowedIngressCidrs)) ? [] : split(replace(allowedIngressCidrs, ' ', ''), ',')
var ingressRestrictions = [for (cidr, index) in ingressCidrs: {
  name: 'allow-${index}'
  action: 'Allow'
  ipAddressRange: cidr
  description: 'Allowed deployment ingress CIDR.'
}]

var apiSecrets = [
  {
    name: 'database-url'
    keyVaultUrl: databaseUrlSecretUri
    identity: apiIdentityId
  }
  {
    name: 'alembic-database-url'
    keyVaultUrl: alembicDatabaseUrlSecretUri
    identity: apiIdentityId
  }
  {
    name: 'postgres-password'
    keyVaultUrl: postgresPasswordSecretUri
    identity: apiIdentityId
  }
  {
    name: 'azure-openai-api-key'
    keyVaultUrl: openAiKeySecretUri
    identity: apiIdentityId
  }
  {
    name: 'azure-search-api-key'
    keyVaultUrl: searchKeySecretUri
    identity: apiIdentityId
  }
]

var webSecrets = enableEntraAuthentication ? [
  {
    name: 'entra-client-secret'
    keyVaultUrl: entraClientSecretUri
    identity: webIdentityId
  }
] : []

var commonApiEnv = [
  {
    name: 'ENVIRONMENT'
    value: 'production'
  }
  {
    name: 'LOG_LEVEL'
    value: 'INFO'
  }
  {
    name: 'API_HOST'
    value: '0.0.0.0'
  }
  {
    name: 'API_PORT'
    value: '8010'
  }
  {
    name: 'DEV_AUTH_ENABLED'
    value: 'false'
  }
  {
    name: 'DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'ALEMBIC_DATABASE_URL'
    secretRef: 'alembic-database-url'
  }
  {
    name: 'POSTGRES_HOST'
    value: postgresHost
  }
  {
    name: 'POSTGRES_PORT'
    value: string(postgresPort)
  }
  {
    name: 'POSTGRES_DB'
    value: postgresDatabaseName
  }
  {
    name: 'POSTGRES_USER'
    value: postgresAdministratorLogin
  }
  {
    name: 'POSTGRES_PASSWORD'
    secretRef: 'postgres-password'
  }
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: openAiEndpoint
  }
  {
    name: 'AZURE_OPENAI_API_KEY'
    secretRef: 'azure-openai-api-key'
  }
  {
    name: 'AZURE_OPENAI_API_VERSION'
    value: openAiApiVersion
  }
  {
    name: 'AZURE_OPENAI_DEPLOYMENT'
    value: openAiReasoningDeploymentName
  }
  {
    name: 'AZURE_OPENAI_FAST_DEPLOYMENT'
    value: openAiFastDeploymentName
  }
  {
    name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
    value: openAiEmbeddingDeploymentName
  }
  {
    name: 'AZURE_OPENAI_EMBEDDING_MODEL'
    value: openAiEmbeddingModelName
  }
  {
    name: 'AZURE_OPENAI_EMBEDDING_DIMENSIONS'
    value: string(openAiEmbeddingDimensions)
  }
  {
    name: 'AZURE_SEARCH_ENDPOINT'
    value: searchEndpoint
  }
  {
    name: 'AZURE_SEARCH_API_KEY'
    secretRef: 'azure-search-api-key'
  }
  {
    name: 'AZURE_SEARCH_API_VERSION'
    value: searchApiVersion
  }
  {
    name: 'AZURE_SEARCH_AUTHORING_INDEX'
    value: searchAuthoringIndexName
  }
  {
    name: 'AZURE_SEARCH_EVIDENCE_INDEX'
    value: searchEvidenceIndexName
  }
  {
    name: 'AZURE_CLIENT_ID'
    value: apiIdentityClientId
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: applicationInsightsConnectionString
  }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: union(tags, {
    'azd-service-name': 'api'
  })
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${apiIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        allowInsecure: false
        clientCertificateMode: 'Ignore'
        targetPort: 8010
        transport: 'auto'
      }
      maxInactiveRevisions: 5
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: placeholderImage
          env: commonApiEnv
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          volumeMounts: [
            {
              volumeName: 'documents'
              mountPath: '/app/data/documents'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8010
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8010
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      volumes: [
        {
          name: 'documents'
          storageName: storageMountName
          storageType: 'AzureFile'
        }
      ]
    }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: webName
  location: location
  tags: union(tags, {
    'azd-service-name': 'web'
  })
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${webIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        clientCertificateMode: 'Ignore'
        targetPort: 8080
        transport: 'auto'
        ipSecurityRestrictions: ingressRestrictions
      }
      maxInactiveRevisions: 5
      secrets: webSecrets
    }
    template: {
      containers: [
        {
          name: 'web'
          image: placeholderImage
          env: [
            {
              name: 'API_UPSTREAM'
              value: 'https://${api.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'NGINX_ENVSUBST_FILTER'
              value: 'API_UPSTREAM'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: webIdentityClientId
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        minReplicas: webMinReplicas
        maxReplicas: webMaxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

resource webAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (enableEntraAuthentication) {
  parent: web
  name: 'current'
  properties: {
    globalValidation: {
      redirectToProvider: 'azureActiveDirectory'
      unauthenticatedClientAction: 'RedirectToLoginPage'
    }
    httpSettings: {
      requireHttps: true
      routes: {
        apiPrefix: '/.auth'
      }
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        isAutoProvisioned: false
        registration: {
          clientId: entraClientId
          clientSecretSettingName: 'entra-client-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${entraTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            entraClientId
            'api://${entraClientId}'
          ]
          defaultAuthorizationPolicy: {
            allowedPrincipals: {}
          }
        }
      }
    }
    login: {
      preserveUrlFragmentsForLogins: true
      tokenStore: {
        enabled: true
      }
    }
    platform: {
      enabled: true
      runtimeVersion: '~1'
    }
  }
}

resource bootstrapJob 'Microsoft.App/jobs@2024-03-01' = {
  name: bootstrapJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${apiIdentityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: apiSecrets
      registries: [
        {
          server: containerRegistryServer
          identity: apiIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'initialize'
          image: placeholderImage
          command: ['python']
          args: ['-m', 'infra.bootstrap.initialize']
          env: commonApiEnv
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
}

output apiName string = api.name
output apiPrincipalId string = api.identity.principalId
output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output webName string = web.name
output webPrincipalId string = web.identity.principalId
output webFqdn string = web.properties.configuration.ingress.fqdn
output webUrl string = 'https://${web.properties.configuration.ingress.fqdn}'
output bootstrapJobName string = bootstrapJob.name
