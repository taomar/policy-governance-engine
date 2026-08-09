# Frameworks and technologies

Only technologies used by the implementation are listed here.

## Runtime

| Technology | Responsibility |
|---|---|
| Python 3.11 | Backend runtime |
| FastAPI / Uvicorn | HTTP API and ASGI server |
| Pydantic / pydantic-settings | Contracts and typed environment configuration |
| PostgreSQL 16 | System of record |
| SQLAlchemy async / asyncpg | Application persistence |
| Alembic / psycopg | Schema migrations |
| pdfplumber / python-docx | PDF/DOCX layout-aware ingestion |
| httpx | Azure OpenAI and Azure AI Search REST calls |

FastAPI request/response models reuse the same Pydantic contracts consumed by
the evaluator. PostgreSQL JSONB stores canonical payloads alongside queryable
columns.

## Frontend

| Technology | Responsibility |
|---|---|
| React 19 | Single-page UI |
| TypeScript | Typed frontend and API client |
| Vite | Development server and build |
| Ant Design / icons | Controls, drawers, forms, tabs, and registers |
| oxlint | Frontend linting |

`apps/web/src/api.ts` is the typed HTTP client. `ActorContext.tsx` stores the
local workflow identity/persona.

## AI and grounding

| Service | Responsibility |
|---|---|
| Azure OpenAI | Extraction, quality, correlation, rewrite, summaries, tests, Ask AI |
| Azure AI Search | Hybrid/vector clause retrieval |

Both are called through small REST clients. Runtime policy evaluation has no AI,
database, or network dependency.

## Development and testing

| Tool | Responsibility |
|---|---|
| pytest / pytest-asyncio | Backend unit tests |
| TypeScript compiler | Frontend type checking |
| Docker Compose | Local PostgreSQL |
| Docker | API and web images |

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd apps\web
npm run build
npm run lint
```

There is no frontend test runner or CI/CD pipeline.

## Deployment tooling

| Tool | Status |
|---|---|
| Azure Developer CLI (`azd`) | Prepared for pending Azure deployment |
| Bicep | Defines Container Apps, networking, data, AI, identity, and monitoring |
| Azure Container Apps | Selected Azure runtime |
| Nginx | Serves the SPA and proxies same-origin API traffic |

The Local deployment is available. Azure deployment remains pending live
provisioning and validation.

## Standards vocabulary

The code aligns with OpenAPI, JSON Schema, XACML concepts, DMN/FEEL concepts,
ISO governance practices, and OPA-style decision logging. See
[Standards research](policy-standards-research.md) for optional depth.
