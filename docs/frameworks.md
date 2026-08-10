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
| Docling 2.118.0 | PDF/DOCX conversion to structured, offset-anchored elements |
| docling-graph 1.9.1 | Dense graph discovery over converted documents |
| pdfplumber / python-docx | Legacy layout-aware ingestion, retained for shadow comparison |
| httpx | Azure OpenAI and Azure AI Search REST calls |

FastAPI request/response models reuse the same Pydantic contracts consumed by
the evaluator. PostgreSQL JSONB stores canonical payloads alongside queryable
columns.

Docling and `docling-graph` are **exactly pinned and deliberately optional**:
they pull torch, torchvision, accelerate and scipy, which the API runtime image
must not carry, and `docling-graph` requires `httpx>=0.28` where the API pins
`<0.28`. Extraction therefore runs in its own environment. See
[Docling](docling.md).

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
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q
cd apps\web
npx tsc --noEmit
npm run build
```

`pyproject.toml` sets `pythonpath = ["src"]`, so the suite runs without an
editable install, and pins the approved Microsoft package feed proxy as the
default index. There is no frontend test runner or CI/CD pipeline.

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

Three standards are implemented: **OASIS XACML 3.0** (decisions, obligations,
target matching, attribute naming), **OMG DMN 1.5 / FEEL** (decision tables and
condition expressions), and **OMG SBVR 1.5** concepts (deontic rule categories).

[Standards](standards.md) is the binding statement of which one governs which
decision, and what is deliberately not claimed.
[Standards research](policy-standards-research.md) holds the full survey.
