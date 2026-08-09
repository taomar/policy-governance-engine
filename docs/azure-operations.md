# Azure operations

This runbook applies after the pending Azure Container Apps deployment is
provisioned. It does not imply that an Azure environment currently exists.

## Initialization

The postdeploy hook runs a manual Container Apps job using the deployed API
image. The job:

1. applies every Alembic revision to the empty Azure PostgreSQL database
2. creates or idempotently updates both Azure AI Search index definitions
3. exits nonzero if either boundary fails
4. imports no policy or document data

Inspect executions:

```powershell
az containerapp job execution list \
  --resource-group <resource-group> \
  --name <bootstrap-job> -o table
```

Rerun initialization after a schema or index-definition change:

```powershell
.\infra\scripts\Invoke-PostDeployBootstrap.ps1
```

Do not run repository backfill scripts on a fresh database.

## Logs and health

- Public web health: `<WEB_URL>/healthz`
- API health from inside the environment: `/health`
- Container console/system logs: Log Analytics
- Initialization output: Container Apps job execution logs

Useful commands:

```powershell
az containerapp logs show -g <rg> -n <web-app> --follow
az containerapp logs show -g <rg> -n <api-app> --follow
az containerapp job logs show -g <rg> -n <bootstrap-job> --execution <execution-name>
```

Application Insights is provisioned as a workspace-based resource. Platform
logs are immediate; application traces/dependencies require future Python
instrumentation.

## Scaling

Baseline replicas are intentionally small:

```powershell
azd env set AZURE_WEB_MIN_REPLICAS 1
azd env set AZURE_WEB_MAX_REPLICAS 2
azd env set AZURE_API_MIN_REPLICAS 1
azd env set AZURE_API_MAX_REPLICAS 3
```

Change parameters and reprovision rather than applying undocumented portal
drift. Scale PostgreSQL from Burstable to General Purpose when CPU credits,
connections or extraction latency show sustained pressure. Add a second Search
replica for query availability before treating the platform as production HA.

## Long-running requests

Extraction, quality and correlation currently execute synchronously. The Nginx
proxy timeout is 240 seconds, matching the practical Container Apps ingress
boundary. Operations longer than that need an application-level durable job
pattern; increasing only proxy timeouts is not a reliable fix.

## Backup and restore

PostgreSQL Flexible Server automated backup retention defaults to seven days.
The baseline is not zone redundant and geo-redundant backup is disabled.
Document and test point-in-time restore before production use.

Azure Files uses soft-deleted shares for seven days but `Standard_LRS` is not
zone redundant. Use the resilient profile (`Standard_ZRS`) where regional-zone
resilience is required.

## Secret rotation

OpenAI and Search account keys are stored in Key Vault. To rotate:

1. regenerate the secondary service key
2. update the corresponding Key Vault secret
3. create a new Container Apps revision or restart replicas
4. verify the new key
5. regenerate the former primary key

Rotate the PostgreSQL password in PostgreSQL and both database URL secrets as
one controlled change. Rotate the Entra client secret before expiration and
update `entra-client-secret` in Key Vault.

## Search freshness

Document upload indexes clauses best-effort. If indexing fails, the document
can exist in PostgreSQL/Azure Files without Search entries. Monitor warning
logs and use a controlled re-index procedure; the current application has no
scheduled reconciliation job.

The initialization job owns index **schema**, not document ingestion.

## Deployment rollback

Container Apps preserves inactive revisions. Roll back service code by shifting
traffic to a known-good revision. Database schema rollback is separate: Alembic
migrations may not be safely reversible after data exists. Prefer a forward fix
and restore from PostgreSQL backup only for a tested recovery scenario.

Bicep changes should be previewed with what-if and applied through azd to avoid
portal drift.

## Cost controls

- set Azure budgets and alerts before deployment
- monitor Azure OpenAI token usage and model quota
- monitor Search replicas/partitions and PostgreSQL CPU credits
- retain min-one replicas only where cold starts are unacceptable
- review NAT Gateway and Log Analytics ingestion, which can be material at low
  application volume

## Security operations

- review Key Vault secret access and role assignments
- keep the API internal and verify public access remains disabled on data/AI
  services
- audit Entra app owners, credentials and redirect URIs
- remember that infrastructure authentication does not yet make application
  actor roles authoritative
- use the private-network deployment option when private ingress, WAF or centralized egress
  inspection is a real requirement

## Official references

- [Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions)
- [Container Apps logs](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [PostgreSQL backup and restore](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-backup-restore)
- [Key Vault monitoring](https://learn.microsoft.com/azure/key-vault/general/monitor-key-vault)
- [Azure AI Search monitoring](https://learn.microsoft.com/azure/search/monitor-azure-cognitive-search)
