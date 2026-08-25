# Configuration and operations

This page is for developers and operators setting up a local or future Azure environment. It covers environment variables, how to run and test, and the operational posture. For what each framework does and where it is initialised, see [Frameworks and technologies](frameworks.md).

## Environment

All configuration lives in a `.env` file at the repository root, read once by `policy_platform.infrastructure.settings`. No component reads `os.environ` directly. Copy the template to start:

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
| `WEB_DEV_SERVER_PORT` | `5490` | Included in the API's CORS allow-list along with 5173–5180. |
| `VITE_API_BASE_URL` | `http://localhost:8010` | Read by the frontend at build/dev time. |
| `AZURE_OPENAI_ENDPOINT` / `_API_KEY` / `_API_VERSION` | blank / blank / `2024-12-01-preview` | Optional for a first local run. Blank leaves AI features disabled (routes return `503`), but the app boots and all deterministic features work. |
| `AZURE_OPENAI_DEPLOYMENT` | blank | Reasoning deployment: extraction, quality, correlation, rewrite, compare. Required for AI features, not for booting the app. |
| `AZURE_OPENAI_FAST_DEPLOYMENT` | blank | Low-latency deployment for Ask AI chat. Not part of the `ai_enabled` gate, but Ask AI targets it. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` / `_MODEL` / `_DIMENSIONS` | blank / blank / `3072` | Embeddings for clause indexing and query vectors. `_DEPLOYMENT` is part of the `ai_enabled` gate. Required for AI features. |
| `AZURE_SEARCH_ENDPOINT` / `_API_KEY` / `_API_VERSION` | blank / blank / `2025-09-01` | Blank disables clause indexing and all retrieval-backed grounding. Required for grounding features. |
| `AZURE_SEARCH_AUTHORING_INDEX` / `_EVIDENCE_INDEX` | `policy-authoring` / `policy-evidence` | Index names. Runtime reads/writes the authoring index; the Azure deployment bootstrap initializes both schemas, while the runtime client never alters schema. |

**Azure OpenAI and Azure AI Search are optional for getting started.** The app boots and all deterministic features work with these blank — document upload, rule editing, evaluation, policy tests, the decision log, and the audit trail all function. AI-powered features (extraction, quality checks, Ask AI, grounded answers) require Azure OpenAI and, for retrieval grounding, Azure AI Search. See [AI assistance](ai-assistance.md) and [How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

`ai_enabled` is true only when the OpenAI endpoint, key, chat deployment *and* embedding deployment are all set. `search_enabled` is gated separately on its own endpoint and key. Check the effective state at `GET /api/ai/status`, or via the AI pill in the app header.

> **Degraded mode.** The current code contains **no fail-fast startup check**: the API boots with everything blank. In that state AI endpoints return `503`, the "AI disabled" pill shows, upload reports `clauses_search_indexed: 0`, and Ask AI cannot retrieve — while deterministic import, evaluation, policy tests, export, the decision log and the audit trail keep working. Treat this as a diagnostic mode for developing the deterministic core, not as a supported deployment of the product. The absence of a fail-fast check is recorded in [Known limitations](known-limitations.md).

Per-project extraction configuration (`trusted_config`) is stored on the policy set, not in `.env`. Key it on the source term exactly as it appears in the policy text, with the target fact path nested inside — keying by the fact path instead fails silently because the extractor resolves mappings by source terminology.

### Pointing a migration at a database other than the default

`ALEMBIC_DATABASE_URL` is the *default* target, not the only one. Anything a caller names explicitly wins over it, and the resolved target — with the password removed — is logged at the start of every run, so an operator can see where a `downgrade` is about to land before it lands.

```powershell
# One invocation, from the command line.
.\.venv\Scripts\python.exe -m alembic -x db_url=postgresql+psycopg://user:pw@localhost:5433/scratch upgrade head
```

```python
# One invocation, programmatically. This is the documented, obvious route and
# it is honoured.
config = Config("alembic.ini")
config.set_main_option("sqlalchemy.url", scratch_url)
command.upgrade(config, "head")
```

Setting `ALEMBIC_DATABASE_URL` in a child process's environment also works and always did, but it is no longer the *only* route. It used to be: `alembic/env.py` overwrote `sqlalchemy.url` unconditionally, so a caller who set it programmatically was silently pointed at the ambient default instead — which in a developer's shell is production. The resolution now lives in `infrastructure/persistence/migration_target.py`, which explains the failure in full; `tests/unit/test_migration_target_resolution.py` fails if the override is ever made unconditional again.

## Running locally — step by step

This section takes a reader from a clean machine to a running stack. The local topology is: **one Docker container** (PostgreSQL only) plus **two host processes** (API and web dev server). The API and web app are not containerized for local development.

### Prerequisites

| Tool | Minimum version | Verify with |
|---|---|---|
| Docker Desktop | Any current release | `docker version` |
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Git | Any | `git --version` |

### 1. Clone and configure

```powershell
git clone <repository-url>
cd <repository-root>
Copy-Item .env.example .env
```

The `.env.example` template has working defaults for every local setting. The two **required** variables (`DATABASE_URL` and `ALEMBIC_DATABASE_URL`) are pre-filled with the correct connection strings for the local PostgreSQL container. You do not need to edit `.env` to get started — all Azure OpenAI and Azure AI Search variables can remain blank for a first run.

### 2. Start PostgreSQL

The project provides a single-service Docker Compose file at `infra/local/docker-compose.yml`. It runs PostgreSQL 16 on host port **5433** (not the default 5432, to avoid collisions with a system install).

```powershell
docker compose -f infra/local/docker-compose.yml up -d
```

This starts a **new, empty database**. That is the intended starting point: the guide sets up a clean instance with no projects, documents or policies in it, exactly as a new deployment would begin. If you have run this before and want to start over from nothing, remove the volume as well — see [Useful database commands](#useful-database-commands).

Confirm it is healthy:

```powershell
docker ps --filter name=policy-postgres --format "table {{.Names}}\t{{.Status}}"
```

You should see `policy-postgres` with status `Up ... (healthy)`. If the health check has not passed yet, wait a few seconds and retry — the container runs `pg_isready` every 10 seconds.

You can also test connectivity directly:

```powershell
docker exec policy-postgres psql -U policy_admin -d policy_platform -c "SELECT 1"
```

### 3. Create the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

This installs the `policy-platform` package in editable mode with development dependencies. The `[dev]` extra is sufficient for running the API and all unit tests that do not involve Docling document conversion.

### 4. Create the database schema

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

This builds the empty schema — the tables, columns, indexes and constraints the application needs before it can store anything. It creates **no data**. The database you started in step 2 is brand new and stays empty: after this step there are no projects, no documents, no rules and no policies, and the application opens on empty screens until you upload your first document.

The tool is Alembic, and the scripts under `alembic/versions/` are called *migrations* by convention, which is misleading here — the word suggests moving or populating data, and these do not. Each script describes one schema change, and the set of them is replayed in order to build the structure from nothing. A handful also contain `UPDATE` statements that fill in a newly added column for rows that already exist; on the fresh database in this guide there are no such rows, so those statements match nothing and change nothing. There is not a single `INSERT` in any of them.

Confirm:

```powershell
docker exec policy-postgres psql -U policy_admin -d policy_platform -c "\dt"
```

You should see tables including `policy_sets`, `clauses`, `rules`, `evaluations`, `audit_events`, and others — all of them empty. If you see `Did not find any relations`, the schema was not created: check that PostgreSQL is running and that `ALEMBIC_DATABASE_URL` in `.env` points to `localhost:5433`.

### 5. Start the API

Use the provided launch script rather than invoking uvicorn directly:

```powershell
.\scripts\run_api.ps1
```

The script reads `API_PORT` from `.env` (default `8010`), sets `PYTHONPATH=src`, clears ambient `AZURE_OPENAI_*` environment variables (which otherwise outrank `.env` and can cause silent `401` errors by pairing one resource's endpoint with another's key), and binds to `0.0.0.0` (binding to `127.0.0.1` fails when the browser resolves `localhost` to `::1`).

Confirm the API is running:

```powershell
curl http://localhost:8010/health
```

You should see a JSON response with `"status": "ok"` and `"environment": "development"`. If AI variables are blank, `GET /api/ai/status` will report AI and search as disabled — this is expected and the app is fully functional for deterministic features.

### 6. Start the web app

In a **separate terminal**:

```powershell
cd apps\web
npm install
npm run dev
```

Vite binds to the port in `WEB_DEV_SERVER_PORT` (default `5490` from `.env`). It uses `strictPort: true`, so it will fail rather than silently increment if the port is taken. The dev server reads `VITE_API_BASE_URL` from the root `.env` (default `http://localhost:8010`) and proxies API calls there.

Confirm: open `http://localhost:5490` in a browser. You should see the PolicyVerbAItim interface. The connection pill in the header should be green. If AI is not configured, the "AI disabled" pill is expected.

### 7. Uploaded documents

Uploaded documents are written to the relative path `data/documents` under the repository root. This directory is created automatically on first upload. It is local filesystem state — back it up if the data matters, and note that the Azure deployment mounts this path as an Azure Files share instead.

### Running tests

```powershell
# Backend unit tests (no database or network required)
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest tests/unit -q

# Frontend type-check and production build
cd apps\web
npm run build

# Frontend lint
cd apps\web
npm run lint
```

The full test suite (`tests/`) needs the `[dev,graph]` extra because 13 modules import Docling directly — see the [Docling integration](docling.md) guide. The `tests/unit` subset runs with `.[dev]` alone.

The [testing guide](testing.md) describes the active pytest process by capability, its invocation commands, expected behavior, isolation and coverage gaps. Maintenance scripts are explicitly outside testing.

### Useful database commands

```powershell
# List tables
docker exec policy-postgres psql -U policy_admin -d policy_platform -c "\dt"

# Interactive psql session
docker exec -it policy-postgres psql -U policy_admin -d policy_platform

# Stop and remove the container (data persists in the pgdata volume)
docker compose -f infra/local/docker-compose.yml down

# Stop and destroy the data as well — this is how you start over from an
# empty database, which is the supported starting point for a new setup
docker compose -f infra/local/docker-compose.yml down -v
```

## Deployment status

| Deployment | Status | Runtime |
|---|---|---|
| **Local deployment** | **Available** | PostgreSQL uses `infra/local/docker-compose.yml`; API and Vite run locally and may call configured Azure OpenAI/Search endpoints. |
| **Azure deployment** | **Pending** | The azd/Bicep/container kit is prepared, but no Azure-hosted environment has been provisioned from this repository. |

The repository also contains a deployment-ready Azure kit: root `azure.yaml` and Dockerfiles plus Bicep, parameter profiles, prerequisite hooks, Search schemas and fresh-environment bootstrap under `infra/`. The recommended target is Azure Container Apps with private PostgreSQL, Azure Files, Key Vault, Azure OpenAI and Azure AI Search connectivity. See [Azure deployment](azure-deployment.md) and [Azure prerequisites](azure-prerequisites.md).

This is interactive deployment automation through `azd`; it is not a CI/CD pipeline. There is still no `.github/workflows/` or other automated build, test, scan or release pipeline.

## Security status

Read this before exposing the platform anywhere beyond a developer machine.

| Aspect | Status |
|---|---|
| Authentication | The application validates a bearer token when an OIDC issuer is configured (`ENTRA_ISSUER`, `ENTRA_AUDIENCE`, `ENTRA_JWKS_URL`) — signature, expiry, issuer and audience are all checked. With those unset the token path is not offered at all, rather than half-checked, and callers resolve to the least privilege. The Azure deployment additionally authenticates at web ingress. |
| Identity | Comes from validated token claims where a token is presented. The role is no longer chosen in the browser: the "acting as" switcher has been removed, because a user who can pick their own role does not have one. A display name is still held locally for attribution. |
| Authorization | A capability layer covering **all 96 API operations**. Each is classified into a band — read, use, author, administer — and one dependency enforces the registry, rather than checks scattered through routers. A guard test fails when any route is unclassified, and an unclassified route is denied at runtime too. **Disabled by default** (`RBAC_ENABLED=false`) so existing deployments are unchanged; see the note below before enabling it. |
| Multi-tenancy | Not modelled. Single-tenant local assumption. |
| Transport | Local deployment uses HTTP. The pending Azure deployment enforces HTTPS ingress and TLS/private connectivity to data and AI services. |
| CORS | Restricted to the configured local Vite ports. |
| Secrets | Local keys use ignored `.env`. The pending Azure deployment stores database, Entra, OpenAI and Search secrets in private Key Vault and injects Key Vault references. |
| Uploaded files | Local files use `data/documents`; the pending Azure deployment mounts a private Azure Files share. Malware/content scanning is not implemented. |
| Threat model | No security review has been performed. |

### Signing in

There are two ways to establish who is calling. Both produce a validated bearer token, and both are checked by the same code — signature, expiry, issuer, audience, with the algorithm pinned. That is deliberate: when you move from one to the other, the only thing that changes is who issued the token, so what you tested is what runs.

**Local accounts, for development.** Set `LOCAL_ACCOUNTS_ENABLED=true` and put accounts in `.local-accounts.txt`, one per line as `username:password:role`, with `#` for comments. Sign in through the web app, or directly:

```powershell
curl -X POST http://localhost:8010/api/auth/login -H "Content-Type: application/json" -d '{"username":"viewer","password":"..."}'
```

The response carries `access_token`; send it as `Authorization: Bearer <token>` on subsequent calls. `GET /api/auth/me` reports the resolved principal, which is the quickest way to confirm a token is doing what you expect.

The file holds plain-text passwords, because you need to read them to sign in. It is gitignored by shape — a copy named `local-accounts.backup.txt` is the same secret with a different name — and the API **refuses to start** with local accounts enabled while `ENVIRONMENT` is production. A plain-text credential file that can be switched on in production is worse than no authentication, because it looks like authentication.

Tokens are signed with a key held in `.local-signing-key.pem`, also gitignored. Anyone holding that key can mint a token this API accepts, which is a more complete compromise than the passwords themselves.

**Microsoft Entra, for a real deployment.** Set `ENTRA_ISSUER`, `ENTRA_AUDIENCE` and `ENTRA_JWKS_URL`. Roles come from the token's `roles` (or `groups`) claim by exact name — `viewer`, `policy_author`, `admin` — so they are configured once in the directory rather than translated here. A caller holding several gets the highest. Roles that belong to other applications are ignored rather than refused, because a directory carries plenty of them.

### Before enabling `RBAC_ENABLED`

Enforcement is only as good as the identity it reads, so configure sign-in first. With neither local accounts nor an issuer configured, no token can be validated and every caller falls to the least privilege — which is safe, and also unusable.

**Do not enable `TRUST_PLATFORM_AUTH_HEADER` without checking your ingress.** Azure Container Apps injects `X-MS-CLIENT-PRINCIPAL` after authenticating someone, and reading it is tempting. In this topology the browser reaches an nginx container that proxies to the API, and a proxy forwards headers it was not told to drop — so a caller who sets that header themselves has it delivered alongside the genuine one. `apps/web/nginx.conf.template` now clears the platform identity headers before proxying, which is what makes trusting them defensible behind *that* ingress. A different ingress is a different question, and the setting stays off until it is answered.

**`DEV_AUTH_ENABLED` must be false in production.** It enables an `X-Dev-Role` header that sets the caller's role directly. The application refuses to start if it is true while `ENVIRONMENT` is production — a bypass that can be switched on where it matters is worse than no layer at all. It is also worth turning off locally once local accounts work, so that what you exercise is the real path rather than the shortcut.

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

- On startup the API marks an `extraction_runs` row it owns (`owner_kind == OWNER_API`) still `running`/`pending` as `failed`, because an in-process extraction does not survive a restart. Runs owned by another process are left untouched, and rules already committed by that run are kept.
- Azure AI Search indexing is best-effort: failures are logged and swallowed so a document upload never fails because a downstream service is unavailable. The trade-off is that a document can be fully usable while missing from the index, and nothing reconciles that afterwards except the maintenance scripts in [`docs/testing.md`](testing.md#maintenance-scripts-are-outside-testing).
- Long AI operations (candidate quality over hundreds of rules) run as a single request without incremental progress reporting.

## Extension points

Places designed to be extended, with the seam already in place:

| Point | How |
|---|---|
| **Prompts** | `src/policy_platform/infrastructure/prompts/*.md` are loaded from disk. Editing one is a reviewable file change. Note prompts are cached per process — restart the API to pick up an edit. |
| **Models** | Deployments are configuration, not code. Point `AZURE_OPENAI_DEPLOYMENT` / `_FAST_DEPLOYMENT` at different models. |
| **Condition operators** | Add to the allowlisted enum in `contracts/conditions.py` and implement it in `evaluator/conditions.py`. The allowlist is deliberate. |
| **Deterministic quality checks** | Add a `_*_findings()` function in `infrastructure/quality/ai_quality.py` and include it in the deterministic pass. |
| **Export formats** | `infrastructure/projection/export.py` is format-dispatched (`json`, `jsonl`, `csv`). |
| **Document formats** | `infrastructure/ingestion/document_ingestion.py` produces a canonical representation; `document_extraction.py` adapts it to the persistence shape. |
| **Storage** | Document storage is a local path in the documents router; swapping in blob storage means replacing that write/read pair. |
| **Eventing** | `outbox_messages` exists and is modelled, but no publisher consumes it. |
| **Orchestration** | Extraction runs inside the API request that starts it. |

## Troubleshooting

| Symptom | Likely cause | Diagnostic |
|---|---|---|
| API starts, all requests fail on the database | PostgreSQL container not running, or `DATABASE_URL` port is not 5433. | Run `docker ps --filter name=policy-postgres` — if it is not listed, run `docker compose -f infra/local/docker-compose.yml up -d`. If it is listed but unhealthy, check `docker logs policy-postgres`. |
| `alembic upgrade head` fails with connection refused | PostgreSQL is not running or `.env` has the wrong port. | Verify `ALEMBIC_DATABASE_URL` in `.env` uses port `5433` and driver `postgresql+psycopg`. Run `docker exec policy-postgres psql -U policy_admin -d policy_platform -c "SELECT 1"` to confirm connectivity. |
| API returns `401` from Azure OpenAI | Ambient `AZURE_OPENAI_*` environment variables outrank `.env`, pairing one resource's endpoint with another's key. | Use `scripts/run_api.ps1` which clears these variables before starting. Alternatively, close and reopen the terminal. |
| AI endpoints return `503` | Azure OpenAI not fully configured — check `GET /api/ai/status`. This is expected if you left AI variables blank. Azure OpenAI is required for AI features; a `503` means the platform is in degraded mode but deterministic features work. | Verify all four variables: `AZURE_OPENAI_ENDPOINT`, `_API_KEY`, `_DEPLOYMENT`, and `_EMBEDDING_DEPLOYMENT`. |
| Ask AI answers with no source chips | `AZURE_SEARCH_*` not configured, the document was never indexed (indexing is best-effort), or retrieval failed and was caught. | Check `search_enabled` at `GET /api/ai/status`. |
| Frontend cannot reach the API | Vite chose a port outside the CORS allow-list, or `VITE_API_BASE_URL` does not match the API port. | Confirm `WEB_DEV_SERVER_PORT` in `.env` is `5490` (within the CORS allow-list). Confirm `VITE_API_BASE_URL` matches the port the API is actually running on. Check the browser console for CORS errors. |
| Vite exits with "port already in use" | Port `5490` is taken. The dev server uses `strictPort: true` and refuses to silently increment. | Free the port or change `WEB_DEV_SERVER_PORT` in `.env`. |
| Browser shows blank page but API works via curl | The API is bound to `127.0.0.1` but the browser resolves `localhost` to `::1` (IPv6). | Use `scripts/run_api.ps1` which binds to `0.0.0.0`. |
| Extraction restarts mid-run | The API was started with `--reload`. | Use `scripts/run_api.ps1` which does not pass `--reload`. |
| A prompt edit has no effect | Prompt loading is cached per process; restart the API. | Stop and restart via `scripts/run_api.ps1`. |
| An extraction run shows `failed` after a restart | Expected: interrupted runs are reconciled at startup. | Not a bug — the API marks in-process runs as `failed` on boot because they cannot resume. Rules already committed by that run are kept. |
| `npm run dev` fails with module not found | `npm install` was not run in `apps/web`. | Run `cd apps\web; npm install`. |
| Tests fail at collection with Docling import errors | The `[dev]` extra does not include Docling. | Install with `.[dev,graph]` in a separate venv (`.venv-graph`) — see the [Docling integration](docling.md) guide. |
