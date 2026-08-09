# Azure infrastructure

This folder contains the deployment-ready Azure design for the Policy Platform.
It is prepared for Azure Developer CLI and Bicep, but no Azure deployment was
run while generating it.

## Layout

```text
infra/
  main.bicep                  Subscription-scope entry point
  main.parameters.json        azd environment substitutions
  modules/                    Resource-group Bicep modules
  parameters/                 Baseline and resilient non-secret profiles
  search/                     Azure AI Search index schemas
  bootstrap/                  Fresh schema/index initialization
  scripts/                    Prompt, prerequisite and postdeploy hooks
  local/                      Existing local PostgreSQL Docker Compose setup
```

`azure.yaml` remains at the repository root because that is where `azd` looks
for project configuration. The API and web Dockerfiles remain beside their
build contexts.

## Recommended baseline

- Azure Container Apps Consumption workload profile, with one public web app
  and one internal API app
- Azure Database for PostgreSQL Flexible Server `Standard_B1ms`
- Azure AI Search Standard S1
- Azure OpenAI S0 with parameterized model deployments
- ACR Standard with managed-identity pulls and admin access disabled
- StorageV2 `Standard_LRS` with a private Azure Files share
- Key Vault Standard, private endpoints, Log Analytics and Application Insights
- VNet-integrated Container Apps, delegated PostgreSQL subnet, private-endpoint
  subnet and NAT Gateway

No free service tier is selected. The API Docker build uses the approved Microsoft PyPI proxy (`packagefeedproxy.microsoft.io/pypi/simple`).

## Future deployment flow

```powershell
azd auth login
azd env new <environment-name>
azd up
```

`azd up` asks for subscription and location. `PreProvision.ps1` asks for missing
resource group, PostgreSQL, Entra and Azure OpenAI model values, then runs a
read-only prerequisite/quota check. After service images deploy,
`PostDeploy.ps1` configures the Entra redirect URI and runs the one-time
Container Apps initialization job.

The job applies `alembic upgrade head` and creates the Search index schemas. It
does not import local policies, documents, samples or database rows.

See [Azure deployment](../docs/azure-deployment.md),
[prerequisites](../docs/azure-prerequisites.md),
[variants](../docs/azure-deployment-variants.md), and
[operations](../docs/azure-operations.md).
