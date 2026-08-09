# Policy Governance Engine

AI-assisted policy formalization and governance with deterministic evaluation.

The platform turns PDF/DOCX policy documents into source-traceable structured
rules. AI drafts, humans review and publish, and a pure Python engine evaluates
approved versions without a model in the decision path.

## Capabilities

| Capability | Purpose |
|---|---|
| Document ingestion | Parse immutable PDF/DOCX versions into offset-anchored clauses |
| AI formalization | Draft candidate conditions, effects, scope, facts, and exceptions |
| Human governance | Review, edit, approve, reject, and publish with attribution |
| Immutable versions | Preserve complete policy snapshots and source evidence |
| Deterministic evaluation | Evaluate facts with explicit outcomes and stable hashes |
| Assurance | Quality checks, blind tests, regression guards, and version comparison |
| Evidence | Decision logs, test/quality history, citations, and exports |
| Grounded assistance | Ask AI using approved rules and Azure AI Search clauses |

## Trust model

```text
Source document
-> AI-drafted candidate
-> human review
-> immutable published version
-> deterministic evaluation
-> append-only evidence
```

AI never makes the runtime policy decision.

## Deployment status

| Deployment | Status |
|---|---|
| **Local deployment** | **Available.** Web, API, and PostgreSQL run locally; the API may call configured Azure OpenAI and Azure AI Search endpoints. |
| **Azure deployment** | **Pending.** Docker, Bicep, azd, network, and operations assets are prepared and statically validated; no Azure-hosted environment has been provisioned from this repository. |

Using Azure AI endpoints from the local API remains a Local deployment.

## Quick start

Prerequisites: Docker Desktop, Python 3.11+, and Node.js 18+.

```powershell
Copy-Item .env.example .env
docker compose -f infra/local/docker-compose.yml up -d

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head

cd apps\web
npm install
```

Run in separate terminals:

```powershell
# API: http://127.0.0.1:8010
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010

# Web: Vite prints the URL
cd apps\web
npm run dev
```

Interactive API documentation: <http://127.0.0.1:8010/docs>.

AI-assisted features require Azure OpenAI. Retrieval-grounded features also
require Azure AI Search. See [Configuration](docs/configuration.md).

## User journey

1. Create or open a project.
2. Upload a versioned source document.
3. Extract candidate rules.
4. Review rules against source evidence.
5. Run pre-publish quality checks.
6. Publish an immutable policy version.
7. Create blind tests and regression guards.
8. Evaluate facts and inspect the Decision Log.

See the illustrated [User guide](docs/user-guide.md).

## Stack

- Python 3.11, FastAPI, Pydantic, SQLAlchemy async, Alembic
- PostgreSQL 16
- React 19, TypeScript, Vite, Ant Design
- Azure OpenAI and Azure AI Search through `httpx`
- Azure Container Apps/Bicep/azd assets for the pending Azure deployment

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd apps\web
npm run build
npm run lint
```

## Important boundaries

- The header actor/persona is workflow attribution, not authentication.
- Published versions are immutable.
- Missing facts produce `INDETERMINATE`; the engine does not guess.
- Search is grounding, not execution.
- Azure deployment and production authorization remain pending.

See [Known limitations](docs/known-limitations.md) and the
[Security roadmap](docs/security-roadmap.md).

## Documentation

| Page | Purpose |
|---|---|
| [User guide](docs/user-guide.md) | End-to-end journey with screenshots |
| [Architecture](docs/architecture.md) | System boundaries and trust model |
| [Workflows](docs/workflows.md) | Concise operational flows |
| [Capability flows](docs/capability-flows.md) | Seven high-impact diagrams |
| [AI assistance](docs/ai-assistance.md) | Extraction, grounding, and validation |
| [API](docs/api.md) | Endpoint groups and common sequences |
| [Configuration](docs/configuration.md) | Environment, local operation, and troubleshooting |
| [Testing](docs/testing.md) | Commands and coverage boundaries |
| [Azure deployment](docs/azure-deployment.md) | Pending Container Apps deployment |
| [Data model](docs/data-model.md) | Tables and lifecycle invariants |

Detailed ADRs, ingestion specifications, and standards research remain available
under `docs/` as technical reference.
