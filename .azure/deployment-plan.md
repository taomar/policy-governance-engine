# Azure Deployment Plan

> **Status:** Validated - deployment assets only; live subscription preflight remains mandatory

Generated: 2026-08-09

---

## 1. Project Overview

**Goal:** Prepare a complete, deployment-ready Azure design and `azd`/Bicep kit for the Policy Platform without deploying any Azure resources.

**Path:** Modernize an existing local-first application for Azure hosting.

**Deployment boundary:** This work generates documentation, Dockerfiles, Bicep, parameter files, prerequisite checks, bootstrap scripts, and `azure.yaml`. It must not run `azd up`, create resources, migrate existing records, or upload existing documents.

### Fresh-start data decision

The Azure environment starts empty. `alembic upgrade head` initializes the PostgreSQL schema only. The bootstrap process also creates the required Azure AI Search index definitions. It does **not** copy local policies, candidate rules, evaluations, attestations, source files, sample data, or database rows.

---

## 2. Requirements and Assumptions

| Attribute | Value |
|---|---|
| Classification | Small controlled deployment baseline; production-style network boundaries with cost-optimized capacity |
| Scale | Small initial user and document volume |
| Budget | Cost-optimized; no free tiers; lower standard/entry SKUs |
| Subscription | Selected interactively when `azd up` is eventually run |
| Location | Selected interactively when `azd up` is eventually run; must support Azure OpenAI model deployments, Azure AI Search, Container Apps, and PostgreSQL Flexible Server |
| IaC | Bicep, orchestrated by Azure Developer CLI |
| Network | Mandatory VNet with separate delegated and private-endpoint subnets |
| Data start | Fresh PostgreSQL schema and empty document share |
| AI | Required Azure OpenAI plus Azure AI Search grounding |
| Authentication | Microsoft Entra ID gate on the public web entry point; API has internal ingress only |
| Availability | Single-region, non-HA baseline; documented production variant increases redundancy |
| Deployment execution | Explicitly out of scope for this task |

### Application constraints discovered

- FastAPI/Python 3.11 API in `src/policy_platform` with `/health` endpoint.
- React/Vite frontend in `apps/web`; API base URL is injected at build time.
- PostgreSQL is required at startup through async and Alembic connection URLs.
- Uploaded files are written to relative path `data/documents`; durable Azure Files mounting is required without changing application storage code.
- Azure OpenAI and Azure AI Search are called directly over HTTPS with API keys through `httpx`.
- Azure AI Search indexes are data-plane artifacts and must be initialized separately from ARM resource provisioning.
- There is no production authorization model in the application. Infrastructure can authenticate users at ingress, but actor-role authorization remains an application limitation.
- Long extraction/quality requests run synchronously in the API process; the API needs at least one warm replica and deployment documentation must call out ingress timeout limits.

---

## 3. Components Detected

| Component | Type | Technology | Path |
|---|---|---|---|
| Web UI | Frontend | React 19, TypeScript, Vite, Ant Design | `apps/web` |
| Policy API | API | Python 3.11, FastAPI, Uvicorn, Pydantic | `src/policy_platform/api` |
| Deterministic engine | Library | Pure Python evaluator and test runner | `src/policy_platform/evaluator` |
| Persistence | Data access | SQLAlchemy 2, asyncpg, psycopg, Alembic | `src/policy_platform/domain`, `alembic` |
| AI services | Integration | Direct Azure OpenAI REST calls | `src/policy_platform/infrastructure/ai`, `ai_*.py` |
| Grounding | Integration | Azure AI Search hybrid/vector REST calls | `src/policy_platform/infrastructure/search` |
| Document storage | Filesystem | PDF/DOCX upload and extraction | `data/documents`, document router/ingestion modules |
| Schema/search bootstrap | One-time job | Alembic plus Search index initialization | To be generated under `infra/bootstrap` |

---

## 4. Recipe Selection

**Selected:** Azure Developer CLI (`azd`) + Bicep + custom Dockerfiles.

**Rationale:** The repository is Azure-only, contains two independently deployable services, requires multiple managed Azure dependencies, and the user explicitly wants a future `azd up` workflow. Bicep provides direct Azure resource modeling; `azd` supplies environment selection, parameter substitution, image build/push, service deployment, and hooks.

**No deployment command will be run during this task.**

---

## 5. Architecture Decision

### Recommended variant: Azure Container Apps

Container Apps is the best fit because the application is a two-service container workload, benefits from internal API ingress, supports VNet injection and independent resource sizing, and does not need Kubernetes administration.

```text
Internet user
  -> Container Apps built-in Entra authentication
  -> public web Container App (Nginx + React)
  -> same-origin /api reverse proxy
  -> internal API Container App (FastAPI)
  -> private PostgreSQL / Azure Files / Key Vault / Azure OpenAI / Azure AI Search
```

The web app is the only public endpoint. The API uses internal Container Apps ingress. Nginx proxies `/api`, `/docs`, `/redoc`, `/openapi.json`, and `/health` to the API so the browser never needs direct API network access or cross-origin configuration.

### Why not App Service as the default

App Service is viable and is documented as Variant B, using two Linux Web Apps on one Standard S1 plan, VNet integration, and a private endpoint for the API. It provides deployment slots and a familiar fixed-capacity model, but it requires more explicit private-endpoint/DNS wiring between the web proxy and API and cannot size the two components independently within one plan. Container Apps gives the cleaner internal-service boundary for this application.

### Why not AKS

AKS would add cluster, node-pool, upgrade, ingress, and policy operations that this small two-service system does not require.

### Why not Microsoft Agent Framework

The deployment architecture does not introduce MAF. Existing AI flows are fixed request-driven services, not resumable multi-agent workflows.

---

## 6. Recommended Azure Service Mapping and SKUs

| Component | Azure service | Baseline SKU/configuration | Rationale |
|---|---|---|---|
| Web UI | Azure Container Apps | Consumption workload profile, 0.25 vCPU, 0.5 GiB, min 1/max 2 replicas | Low baseline cost, no free tier, always warm, external HTTPS ingress |
| API | Azure Container Apps | Consumption workload profile, 1 vCPU, 2 GiB, min 1/max 3 replicas | PDF/DOCX parsing and AI orchestration need more memory; internal ingress |
| Schema/search initialization | Container Apps Job | Manual trigger, 0.5 vCPU, 1 GiB | Runs Alembic and index initialization from inside the VNet |
| Image registry | Azure Container Registry | Standard, admin disabled | Lower standard tier; managed-identity image pulls. Private Link requires Premium and is reserved for hardened variant |
| Relational database | Azure Database for PostgreSQL Flexible Server | Burstable `Standard_B1ms`, PostgreSQL 16, 32 GiB, 7-day backup, no HA | User-approved entry tier for a fresh small database |
| Uploaded documents | StorageV2 + Azure Files | `Standard_LRS`, 10 GiB share | Persists the existing `data/documents` filesystem contract |
| Secrets | Azure Key Vault | Standard, RBAC, purge protection, private endpoint | Keeps DB/OpenAI/Search keys out of source and Container App plain configuration |
| AI inference | Azure OpenAI | `S0`; three parameterized deployments (reasoning, fast, embedding) | Required by current application; model names/versions remain region-dependent inputs |
| Grounding | Azure AI Search | Standard S1, 1 replica, 1 partition | Non-free lower Standard tier with hybrid/vector support and private endpoint |
| Logging | Log Analytics | Pay-as-you-go, 30-day retention | Container Apps platform and console logs |
| Monitoring | Workspace-based Application Insights | Standard consumption billing | Availability/telemetry surface; code-level tracing requires later instrumentation |
| Stable egress | NAT Gateway + Standard static public IP | Standard | Stable outbound identity for Container Apps workload-profile environment |
| Identity | Managed identities | System identity for ACR pulls; user-assigned runtime identity for Key Vault | Removes registry credentials and limits secret-read permissions |

### Resilient production parameter profile

The same Bicep modules will support a higher profile: PostgreSQL General Purpose `Standard_D2ds_v5` with zone-redundant HA and 14-35 day backup, Search S1 with 2+ replicas, Storage `Standard_ZRS`, API min 2 replicas, web min 2 replicas, ACR Premium with private endpoint, and optional WAF ingress. This is documented but not the default because it conflicts with the requested lower-cost baseline.

---

## 7. Network Topology

One VNet is required. Multiple subnets are necessary because Container Apps and PostgreSQL require exclusive delegated subnets, while private endpoints must not share either delegated subnet.

| Network | Default CIDR | Purpose and rules |
|---|---|---|
| VNet | `10.20.0.0/16` | Deployment boundary; parameterized |
| `snet-container-apps` | `10.20.0.0/23` | Dedicated delegation to `Microsoft.App/environments`; workload-profile environment; NAT Gateway association |
| `snet-postgresql` | `10.20.4.0/24` | Dedicated delegation to `Microsoft.DBforPostgreSQL/flexibleServers`; no public database endpoint |
| `snet-private-endpoints` | `10.20.5.0/24` | Key Vault, Azure Files, Azure OpenAI, and Azure AI Search private endpoints; private endpoint policies disabled |

### Routing and controls

- The baseline uses Azure system routes plus a NAT Gateway on the Container Apps subnet for stable internet egress needed by the public Standard ACR endpoint and Azure control-plane dependencies.
- No forced-tunnel UDR or Azure Firewall is included in the lower-cost baseline. A firewall route is an enterprise variant because it adds cost and requires the full Container Apps outbound allowlist.
- PostgreSQL has private VNet access through its delegated subnet and private DNS; public access is disabled.
- Key Vault, Storage file, Azure OpenAI, and AI Search expose private endpoints only; public network access is disabled.
- ACR Standard remains public-network reachable but accepts managed-identity authenticated pulls over TLS and has the admin account disabled. The hardened profile uses ACR Premium plus Private Link.
- Web ingress is HTTPS only. API ingress is internal to the Container Apps environment.
- Optional ingress CIDR restrictions are parameterized for deployments that should be reachable only from office/VPN ranges.

### Private DNS zones

- `private.postgres.database.azure.com`
- `privatelink.vaultcore.azure.net`
- `privatelink.file.core.windows.net`
- `privatelink.openai.azure.com`
- `privatelink.search.windows.net`

Each zone is linked to the VNet and attached to its corresponding private endpoint/delegated service.

---

## 8. Security Design

- Microsoft Entra built-in authentication protects the public web Container App. The deployment prerequisite guide will explain app registration values and redirect URI updates.
- The API has no public ingress and accepts traffic from the web proxy inside the Container Apps environment.
- TLS is required for every service connection. PostgreSQL URLs include `ssl=require`/`sslmode=require`.
- Key Vault references supply `DATABASE_URL`, `ALEMBIC_DATABASE_URL`, PostgreSQL password, Azure OpenAI key, Azure Search key, and Entra client secret.
- Managed identities pull images and read only required Key Vault secrets.
- ACR admin access and anonymous storage access are disabled.
- Storage enforces HTTPS and TLS 1.2; Azure Files is mounted at `/app/data/documents`.
- PostgreSQL, Key Vault, Storage, OpenAI, and Search public network access is disabled.
- No secret is emitted as a Bicep output or committed to parameter files.
- Deployment operators need Contributor plus User Access Administrator (or Owner) for role assignments, and rights to create model deployments and an Entra app registration.
- Infrastructure authentication does not convert the application's client-supplied actor role into trusted authorization. This remains a documented application risk.

---

## 9. Configuration and Interactive Parameters

`azd up` natively asks for environment name, subscription, and location. A cross-platform preprovision PowerShell hook will ask for any missing custom values, show safe defaults, validate formats, and store them in the local ignored azd environment.

### Required interactive values

- Azure resource group name (default `rg-<environment>`)
- PostgreSQL administrator login and securely entered password
- Entra application client ID and client secret (unless authentication is explicitly disabled for a private test deployment)
- Azure OpenAI reasoning, fast, and embedding model names and versions
- Confirmation that the selected region supports those model deployments

### Defaulted but overridable values

- Container Apps CPU/memory/min/max replicas
- PostgreSQL SKU/storage/backup/HA settings
- Azure AI Search SKU/replicas/partitions
- ACR SKU
- Storage replication and share quota
- VNet/subnet CIDRs
- model deployment names and capacities
- log retention
- allowed ingress CIDRs
- tags and resource name prefix

`infra/main.parameters.json` will contain `${AZD_ENV_VALUE}` placeholders only, never secrets or hard-coded subscription/tenant/resource-group identifiers.

---

## 10. Database and Search Initialization

This is initialization, not migration of existing data.

1. Provision an empty PostgreSQL Flexible Server and empty `policy_platform` database.
2. Deploy web/API images.
3. Update the manual Container Apps bootstrap job to the deployed API image.
4. Run `alembic upgrade head` once from that job inside the VNet.
5. Create or idempotently update the `policy-authoring` and `policy-evidence` Azure AI Search index definitions with the configured embedding dimensions.
6. Record success/failure in the job execution result and stop `azd up` on failure.
7. Do not execute backfill scripts, sample imports, local database dumps, or document uploads.

The application then starts with zero policies and an empty Azure Files share.

---

## 11. Deployment Variants to Document

| Variant | Hosting | Best for | Main trade-off |
|---|---|---|---|
| A - Recommended baseline | Two Azure Container Apps + manual bootstrap job | Small secure deployment with internal API and independent scaling | No deployment slots; synchronous long requests remain an app constraint |
| B - App Service alternative | Two Linux custom-container Web Apps on Standard S1 plan | Teams preferring fixed capacity, deployment slots, and App Service operations | Shared plan sizing and more private endpoint/DNS wiring |
| C - Hardened private ingress | Internal Container Apps environment + WAF/Application Gateway, Premium ACR | Regulated/private-access environments | Significantly higher networking and operations cost |
| D - Foundry IQ grounding | Replace direct Search calls with a Foundry IQ adapter | Future managed knowledge/agentic retrieval | Not deployable by current code; requires application integration first |

Only Variant A receives executable Bicep in this delivery. Other variants receive architecture, SKU, parameter, security, and migration guidance so they are not confused with implemented deployment paths.

---

## 12. Provisioning Limit and Region Preflight

No subscription or region is selected because this task must not deploy and the user requires those values to be chosen later through `azd up`. Therefore current subscription usage cannot be queried now. The generated kit will include a mandatory, read-only `infra/scripts/Test-AzurePrerequisites.ps1` preflight that runs before provisioning and exits before resource creation if any check fails.

| Resource type | Planned quantity | Deployment-time validation |
|---|---:|---|
| `Microsoft.App/managedEnvironments` | 1 | Container Apps environment quota and regional availability |
| `Microsoft.App/containerApps` | 2 | App count and Consumption workload capacity |
| `Microsoft.App/jobs` | 1 | Job availability |
| `Microsoft.Network/virtualNetworks` | 1 | VNet limit |
| `Microsoft.Network/publicIPAddresses` | 1 | Standard public IP quota |
| `Microsoft.Network/natGateways` | 1 | NAT Gateway limit |
| `Microsoft.Network/privateEndpoints` | 4 | Private endpoint limit |
| `Microsoft.ContainerRegistry/registries` | 1 | Registry availability |
| `Microsoft.DBforPostgreSQL/flexibleServers` | 1 | `Standard_B1ms` regional availability |
| `Microsoft.Storage/storageAccounts` | 1 | Storage account quota |
| `Microsoft.KeyVault/vaults` | 1 | Vault limit |
| `Microsoft.Search/searchServices` | 1 | Search service quota and S1 availability |
| `Microsoft.CognitiveServices/accounts` | 1 | Azure OpenAI regional availability |
| `Microsoft.CognitiveServices/accounts/deployments` | 3 | Model availability and TPM quota |
| `Microsoft.OperationalInsights/workspaces` | 1 | Workspace limit |
| `Microsoft.Insights/components` | 1 | Application Insights availability |

The preflight uses `az quota` first for supported providers, falls back to Azure Resource Graph and official service-limit documentation where quota CLI is unsupported, verifies provider registration, checks address-prefix overlap, and verifies model availability in the chosen location. This is intentionally a deployment-time check, not an unverified claim in this documentation-only phase.

---

## 13. WAF Trade-off Assessment

| Pillar | Baseline decision | Trade-off |
|---|---|---|
| Security | VNet, private data/AI endpoints, Key Vault, managed identity, Entra ingress gate | ACR Standard uses a secured public endpoint; application role authorization is still weak |
| Reliability | Durable PostgreSQL and Azure Files, min-one replicas, health probes, bootstrap job | Single region, single PostgreSQL zone, one Search replica, no queue for long work |
| Performance efficiency | Independently sized web/API, hybrid Search S1, API 1 vCPU/2 GiB | B1ms can throttle and synchronous AI requests can approach ingress timeouts |
| Cost optimization | Consumption compute, B1ms PostgreSQL, S1 Search, Standard_LRS, Standard ACR | Lower resilience; Azure OpenAI usage remains variable and should have budgets/quotas |
| Operational excellence | Bicep, azd, deterministic bootstrap, Log Analytics, App Insights, what-if/preflight | CI/CD remains outside this task; code-level tracing is not yet instrumented |

---

## 14. Files to Generate After Approval

| File | Purpose | Status |
|---|---|---|
| `.azure/deployment-plan.md` | Source-of-truth plan | Complete, awaiting approval |
| `azure.yaml` | Two-service azd configuration and non-deploying hooks | Pending approval |
| `infra/main.bicep` | Subscription-scope resource group and module orchestration | Pending approval |
| `infra/main.parameters.json` | azd environment substitutions | Pending approval |
| `infra/modules/*.bicep` | Network, observability, identities, registry, data, AI, private endpoints, Container Apps | Pending approval |
| `infra/search/*.json` | Search index schemas | Pending approval |
| `infra/scripts/Initialize-AzdEnvironment.ps1` | Interactive missing-parameter collection | Pending approval |
| `infra/scripts/Test-AzurePrerequisites.ps1` | Read-only provider/quota/region/model/network checks | Pending approval |
| `infra/scripts/Invoke-PostDeployBootstrap.ps1` | Future schema/index initialization hook | Pending approval |
| `infra/bootstrap/initialize.py` | Idempotent schema/index initialization, no sample data | Pending approval |
| `Dockerfile` | API container build | Pending approval |
| `apps/web/Dockerfile` | React/Nginx container build | Pending approval |
| `apps/web/nginx.conf.template` | SPA routing and same-origin API proxy | Pending approval |
| `docs/azure-deployment.md` | Complete recommended deployment guide | Pending approval |
| `docs/azure-deployment-variants.md` | Container Apps, App Service, hardened, Foundry IQ comparisons | Pending approval |
| `docs/azure-prerequisites.md` | Tools, roles, providers, Entra, quotas, DNS and region checks | Pending approval |
| `docs/azure-operations.md` | Initialization, scaling, backup, restore, rotation, troubleshooting | Pending approval |

---

## 15. Validation Plan

No resources are provisioned by validation. The validated scope is the portable
deployment kit:

- azd project schema and local authentication availability
- Bicep compilation and linting
- complete API and web container builds
- Docker build contexts and lock file
- parameter-source and literal-secret checks
- Search JSON, bootstrap Python and PowerShell hook syntax
- static least-privilege RBAC review
- documentation links, code fences and Git whitespace
- confirmation that no Azure provisioning/deployment command ran

The application test suite is not part of this deployment-artifact validation.
Live `azd provision --preview`, regional quota/model checks and Azure Policy
checks intentionally run later, after the operator selects subscription,
location and secret inputs. `PreProvision.ps1` blocks a future deployment when
those checks fail.

### Validation proof

Validated: 2026-08-09T07:30:33+03:00

| Check | Command/evidence | Result |
|---|---|---|
| azd installation and schema | `azd version`; `azd show --output json` | Pass; project and both services parsed |
| azd authentication availability | `azd auth login --check-status` | Pass |
| Bicep compile and lint | `az bicep build --file infra/main.bicep --stdout`; `az bicep lint --file infra/main.bicep` | Pass; no template/linter finding |
| API image | `docker build -t policy-platform-api:validation -f Dockerfile .` using the approved Microsoft PyPI proxy | Pass |
| Web image | `docker build -t policy-platform-web:validation -f apps/web/Dockerfile apps/web` | Pass |
| Container contents | API/bootstrap import check; `nginx -t`; built SPA index check | Pass |
| Docker contexts | Both `docker build --check`; `apps/web/package-lock.json` present | Pass |
| Parameters and secrets | Automated inventory of all 52 `${...}` parameter sources plus literal-credential scan | Pass |
| Bootstrap and schemas | JSON parse, Python compile, PowerShell parser | Pass |
| RBAC | Static review of 3 AcrPull and 2 Key Vault Secrets User assignments | Pass; resource scoped |
| Documentation | Relative-link, fence and 31-Mermaid-block structural checks | Pass |
| Git integrity | `git diff --check`; `git diff --cached --check` | Pass |
| Subscription/location | Not selected by design | Deployment-time gate in `PreProvision.ps1` |
| ARM preview and Azure Policy | Not run without a target subscription/location | Mandatory immediately before future deployment |
| Deployment | `azd up` / `azd provision` / Azure create commands | Not run, as required |

### Role assignment verification

- API and web system identities: `AcrPull` on the generated registry only.
- Bootstrap user-assigned identity: `AcrPull` on the generated registry only.
- API user-assigned identity: `Key Vault Secrets User` on the generated vault.
- Web user-assigned identity: `Key Vault Secrets User` on the generated vault.
- PostgreSQL, OpenAI and Search use application-compatible secrets held in Key
  Vault; no broad Contributor/Owner data-plane role is assigned to a workload.

---

## 16. Execution Checklist

### Planning

- [x] Create plan skeleton before infrastructure generation
- [x] Analyze workspace and dependencies
- [x] Gather scale, budget, networking, AI, and fresh-data requirements
- [x] Select azd + Bicep recipe
- [x] Select Container Apps as recommended hosting
- [x] Define resource inventory, SKU defaults, security, and variants
- [x] Define deployment-time quota and region preflight
- [x] User approved the plan and confirmed Azure assets belong under `infra/`

### Artifact generation

- [x] Generate azd/Bicep/Docker/bootstrap artifacts
- [x] Generate Azure deployment and variant documentation
- [x] Update plan status to `Ready for Validation`

### Validation

- [x] Invoke `azure-validate`
- [x] All validation checks pass
  - [x] azd installation and project-schema validation
  - [x] Azure authentication availability check
  - [x] Subscription/location check deferred explicitly to future `azd up`
  - [x] Provision preview deferred explicitly until subscription/location/secrets are selected
  - [x] Bicep build and lint
  - [x] API and web container build verification
  - [x] Docker build-context and lock-file validation
  - [x] Bootstrap/Search schema and PowerShell hook syntax validation
  - [x] Parameter-source completeness and no-secret static scan
  - [x] Static RBAC role verification
  - [x] Azure policy validation deferred to the future selected subscription
  - [x] Documentation links and formatting validation
  - [x] Confirm no provisioning/deployment command was run
- [x] Resolve all validation findings
- [x] Record validation proof
- [x] Set plan status to `Validated`

### Deployment

- [ ] Not part of this task; do not invoke `azure-deploy` or run `azd up`

---

## 17. Official Microsoft References

- [Azure Container Apps networking](https://learn.microsoft.com/azure/container-apps/networking)
- [Authentication in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/authentication)
- [Azure Database for PostgreSQL private networking](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-networking-private)
- [Azure Database for PostgreSQL compute tiers](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-compute)
- [Azure AI Search service tiers](https://learn.microsoft.com/azure/search/search-sku-tier)
- [Azure AI Search network controls](https://learn.microsoft.com/azure/search/service-configure-firewall)
- [Azure AI services virtual networks](https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks)
- [Azure Key Vault Private Link](https://learn.microsoft.com/azure/key-vault/general/private-link-service)
- [Azure Container Registry tiers](https://learn.microsoft.com/azure/container-registry/container-registry-skus)
- [Azure Developer CLI schema](https://learn.microsoft.com/azure/developer/azure-developer-cli/azd-schema)
- [Bicep what-if](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if)

---

## 18. Approval Gate

Current phase: deployment kit validated. Live subscription preflight and deployment are intentionally not executed.
