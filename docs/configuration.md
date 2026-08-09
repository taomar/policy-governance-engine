# Configuration and operations

Environment variables, how to run and test, and the operational posture. For
what each framework does and where it is initialised, see
[Frameworks and technologies](frameworks.md).

## Environment

All configuration lives in a `.env` file at the repository root, read once by
`policy_platform.infrastructure.settings`. No component reads `os.environ`
directly. Copy the template to start:

```powershell
Copy-Item .env.example .env
```

`.env` is git-ignored. Never commit real credentials.

| Variable | Default in `.env.example` | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | Reported by `GET /health`. |
| `LOG_LEVEL` | `INFO` | Standard Python logging level. |
| `POSTGRES_HOST` / `_PORT` / `_DB` / `_USER` / `_PASSWORD` | `localhost` / `5433` / `policy_platform` / `policy_admin` / `policy_admin_pw` | Match `infra/local/docker-compose.yml`. |
| `DATABASE_URL` | asyncpg URL | Used by the application (async). **Required.** |
| `ALEMBIC_DATABASE_URL` | psycopg URL | Used by migrations (sync). **Required.** |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8010` | Port 8000 was already taken locally, hence 8010. |
| `DEV_AUTH_ENABLED` | `true` | Local development flag; there is no real auth. |
| `WEB_DEV_SERVER_PORT` | `5174` | Included in the API's CORS allow-list along with 5173–5179. |
| `VITE_API_BASE_URL` | `http://localhost:8010` | Read by the frontend at build/dev time. |
| `AZURE_OPENAI_ENDPOINT` / `_API_KEY` / `_API_VERSION` | blank / blank / `2024-12-01-preview` | **Required for the product.** Blank leaves the platform in degraded mode (AI routes `503`). |
| `AZURE_OPENAI_DEPLOYMENT` | blank | **Required.** Reasoning deployment: extraction, quality, correlation, rewrite, compare. |
| `AZURE_OPENAI_FAST_DEPLOYMENT` | blank | Low-latency deployment for Ask AI chat. Not part of the `ai_enabled` gate, but Ask AI targets it. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` / `_MODEL` / `_DIMENSIONS` | blank / blank / `3072` | **Required.** Embeddings for clause indexing and query vectors. `_DEPLOYMENT` is part of the `ai_enabled` gate. |
| `AZURE_SEARCH_ENDPOINT` / `_API_KEY` / `_API_VERSION` | blank / blank / `2025-09-01` | **Required grounding layer.** Blank disables clause indexing and all retrieval-backed grounding. |
| `AZURE_SEARCH_AUTHORING_INDEX` / `_EVIDENCE_INDEX` | `policy-authoring` / `policy-evidence` | Index names. Runtime reads/writes the authoring index; the Azure deployment bootstrap initializes both schemas, while the runtime client never alters schema. |

**AI and search are product requirements, not options.** Azure OpenAI drives
every AI capability, and a grounding/search layer — today Azure AI Search — is
what makes grounded answers and grounded test proposals possible. See
[AI assistance](ai-assistance.md) and
[How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

`ai_enabled` is true only when the OpenAI endpoint, key, chat deployment *and*
embedding deployment are all set. `search_enabled` is gated separately on its own
endpoint and key. Check the effective state at `GET /api/ai/status`, or via the
AI pill in the app header.

> **Degraded mode.** The current code contains **no fail-fast startup check**:
> the API boots with everything blank. In that state AI endpoints return `503`,
> the "AI disabled" pill shows, clause indexing returns `0`, and Ask AI cannot
> retrieve — while deterministic import, evaluation, policy tests, export, the
> decision log and the audit trail keep working. Treat this as a diagnostic
> mode for developing the deterministic core, not as a supported deployment of
> the product. The absence of a fail-fast check is recorded in
> [Known limitations](known-limitations.md).

Per-project extraction configuration (`trusted_config`) is stored on the policy
set, not in `.env`. Key it on the source term exactly as it appears in the policy
text, with the target fact path nested inside — keying by the fact path instead
fails silently because the extractor resolves mappings by source terminology.

## Setup, run, test

Prerequisites: Docker Desktop, Python 3.11+, Node.js 18+.

```powershell
# Database
docker compose -f infra/local/docker-compose.yml up -d

# Backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head

# Frontend
cd apps\web; npm install; cd ..\..
```

```powershell
# Run the API (no --reload: the watcher fights long extraction runs)
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010 --app-dir src

# Run the web app
cd apps\web; npm run dev
```

```powershell
# Backend tests
.\.venv\Scripts\python.exe -m pytest tests/unit -q     # active Python unit-test process

# Frontend type-check + build, and lint (not a test suite)
cd apps\web; npm run build
cd apps\web; npm run lint
```

The [testing guide](testing.md) describes the active pytest process by
capability, its invocation commands, expected behavior, isolation and coverage
gaps. Maintenance scripts are explicitly outside testing.

Useful database access:

```powershell
docker exec policy-postgres psql -U policy_admin -d policy_platform -c "\dt"
```

## Deployment status

| Deployment | Status | Runtime |
|---|---|---|
| **Local deployment** | **Available** | PostgreSQL uses `infra/local/docker-compose.yml`; API and Vite run locally and may call configured Azure OpenAI/Search endpoints. |
| **Azure deployment** | **Pending** | The azd/Bicep/container kit is prepared, but no Azure-hosted environment has been provisioned from this repository. |

The repository also contains a deployment-ready Azure kit: root `azure.yaml`
and Dockerfiles plus Bicep, parameter profiles, prerequisite hooks, Search
schemas and fresh-environment bootstrap under `infra/`. The recommended target
is Azure Container Apps with private PostgreSQL, Azure Files, Key Vault, Azure
OpenAI and Azure AI Search connectivity. See
[Azure deployment](azure-deployment.md) and
[Azure prerequisites](azure-prerequisites.md).

This is interactive deployment automation through `azd`; it is not a CI/CD
pipeline. There is still no `.github/workflows/` or other automated build,
test, scan or release pipeline.

## Security status

Read this before exposing the platform anywhere beyond a developer machine.

| Aspect | Status |
|---|---|
| Authentication | The application has no login/token validation. The pending Azure deployment adds Microsoft Entra authentication at public web ingress; it does not make application actor roles authoritative. |
| Identity | The "acting as" switcher (`ActorContext.tsx`) is a name and role held in browser `localStorage`. It is not an identity claim. |
| Authorization | A lightweight local-trust check only: `request-changes`, `override` and attestation-campaign creation require `actor_role: "policy_manager"` in the request body and return `403` otherwise. It is trivially spoofable and is not a security boundary. |
| Multi-tenancy | Not modelled. Single-tenant local assumption. |
| Transport | Local deployment uses HTTP. The pending Azure deployment enforces HTTPS ingress and TLS/private connectivity to data and AI services. |
| CORS | Restricted to the configured local Vite ports. |
| Secrets | Local keys use ignored `.env`. The pending Azure deployment stores database, Entra, OpenAI and Search secrets in private Key Vault and injects Key Vault references. |
| Uploaded files | Local files use `data/documents`; the pending Azure deployment mounts a private Azure Files share. Malware/content scanning is not implemented. |
| Threat model | No security review has been performed. |

The client-supplied actor role **must** be replaced by trusted Entra claims and server-side authorization before untrusted or production use. The prepared ingress gate authenticates users but does not complete that application change.

## Observability

| Signal | Where |
|---|---|
| Liveness | `GET /health` returns status plus the environment name; the web app polls it and shows a connection pill. |
| AI availability | `GET /api/ai/status`; shown as a pill in the app header. |
| Logs | Standard Python logging at `LOG_LEVEL`. Local runs also produce `backend_stdout.log` / `backend_stderr.log` (git-ignored). |
| Extraction progress | In-memory, exposed via `GET /api/ai/documents/{id}/extraction-progress`, plus persisted run history at `.../extraction-runs`. Progress is telemetry, not a source of truth. |
| Decision log | `evaluations` — every runtime evaluation with its facts, result and hash, browsable via the API and the Decision Log tab. |
| Audit trail | `audit_events` — immutable records of approvals, publications and dispositions, readable at `GET /api/audit-events`. |
| Quality / correlation history | Persisted runs, so results can be compared over time. |
| Test results | `policy_test_runs`, append-only, recording the version each run targeted. |

No metrics endpoint, tracing, alerting or log aggregation is implemented.

### Operational notes

- On startup the API marks any `extraction_runs` row still `running`/`pending`
  as `failed`, because an in-process extraction cannot survive a restart. Rules
  already committed by that run are kept.
- Azure AI Search indexing is best-effort: failures are logged and swallowed so a
  document upload never fails because a downstream service is unavailable. The
  trade-off is that a document can be fully usable while missing from the index,
  and nothing reconciles that afterwards except the maintenance scripts in
  [`docs/testing.md`](testing.md#maintenance-scripts-are-outside-testing).
- Long AI operations (candidate quality over hundreds of rules) run as a single
  request without incremental progress reporting.

## Extension points

Places designed to be extended, with the seam already in place:

| Point | How |
|---|---|
| **Prompts** | `src/policy_platform/infrastructure/prompts/*.md` are loaded from disk. Editing one is a reviewable file change. Note prompts are cached per process — restart the API to pick up an edit. |
| **Models** | Deployments are configuration, not code. Point `AZURE_OPENAI_DEPLOYMENT` / `_FAST_DEPLOYMENT` at different models. |
| **Condition operators** | Add to the allowlisted enum in `contracts/conditions.py` and implement it in `evaluator/conditions.py`. The allowlist is deliberate. |
| **Deterministic quality checks** | Add a `_*_findings()` function in `infrastructure/ai_quality.py` and include it in the deterministic pass. |
| **Export formats** | `infrastructure/export.py` is format-dispatched (`json`, `jsonl`, `csv`). |
| **Document formats** | `infrastructure/document_ingestion.py` produces a canonical representation; `document_extraction.py` adapts it to the persistence shape. |
| **Storage** | Document storage is a local path in the documents router; swapping in blob storage means replacing that write/read pair. |
| **Eventing** | `outbox_messages` exists and is modelled, but no publisher consumes it. |
| **Orchestration** | `src/policy_platform/worker/` is an empty reserved package. |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| API starts, all requests fail on the database | PostgreSQL container not running, or `DATABASE_URL` port is not 5433. |
| AI endpoints return `503` | Azure OpenAI not fully configured — check `GET /api/ai/status`. Azure OpenAI is required for the product; a `503` means the platform is in degraded mode. |
| Ask AI answers with no source chips | `AZURE_SEARCH_*` not configured, the document was never indexed (indexing is best-effort), or retrieval failed and was caught. Check `search_enabled` at `GET /api/ai/status`. |
| Frontend cannot reach the API | Vite chose a port outside the CORS allow-list, or `VITE_API_BASE_URL` does not match the API port. |
| Extraction restarts mid-run | The API was started with `--reload`. |
| A prompt edit has no effect | Prompt loading is cached per process; restart the API. |
| An extraction run shows `failed` after a restart | Expected: interrupted runs are reconciled at startup. |
