# Azure deployment variants

The executable Bicep implements **Variant A**. The other variants explain when
a different Azure hosting pattern is justified and what would change; they are
not presented as implemented deployment paths.

## Comparison

| Variant | Compute | Ingress | Baseline compute SKU | Best fit | Main trade-off |
|---|---|---|---|---|---|
| A. Container Apps baseline | Two Container Apps + one manual job | Public web, internal API | Consumption with min-one replicas | Small container-native deployment and independent sizing | No deployment slots; long synchronous requests remain |
| B. App Service | Two Linux Web Apps on one plan | Public web; API private endpoint | Standard S1 | Teams preferring fixed capacity and deployment slots | Shared plan capacity and additional private DNS/integration wiring |
| C. Hardened private | Internal Container Apps environment + WAF gateway | Private/WAF-controlled | Consumption or dedicated profile | Regulated access through private network/VPN | Higher gateway/firewall/operations cost |
| D. Foundry IQ grounding | Same compute, different retrieval integration | Same as A or C | Foundry IQ consumption plus Search | Future managed knowledge retrieval | Current code cannot use it without an adapter |

## Variant A: Container Apps baseline

This is the recommended and generated design. It uses a workload-profile
Container Apps environment injected into a `/23` subnet, even though smaller
subnets may be technically possible, to leave room for revisions and scale.
The public web container reverse-proxies to an internal API container.

Use when:

- the team wants independent web/API resource sizing
- internal service ingress is preferred over exposing the API
- container revisions and consumption billing are acceptable
- AKS operations are not justified

## Variant B: App Service Standard S1

A valid alternative uses:

- one Linux App Service Plan, Standard S1
- one custom-container web app and one custom-container API app
- a dedicated `/26` VNet integration subnet
- a private endpoint and `privatelink.azurewebsites.net` zone for the API
- the same PostgreSQL, Files, Key Vault, OpenAI and Search private services
- Easy Auth on the public web app
- Nginx reverse proxy from the web app through VNet integration to the API

Advantages:

- deployment slots and autoscale are available at Standard tier
- fixed capacity is familiar and both apps can share one plan
- built-in App Service backup/operations model

Trade-offs:

- web and API compete for the same plan unless separate plans are purchased
- independent resource sizing is unavailable on a shared plan
- inbound API privacy needs private endpoint and DNS configuration
- source-based mixed Python/Node deployment is less predictable than the
  generated custom-container path

Choose App Service when slots and fixed-plan operations matter more than
per-service resource sizing.

## Variant C: hardened private ingress

For private-only or regulated access:

- set the Container Apps environment to internal
- add Application Gateway WAF_v2 (or an approved enterprise ingress platform)
- route access through VPN/ExpressRoute or a controlled public WAF listener
- add Azure Firewall and UDRs when centralized egress inspection is mandatory
- use ACR Premium with Private Link
- select PostgreSQL zone-redundant HA, Storage ZRS and at least two Search/API/web
  replicas

This variant is materially more expensive and operationally heavier. It should
not be selected only to claim that every endpoint is private; it needs a real
network/compliance requirement.

## Variant D: Foundry IQ

The current application directly calls Azure AI Search indexes and builds its
own hybrid vector request. Microsoft Foundry IQ is therefore not a parameter
switch or drop-in resource replacement.

Adoption requires an application retrieval interface that maps:

- uploaded clauses to Foundry IQ knowledge sources
- policy/document scoping to knowledge-base filters
- Foundry citations back to the platform's evidence references
- freshness/reconciliation to the policy lifecycle

Until that adapter exists, deploy Azure AI Search as generated. See
[AI assistance](ai-assistance.md#how-the-ai-is-grounded) for the current
retrieval boundary.

## SKU profiles

| Service | Baseline | Resilient |
|---|---|---|
| Container Apps | Consumption, web 1-2, API 1-3 | web/API min 2; optionally dedicated workload profile |
| PostgreSQL | Burstable `Standard_B1ms`, 32 GiB, no HA | General Purpose `Standard_D2ds_v5`, 128 GiB, zone-redundant HA |
| AI Search | Standard S1, 1 replica / 1 partition | Standard S1, 2+ replicas / 1+ partitions |
| Storage | `Standard_LRS` | `Standard_ZRS` |
| ACR | Standard, public endpoint + managed identity | Premium + private endpoint |
| Logs | 30 days | 90 days or policy-defined retention |

Actual model quota, regional capacity and prices must be checked for the chosen
subscription and location immediately before deployment.

## Microsoft references

- [Container Apps workload profiles](https://learn.microsoft.com/azure/container-apps/workload-profiles-overview)
- [App Service SKU selection](https://learn.microsoft.com/azure/app-service/overview-hosting-plans)
- [App Service VNet integration](https://learn.microsoft.com/azure/app-service/overview-vnet-integration)
- [Application Gateway WAF](https://learn.microsoft.com/azure/web-application-firewall/ag/ag-overview)
- [Foundry IQ](https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq)
