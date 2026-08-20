# Azure deployment options

**Azure deployment is pending.** The repository provides executable Bicep for Azure Container Apps only. Other options are design guidance.

## Support

| Option | Repository support | Use when |
|---|---|---|
| Container Apps | Implemented and statically validated | Default Azure deployment |
| App Service | Architecture guidance | Deployment slots/fixed plan are mandatory |
| Private-network Container Apps | Architecture guidance | Enterprise WAF/private ingress is mandatory |
| Azure AI Search grounding | Implemented | Current retrieval layer |
| Foundry IQ grounding | Future design | Managed knowledge retrieval after an adapter exists |

No option migrates Local deployment data. Azure starts with an empty PostgreSQL database, empty document share, and initialized Search schemas.

## Recommended: Container Apps

- Public React/Nginx web app with Entra ingress authentication.
- Internal FastAPI app.
- Same-origin Nginx API proxy.
- VNet-integrated Container Apps environment.
- Private PostgreSQL, Key Vault, Azure Files, Azure OpenAI, and AI Search.
- Manual initialization job for Alembic and Search schemas.

### Baseline capacity

| Component | Baseline |
|---|---|
| Web | 0.25 vCPU / 0.5 GiB, 1-2 replicas |
| API | 1 vCPU / 2 GiB, 1-3 replicas |
| PostgreSQL | Burstable `Standard_B1ms`, 32 GiB |
| Search | Standard S1, 1 replica / 1 partition |
| Storage | `Standard_LRS`, 10 GiB |
| ACR | Standard |

This option keeps the API private and lets web/API scale independently without Kubernetes administration.

## App Service

Target design:

- two Linux custom-container Web Apps;
- public Entra-protected web app;
- API private endpoint;
- web VNet integration to the API;
- dedicated initialization procedure.

Choose it only when App Service operational standards or deployment slots matter more than independent web/API sizing. No App Service Bicep is included.

## Private-network Container Apps

Target design:

- internal Container Apps environment;
- Application Gateway WAF or approved enterprise ingress;
- VPN/ExpressRoute or controlled public WAF listener;
- ACR Premium with Private Link;
- two or more web/API replicas;
- PostgreSQL HA and Storage ZRS;
- optional Firewall/UDR when centralized egress inspection is required.

This option adds material cost and network ownership. Use it only for an explicit private-ingress, WAF, egress-inspection, or zone-resilience requirement.

## Resilient capacity profile

The supplied resilient profile increases capacity and redundancy within one region:

| Service | Baseline | Resilient |
|---|---|---|
| Container Apps | Web 1-2, API 1-3 | Web/API 2-5 |
| PostgreSQL | B1ms, no HA | D2ds_v5, zone-redundant HA |
| Search | 1 replica | 2 replicas |
| Files | LRS, 10 GiB | ZRS, 100 GiB |
| ACR | Standard | Premium |

It is not a multi-region disaster-recovery design.

## Grounding

Azure AI Search is implemented directly. Foundry IQ is not integrated and is not a drop-in replacement; adoption requires a retrieval abstraction and citation/ scope mapping.

## Selection checklist

1. Is private application ingress mandatory?
2. Are deployment slots or a fixed App Service plan mandatory?
3. What availability target is required?
4. Who owns DNS, certificates, WAF, and egress controls?
5. Are Azure OpenAI model and Search quotas available in the selected region?
6. Has the chosen option been implemented and live-tested?

See [Azure deployment](azure-deployment.md) and [Azure prerequisites](azure-prerequisites.md).
