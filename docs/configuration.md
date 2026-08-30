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
| `POLICY_SUBSCRIPTION_KEY` | blank | One pre-shared key for a non-interactive caller, sent in `X-Policy-Subscription-Key`. **Blank disables the mechanism** — the header is not read at all. See [calling the decision API](#calling-the-decision-api-from-another-system). |
| `POLICY_SUBSCRIPTION_KEY_IDENTITY` | `external-api-client` | The identity every receipt that key produces is attributed to. |
| `POLICY_SUBSCRIPTION_KEY_ROLE` | `viewer` | `viewer`, `policy_author` or `admin`. An unrecognised value refuses the key rather than granting an unusable role. |
| `WEB_DEV_SERVER_PORT` | `5490` | Included in the API's CORS allow-list along with 5173–5180. |
| `CORS_ALLOWED_ORIGINS` | blank | Comma-separated browser origins allowed to call the API. **Blank derives them**; an explicit list **replaces** the derived set rather than adding to it. See [browser origins](#browser-origins-and-cors) below. |
| `CORS_DEV_PORT_RANGE` | `5173-5180` | The ports probed on both `localhost` and `127.0.0.1` when `CORS_ALLOWED_ORIGINS` is blank. |
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

## Reaching the API from outside

Locally the API is its own process on `http://localhost:8010` and an external client calls it directly.

In the Azure topology it is not directly addressable. The public FQDN belongs to the **web** container app, whose nginx reverse-proxies `/api` through to the API container app; the API container stays internal to the Container Apps environment. So the base URL you hand to an integrator is the web application's address — `https://<web-fqdn>` — and every path documented in the [API guide](api.md) sits unchanged beneath it. That is also why a decision receipt's `receipt_url` is a relative path: an absolute URL built inside the API would name a host the caller never used.

There is no separate public ingress for the API, and none is needed. If you add one, it is a new trust boundary and the CORS list, the token audience and the platform-header decision below all have to be revisited for it.

### Browser origins and CORS

The API's allow-list comes from `settings.allowed_cors_origins`:

- **`CORS_ALLOWED_ORIGINS` blank (the default)** — the configured `WEB_DEV_SERVER_PORT` plus the `CORS_DEV_PORT_RANGE` (`5173-5180`) are allowed on both `localhost` and `127.0.0.1`. Both hostnames are listed because a browser treats them as different origins and which one a developer types is not predictable. A browser client on any port in that range works locally with no configuration change — which is why the external playground under `apps/consume-demo` fixes its dev port at **5179** with `strictPort`, rather than letting Vite move to the next free port and present a CORS block as a broken backend.
- **`CORS_ALLOWED_ORIGINS` set** — the named origins are the whole list. It **replaces** the derived set; it is not unioned with it. An operator who names origins means those and no others, and quietly adding a development range would widen production beyond what was asked for. So a production origin must appear in that variable explicitly, and once you set it the local development ports stop being allowed unless you list them too.

A missing origin fails as a silent CORS block in the browser rather than a server-side error anyone will see in a log, so check the browser console first when a client cannot reach the API.

Server-to-server callers — a service, a workflow step, an agent runtime — are not browsers and are unaffected by any of this.

### Calling the decision API from another system

The two audited decision operations require a proved identity and refuse an unauthenticated caller with `401`, **independently of `RBAC_ENABLED`**. That is the only place the global flag is bypassed, and it only ever narrows access: a receipt has to name the principal that asked for it, and `rbac-disabled` is not a principal. Capability remains the global guard's decision.

There are two ways to be that caller.

**A bearer token**, from the same issuer the API validates. Everything under [Signing in](#signing-in) applies unchanged. This is the option to reach for when the caller is a person, or when you need per-caller attribution, expiry, or revocation without a restart.

**A subscription key**, for a non-interactive caller that has no user and no issuer — an agent, a workflow, a scheduled job.

| Setting | Meaning |
|---|---|
| `POLICY_SUBSCRIPTION_KEY` | The key itself. **Blank by default, and blank means the mechanism does not exist**: the header is not read at all, so a deployment that never enabled it cannot be probed through it. Generate something long and random; no strength requirement is enforced, and a guessable key is a public API. |
| `POLICY_SUBSCRIPTION_KEY_IDENTITY` | The identity recorded on every receipt the key produces. Defaults to `external-api-client`. Name the system, not a person. |
| `POLICY_SUBSCRIPTION_KEY_ROLE` | `viewer` (default), `policy_author` or `admin`. Validated against the role vocabulary: an unrecognised value refuses the key rather than producing a principal no capability band understands. |

The caller sends it in `X-Policy-Subscription-Key`, not in `Authorization`:

```bash
export POLICY_SUBSCRIPTION_KEY="<the key your operator issued>"
curl -sS -X POST "http://localhost:8010/api/policy-decisions/<project-key>/case" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -d '{"scenario": "Describe the situation you want decided."}'
```

What it is, precisely:

- **One key, in this increment.** Every caller presenting it resolves to the same configured identity, so it groups callers rather than distinguishing them. Two systems sharing one key are indistinguishable in every receipt they produce.
- **Rotation is: change the value, restart the API.** There is no overlap window, no second key, no revocation list and no expiry. Plan a short window in which in-flight callers get `401`, or use an issuer.
- **It is compared in constant time** and a wrong key is refused with `401 subscription_key_rejected` rather than falling through to an anonymous request — the same rule the bearer path has always had. Presenting a bad credential must not be indistinguishable from presenting none.
- **A valid bearer token wins.** If a caller sends both, the token decides: it names an individual, expires, and can be revoked at its issuer, and the key does none of those. A token that is presented and *rejected* still ends the request; a subscription key cannot rescue a bad token.
- **It works through the normal guard too.** With `RBAC_ENABLED=true` the same key authenticates ordinary routes at its configured role, so one credential can resolve a project's identity and its active version as well as put a case and read the receipt back.
- **It is not an Azure or APIM subscription key.** Nothing here integrates with API Management, Azure subscriptions, or any gateway product; it is a pre-shared value this application compares against its own configuration.

Practical posture for an integrating system, whichever credential it holds:

- Keep it in the calling system's own secret store. Documentation, snippets and the in-product **Call from your app** panel all read it from `POLICY_SUBSCRIPTION_KEY` and never contain a literal credential; keep it that way in anything you copy out of them.
- **Never put a subscription key in a browser client.** The local playground at `apps/consume-demo` does exactly that, on purpose and for one purpose: it is a local demonstration against a key an operator generated for local use, so the value is shown in clear and appears in its Raw HTTP tab where it can be compared against a failing call. A shipped browser application must not — anything Vite inlines is served to every visitor, and a shared credential in a page is a shared credential in everyone's hands. Put a server between the browser and this API.
- The caller-supplied `calling_system_identity` on a decision request is an **unverified label** for grouping and reporting. It is recorded beside the authenticated principal, never instead of it, and it grants nothing.
- Receipts are readable by the caller who made the decision and by policy authors and administrators. A service verifying its own receipts needs no extra role.
- Scenario text and caller guidance are stored in clear and are not pruned — see [Known limitations](known-limitations.md#before-relying-on-this-build) before exposing the endpoint to end users who type their own prose. **No retention setting exists**, and one is not listed here, because the backend implements none.

## Security status

Read this before exposing the platform anywhere beyond a developer machine.

| Aspect | Status |
|---|---|
| Authentication | The application validates a bearer token when an OIDC issuer is configured (`ENTRA_ISSUER`, `ENTRA_AUDIENCE`, `ENTRA_JWKS_URL`) — signature, expiry, issuer and audience are all checked. With those unset the token path is not offered at all, rather than half-checked, and callers resolve to the least privilege. A non-interactive caller may instead present a pre-shared key in `X-Policy-Subscription-Key`, which is off until `POLICY_SUBSCRIPTION_KEY` is set, compared in constant time, and outranked by any valid bearer token. The Azure deployment additionally authenticates at web ingress. |
| Identity | Comes from validated token claims where a token is presented. The role is no longer chosen in the browser: the "acting as" switcher has been removed, because a user who can pick their own role does not have one. A display name is still held locally for attribution. |
| Authorization | A capability layer covering **all 105 API operations**. Each is classified into a band — read, use, author, administer — and one dependency enforces the registry, rather than checks scattered through routers. A guard test fails when any route is unclassified, and an unclassified route is denied at runtime too. **Disabled by default** (`RBAC_ENABLED=false`) so existing deployments are unchanged; see the note below before enabling it. The two audited decision operations are the single exception: they additionally require a proved identity and answer `401` without one even when the flag is off. |
| Multi-tenancy | Not modelled. Single-tenant local assumption. |
| Transport | Local deployment uses HTTP. The pending Azure deployment enforces HTTPS ingress and TLS/private connectivity to data and AI services. |
| CORS | Derived from the configured local Vite ports when `CORS_ALLOWED_ORIGINS` is blank; an explicit list replaces that derived set entirely. See [browser origins and CORS](#browser-origins-and-cors). |
| Stored request text | An audited decision receipt stores the caller's scenario and caller guidance in clear, append-only, with no retention job. Retention and erasure are operator obligations — see [Known limitations](known-limitations.md#before-relying-on-this-build). |
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
| Case decision receipts | `policy_case_decisions` — one append-only row per audited external case decision, holding the request, the caller, the finalised envelope and its hash. Read back one at a time at `GET /api/policy-decisions/{decision_id}`; there is no list or search endpoint over them. |
| Audit trail | `audit_events` — immutable records of approvals, publications and dispositions, readable at `GET /api/audit-events`. |
| Quality / correlation history | Persisted runs, so results can be compared over time. |
| Test results | `policy_test_runs`, append-only, recording the version each run targeted. |

No metrics endpoint, tracing, alerting or log aggregation is implemented.

### Operational notes

- On startup the API marks an `extraction_runs` row it owns (`owner_kind == OWNER_API`) still `running`/`pending` as `failed`, because an in-process extraction does not survive a restart. Runs owned by another process are left untouched, and rules already committed by that run are kept.
- Azure AI Search indexing is best-effort: failures are logged and swallowed so a document upload never fails because a downstream service is unavailable. The trade-off is that a document can be fully usable while missing from the index, and nothing reconciles that afterwards except the maintenance scripts in [`docs/testing.md`](testing.md#maintenance-scripts-are-outside-testing).
- Long AI operations (candidate quality over hundreds of rules) run as a single request without incremental progress reporting.

### The policy index needs a model, and rebuilding it is not free

The project **policy index** — the one the audited decision endpoint retrieves from — is not a plain copy of the corpus. Every policy is rendered into English before it is indexed, so a question in any language can be scored against it, and both the index and the query are stamped with the contract that rendering was made under.

That makes the index build depend on Azure OpenAI, not only on Azure AI Search:

| Setting | Used for |
|---|---|
| `AZURE_OPENAI_FAST_DEPLOYMENT`, falling back to `AZURE_OPENAI_DEPLOYMENT` | Rendering each policy's retrieval text into English at build time. |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` / `_MODEL` / `_DIMENSIONS` | Embedding the rendered text. |
| `AZURE_SEARCH_*` | Holding the resulting documents. |

**Cost, stated plainly.** Rendering is batched — at most 6 items or 3,000 characters per call, with a fixed 4,096-token completion ceiling — and **a batch never crosses a policy boundary**, so the floor is *one model call per published policy*, plus one more for roughly every six rule texts of a policy large enough to get per-rule documents (over 15 rules). A 74-row schedule is therefore around a dozen calls on its own. Embeddings are additional. Calls are made sequentially, one policy after another.

**There is no cache.** Nothing memoises a rendering between builds, so every rebuild re-renders and re-embeds the entire active version from scratch, and pays the full cost again even if one policy changed. This is deliberate rather than pending: a cache keyed on anything less than the exact rendered contract would serve text from a superseded projection, which is the failure the profile stamp exists to make impossible.

The same build runs **inline on publish** (best-effort, after the publish transaction commits — a failure is recorded, not raised) and inline in the rebuild endpoint. Both paths hold their request open for the whole pass. Budget for that in client timeouts and in any reverse-proxy read timeout in front of the API.

**Rebuilding by hand:**

```bash
curl -X POST "$POLICY_API_BASE/api/policy-sets/$PROJECT_KEY/policy-index/rebuild"
```

It returns `state`, `document_count`, `policy_document_count`, `rule_document_count`, `projection_profile` and `manifest_state`. A successful build ends with `manifest_state: "ready"`; anything else means the project is still unmatchable and the decision endpoint will answer `503 index_projection_unavailable` for it. Re-running the command **is** the recovery — the build is a pure function of the database, so it produces the same document ids and overwrites in place. There is no automatic retry, and no rollback to perform: a failed build never removes the previous documents, it only leaves the manifest short of `ready`.

Check state without rebuilding with `GET /api/policy-sets/{key}/policy-index`.

**Content filtering.** If the deployment's content filter rejects a policy's text, the build fails with the filtered category surfaced in the error rather than being retried or skipped — one unrendered policy would mean a corpus that is English in part, which the profile must never claim.

**Quality assurance is partial today.** Each rendering is checked structurally as it is produced — rejected if it is empty, implausibly larger or smaller than its source, or if a number or identifier failed to survive it, with the whole batch rejected on any failure. The projection-quality gate that assesses whether a rendering is a faithful reading of the passage is still being implemented. Indexes already built under `policy-english-projection-v1` are live and serving retrieval; until the gate validates them, their retrieval quality is unvalidated rather than assured. A successful rebuild therefore means "indexed and structurally checked", not "quality-approved".

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
