# Frameworks and technologies

Every framework and library the platform actually depends on, what it is
responsible for here, where it is configured, and why it fits.

Verified against [`pyproject.toml`](../pyproject.toml),
[`apps/web/package.json`](../apps/web/package.json),
[`infra/local/docker-compose.yml`](../infra/local/docker-compose.yml),
[`alembic.ini`](../alembic.ini) and the imports in `src/`. Nothing is listed
here that the code does not use.

For Microsoft-specific guidance and first-party references, see
[Microsoft technologies and references](microsoft-technologies.md).

---

## Core runtime — backend

| Technology | Role here |
|---|---|
| **Python 3.11+** | The whole backend. `requires-python = ">=3.11"`; the code uses `match` statements and PEP 604 unions. |
| **FastAPI** (`>=0.115,<0.116`) | HTTP layer: routing, request validation, dependency injection, and automatic OpenAPI generation. |
| **Uvicorn** (`[standard]`) | ASGI server that runs the app. |
| **Pydantic v2** (`>=2.9,<3.0`) | The contract layer. Every canonical rule, condition node, evaluation request/response, policy test and correlation finding is a Pydantic model. |
| **pydantic-settings** | Typed configuration loaded once from `.env`. |
| **python-multipart** | Multipart parsing for document upload. |
| **httpx** (`>=0.27,<0.28`) | The only outbound HTTP client — used for Azure OpenAI and Azure AI Search, and by the test suite. |

**Where configured.**
[`api/app.py`](../src/policy_platform/api/app.py) is the app factory: it builds
the `FastAPI` instance, registers ten routers, configures CORS for the local Vite
ports, and installs a lifespan hook that reconciles interrupted extraction runs.
Settings live in
[`infrastructure/settings.py`](../src/policy_platform/infrastructure/settings.py)
— a single `BaseSettings` class with `env_file=".env"`, cached with
`@lru_cache`. No component reads `os.environ` directly.

**How invoked.**

```powershell
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010 --app-dir src
```

Routers obtain an `AsyncSession` through `Depends(get_session)` and call one
infrastructure service or repository.

**Why it fits.** FastAPI's request models *are* the Pydantic contracts, so
validation, the OpenAPI description and the interactive docs at `/docs` all come
from the same declarations that the evaluator consumes — there is no second
schema to drift. Pydantic v2 does the heavy lifting the platform depends on
most: a malformed rule payload is rejected at the boundary rather than
discovered at decision time, and the discriminated-union condition AST in
[`contracts/conditions.py`](../src/policy_platform/contracts/conditions.py) is
enforced by the type system rather than by hand-written checks.

---

## Persistence

| Technology | Role here |
|---|---|
| **PostgreSQL 16** | The system of record. Runs in Docker Compose on host port **5433**. |
| **SQLAlchemy 2.0** (async ORM) | Domain entities and all query construction. |
| **asyncpg** | Async driver used by the application. |
| **psycopg (binary)** | Sync driver used by Alembic migrations. |
| **Alembic** | Schema migrations — 24 revisions in [`alembic/versions/`](../alembic/versions). |

**Where configured.**
[`infrastructure/db.py`](../src/policy_platform/infrastructure/db.py) builds the
async engine and sessionmaker from `DATABASE_URL`. Entities are declared in
[`domain/models.py`](../src/policy_platform/domain/models.py) on the
`DeclarativeBase` in [`domain/base.py`](../src/policy_platform/domain/base.py),
with shared UUID-primary-key and timestamp mixins. Alembic is configured by
[`alembic.ini`](../alembic.ini) and reads `ALEMBIC_DATABASE_URL`.

**How invoked.**

```powershell
docker compose -f infra/local/docker-compose.yml up -d
.\.venv\Scripts\python.exe -m alembic upgrade head
```

**Why it fits.** Two URLs for one database is deliberate: the app needs async
I/O under a request-driven API, migrations do not and are simpler synchronous.
PostgreSQL's JSONB is what makes the "canonical payload is the source of truth"
model workable — a published rule is stored as its full canonical JSON *and* as
queryable columns, so an immutable snapshot never has to be reassembled from
normalised parts. SQLAlchemy 2.0's typed `Mapped[...]` declarations keep the ORM
entities readable next to the Pydantic contracts they mirror.

---

## Document processing

| Technology | Role here |
|---|---|
| **pdfplumber** (`>=0.11,<0.12`) | PDF parsing. Used through `page.extract_words()` — not `extract_text()` — so word geometry is available. |
| **python-docx** (`>=1.1,<2.0`) | DOCX parsing, including table structure. |

**Where configured / used.**
[`infrastructure/document_ingestion.py`](../src/policy_platform/infrastructure/document_ingestion.py)
is the only module that imports either. It reconstructs canonical page text from
word positions, stitches paragraphs across page breaks, detects headings by font
size relative to the modal body size, and reports an `IngestionDiagnostic` where
it cannot do better.
[`document_extraction.py`](../src/policy_platform/infrastructure/document_extraction.py)
adapts the canonical document to persistence shape.

**Why it fits.** Geometry is what makes offsets exact rather than recovered by
searching, and exact offsets are what make verbatim traceability possible later.
A text-only extractor would make chunk boundaries into policy boundaries — the
specific failure this module exists to prevent.

---

## Frontend

| Technology | Role here |
|---|---|
| **React 19** | The single-page app. Local component state only — no Redux, no router library. |
| **TypeScript ~6.0** | Types for the whole frontend, including a hand-maintained mirror of the backend contracts in `api.ts`. |
| **Vite 8** | Dev server and production build. |
| **@vitejs/plugin-react** | React fast refresh and JSX transform. |
| **Ant Design v6** + `@ant-design/icons` | The entire component vocabulary: layout, tables, drawers, forms, tags. |
| **@ant-design/v5-patch-for-react-19** | Compatibility shim for antd under React 19. |
| **oxlint** | Linting. |

**Where configured.** [`apps/web/package.json`](../apps/web/package.json) holds
the scripts; `App.tsx` is the shell (sidebar, health/AI pills, actor switcher,
Ask AI drawer); [`api.ts`](../apps/web/src/api.ts) is the single typed client and
reads `VITE_API_BASE_URL`; `ActorContext.tsx` holds the "acting as" identity in
`localStorage`.

**How invoked.**

```powershell
cd apps\web; npm run dev      # vite
cd apps\web; npm run build    # tsc -b && vite build
cd apps\web; npm run lint     # oxlint
```

**Why it fits.** The app is a pure client — it holds no policy logic, so it needs
state management for UI concerns only, which React's built-in state covers.

`npm run build` runs `tsc -b` first, so a type error in the API client is a build
failure: the TypeScript mirror of the backend contracts is the closest thing the
project has to an end-to-end schema check. Ant Design supplies the dense,
table-and-drawer-heavy vocabulary a review queue needs without a bespoke design
system.

---

## AI and integration — required

| Technology | Role here |
|---|---|
| **Azure OpenAI** | Two chat deployments — a reasoning deployment for extraction, quality, correlation, rewrite and compare; a fast deployment for Ask AI — plus an embedding deployment. Required: without it there are no AI capabilities at all. |
| **Azure AI Search** | The platform's grounding layer: clause-level hybrid keyword + vector retrieval over indexed clauses. Required for grounded answers and grounded test proposals. Directly integrated — there is no retrieval abstraction. |

**Where configured.** All `AZURE_*` variables in `.env`, surfaced through
`Settings`. `ai_enabled` requires endpoint, key, chat deployment *and* embedding
deployment; `search_enabled` is gated separately on its own endpoint and key.
Effective state is readable at `GET /api/ai/status` and shown as a pill in the
app header. Both are product requirements; the process nevertheless starts
without them in a degraded diagnostic mode — see
[Configuration and operations](configuration.md#environment).

**How invoked.** Through two thin `httpx` REST clients, not the vendor SDKs:

- [`infrastructure/ai/openai_client.py`](../src/policy_platform/infrastructure/ai/openai_client.py)
  — `chat()` posts to `/openai/deployments/{deployment}/chat/completions`, with
  `max_completion_tokens`, optional `response_format: {"type": "json_object"}`
  and optional `reasoning_effort`; `embed()` posts to `.../embeddings`.
- [`infrastructure/search/search_client.py`](../src/policy_platform/infrastructure/search/search_client.py)
  — `upload_documents()` (`mergeOrUpload`), `vector_search()` (hybrid `search` +
  `vectorQueries`), `find_ids_by_filter()`, `delete_documents()`.

**Why REST over the SDKs.** This keeps the dependency surface small and the
request/response boundary inspectable. The trust boundary does not depend on an
SDK abstraction, and the deterministic core remains separate from transport.

**Why it fits.** AI here is a drafting aid, not a decision-maker, so a thin,
inspectable transport is worth more than SDK ergonomics. Both clients fail
closed: when configuration is absent, AI routes return `503` before doing any
work — the deterministic core stays usable, but the platform is then running in
a degraded mode rather than delivering the product. What each AI call is
grounded in is documented in
[How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

**Notable behaviours to know about.** The reasoning deployment can consume its
entire completion budget on hidden reasoning and return empty content; the client
detects this and raises a specific error rather than returning nothing. It also
refuses truncated JSON outright instead of letting a tolerant parser salvage a
half-written object.

---

## Developer and test tooling

| Technology | Role here |
|---|---|
| **pytest** (`>=8.3,<9.0`) | Discovers and runs the active Python suite under `tests/`. |
| **pytest-asyncio** (`asyncio_mode = "auto"`) | Async tests without per-test decorators. |
| **httpx** | Also a dev dependency, for exercising the API surface — no test currently imports it. |
| **Docker Compose** | Local PostgreSQL only. |
| **oxlint** | Frontend linting. There is **no frontend test runner** in `apps/web/package.json`. |
| **TypeScript compiler (`tsc -b`)** | Frontend type checking, wired into `npm run build`. |

**How invoked.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q   # active Python unit-test process
cd apps\web; npm run build
cd apps\web; npm run lint
```

The [testing guide](testing.md) documents the active process by capability, its
commands, expected behavior, isolation and coverage gaps.

**What the suite covers.** Condition semantics, precedence, target matching,
combining algorithm, canonical hashing and determinism, aggregate limits, advice,
policy-test assertions and commitment hashes, document ingestion and extraction,
extraction run identity and delta, passage extraction, formulation, correlation
grouping and agent behaviour, quality checks, attestations, scenario engine, test
proposal, search indexing, and audit behaviour. It uses no database and no
network.

**Why it fits.** The evaluator is a pure function over plain data, so its
guarantees are exactly what a fast in-memory unit suite can prove. Test
configuration lives in `[tool.pytest.ini_options]` in `pyproject.toml`; there is
no separate config file.

## Azure deployment tooling

| Technology | Role here |
|---|---|
| **Docker** | Builds separate non-root FastAPI and React/Nginx runtime images. |
| **Nginx** | Serves the SPA and reverse-proxies same-origin API traffic to the internal API Container App. |
| **Azure Developer CLI (`azd`)** | Collects environment/subscription/location and missing deployment values, then orchestrates Bicep and service image deployment. |
| **Bicep** | Defines the VNet, private endpoints, identities, Container Apps, PostgreSQL, Azure Files, Key Vault, Azure OpenAI, AI Search and monitoring resources. |
| **Azure Container Apps** | Recommended runtime for independently sized public web and internal API containers plus a manual initialization job. |

The infrastructure entry point is [`infra/main.bicep`](../infra/main.bicep), and
[`azure.yaml`](../azure.yaml) connects the two container services to `azd`.
See [Azure deployment](azure-deployment.md) for the complete invocation flow.

**CI/CD is not included.** The `azd` kit is an operator-invoked deployment path;
there is no automatic build, test, scan or release pipeline.

---

## Standards and vocabularies the code follows

These are not packages — they are external specifications the implementation
deliberately borrows from. See the status table in the
[root README](../README.md#standards-and-design-principles) for how far each
goes.

| Standard | Where it shows up |
|---|---|
| **OpenAPI** | Generated by FastAPI at `/openapi.json`, rendered at `/docs` and `/redoc`. |
| **JSON Schema** | Emitted by Pydantic for every contract, and surfaced through the OpenAPI document. |
| **OASIS XACML 3.0** | Target/scope matching, Permit/Deny axis, first-applicable combining, obligations-vs-advice split, and the 8 precedence dimensions. |
| **OMG DMN 1.3+ / FEEL** | The formulator's output shape, and the Collect + SUM hit policy behind aggregate limits. The FEEL parser in `formulation_mapping.py` is a deliberately strict subset. |
| **ISO 37301 / ISO 27001 practice** | Periodic review dates, attestation campaigns, exception/waiver records and RACI ownership fields. |
| **OPA decision logs** | The append-only `evaluations` table and its read-only Decision Log API. |

---

## Proposed, deferred, or explicitly not used

Do not assume any of these from the surrounding documentation — the code does
not use them.

| Technology | Status |
|---|---|
| **Microsoft Agent Framework** | **Not used.** `src/policy_platform/worker/` is an empty reserved package. No `agent-framework` dependency, import, workflow graph, checkpoint runtime or tool-registration layer exists. Current flows are explicit FastAPI services with PostgreSQL state and direct Azure OpenAI/Search calls. |
| **Semantic Kernel** | **Not used.** No dependency, no import, no reference in code. |
| **Microsoft.Extensions.AI** | **Not used.** This is a .NET library; the backend is Python. |
| **Official `openai` / `azure-search-documents` SDKs** | **Not used**; thin `httpx` clients own the required REST calls. |
| **Azure Blob Storage** | **Not used.** Documents are written to the local filesystem under `data/documents/`. |
| **Microsoft Entra ID** | **Not used.** There is no authentication of any kind. |
| **Azure Service Bus / eventing** | **Not used.** `outbox_messages` is modelled; no publisher exists. |
| **Retry / circuit-breaker policies on outbound calls** | **Not implemented.** `httpx` calls use timeouts only. Some services retry a model call after a *schema-validation* failure, which is prompt correction, not transient-fault handling. |
| **Redis, Celery, or any queue/scheduler** | **Not used.** Every flow is request-driven; long work runs in-process. |

### When MAF would become justified

MAF would add more machinery than value while each workflow has a fixed entry
point, explicit service calls and durable business state in PostgreSQL. Revisit
it if the platform introduces resumable multi-agent workflows, dynamic tool
selection, parallel agent branches, cross-process checkpoints or
framework-managed human pause/resume. Until then, the current explicit
orchestration is simpler to audit and test.
