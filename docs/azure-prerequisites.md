# Azure deployment prerequisites

Complete these prerequisites before any future `azd up`. The generated scripts check them but do not install tools, register providers, request quota or create resources automatically.

## Local tools

Install current supported releases of:

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-windows)
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Docker Desktop](https://learn.microsoft.com/virtualization/windowscontainers/quick-start/set-up-environment)
- PowerShell 7
- Git

Verify and update before deployment:

```powershell
az version
azd version
docker version
$PSVersionTable.PSVersion
az bicep version

winget upgrade Microsoft.Azd
az bicep upgrade
```

The repository was authored against Python 3.11 and Node 22 container images; local Python/Node are useful for validation but not required by `azd` builds.

## Approved package feeds

The API container defaults to the approved PyPI proxy:

```text
https://packagefeedproxy.microsoft.io/pypi/simple
```

Override Docker build argument `PIP_INDEX_URL` only when an approved environment requires another mirror. The supplied NuGet feed `https://packagefeedproxy.microsoft.io/nuget/v3/index.json` is not consumed by the current Python/React build because the repository contains no .NET project.

The web image currently uses `npm ci` and its committed `package-lock.json`. No organization-approved npm proxy was supplied; configure one before a remote build if direct npm registry access is not permitted.

## Azure identity and permissions

The deployment operator needs:

- Contributor on the target subscription or resource-group scope
- User Access Administrator (or Owner) where managed-identity role assignments are created
- permission to create Azure OpenAI deployments
- permission to read quotas and provider registration
- permission to create/update the selected Microsoft Entra app registration

Use the least-privileged scope allowed by organizational policy.

## Select the azd environment

```powershell
azd auth login
azd env new policy-dev
```

A future `azd up` asks for the subscription and location. The location must support all three chosen Azure OpenAI model/version/SKU combinations, Container Apps, PostgreSQL Flexible Server and AI Search.

## Resource providers

Check registration:

```powershell
$providers = @(
  'Microsoft.App', 'Microsoft.Authorization', 'Microsoft.CognitiveServices',
  'Microsoft.ContainerRegistry', 'Microsoft.DBforPostgreSQL',
  'Microsoft.Insights', 'Microsoft.KeyVault', 'Microsoft.ManagedIdentity',
  'Microsoft.Network', 'Microsoft.OperationalInsights', 'Microsoft.Search',
  'Microsoft.Storage'
)
$providers | ForEach-Object {
  az provider show --namespace $_ --query "{provider:namespace,state:registrationState}" -o table
}
```

Register a missing provider only after authorization from the subscription owner:

```powershell
az provider register --namespace <provider-name>
```

## Quota preflight

Install the Azure CLI quota extension:

```powershell
az extension add --name quota
```

`infra/scripts/Test-AzurePrerequisites.ps1` uses `az quota` for supported providers and verifies that Container Apps quota can be read. Azure OpenAI model availability and TPM capacity are regional; the selected models must be confirmed before provisioning.

No quota is assumed by the documentation because subscription and location are intentionally deployment-time choices.

## Microsoft Entra application

Container Apps built-in authentication needs an app registration. Create or select a single-tenant web application and a client secret according to your organization's credential policy. Record:

- tenant ID
- application/client ID
- client secret value

The initial callback URL is not known until Container Apps is provisioned. The postdeploy script adds:

```text
<WEB_URL>/.auth/login/aad/callback
```

The operator running `azd up` must be allowed to update that registration. If an identity team owns registrations, provide the final `WEB_URL` to that team and run the postdeploy step only after they add the callback.

A client secret is a deployment compromise, not the preferred long-term credential. Rotate it before expiry and consider a federated/managed pattern when Container Apps authentication supports the organization's target design.

## Network ranges

Defaults:

```text
VNet                         10.20.0.0/16
Container Apps subnet        10.20.0.0/23
PostgreSQL subnet            10.20.4.0/24
Private endpoints subnet     10.20.5.0/24
```

Change these azd values if they overlap connected VNets, VPN routes or on-premises networks. Delegated subnets must remain exclusive to their service.

## Required interactive values

The preprovision hook asks for missing values and persists them in the selected local azd environment (ignored by Git):

- resource group and resource prefix
- PostgreSQL administrator login and URI-safe password
- Entra tenant/client ID and client secret
- OpenAI reasoning and fast model names/versions
- deployment names (safe defaults are offered)

Model deployment capacity, SKUs, network ranges, replicas and retention have baseline defaults and can be overridden with `azd env set`.

## Run the read-only check

After selecting the subscription and location:

```powershell
.\infra\scripts\Initialize-AzdEnvironment.ps1
.\infra\scripts\Test-AzurePrerequisites.ps1
```

These scripts create or update local azd environment values and read Azure metadata. They do not create Azure resources. Do not continue to `azd up` until the prerequisite check succeeds.

## Secrets and source control

Never commit:

- `.env`
- `.azure/<environment>/.env`
- PostgreSQL passwords
- Entra client secrets
- OpenAI or Search keys

Bicep obtains newly created OpenAI/Search keys and writes them directly to Key Vault. Container Apps consume versionless Key Vault references.

## Official references

- [Azure quotas overview](https://learn.microsoft.com/azure/quotas/quotas-overview)
- [Azure resource provider registration](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types)
- [Microsoft identity platform app registration](https://learn.microsoft.com/entra/identity-platform/quickstart-register-app)
- [Container Apps Microsoft Entra authentication](https://learn.microsoft.com/azure/container-apps/authentication-azure-active-directory)
- [Azure OpenAI model availability](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/models)
