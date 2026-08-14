# PolicyVerbAItim

**AI to read. Evidence to prove. Determinism to decide.**

Policy documents are written for people. Decisions have to be made by machines.
Something has to cross that gap — and everything you trust downstream depends on
whether it crossed honestly.

PolicyVerbAItim turns PDF and DOCX policy documents into structured, executable
rules where every rule points back at the exact clause that produced it. Spans
are copied verbatim and verified in Python, never paraphrased. When the source
is silent, the platform says so instead of filling the gap.

That link survives publication. Uploaded documents are immutable versions
identified by content hash. Every approved rule cites the document version,
clause id and content hash it came from, plus the extraction run, model
deployment and prompt version that drafted it; the clause in turn carries the
page and the exact character range its text occupies in that page. Publishing
snapshots the whole package rather than pointing at live drafts, so a version
cannot change under a decision made against it. Each evaluation records a
canonical SHA-256 over the policy version, the facts supplied and the outcome
reached, and cites the document and clause behind every rule that fired.

The practical consequence: for any decision the system made, you can name the
document release, the clause, and the characters within it — years later,
without trusting that nothing was edited in between.

Three layers, three jobs: AI reads the document, evidence proves what it read,
and the record states how it must be decided — with no model anywhere in the
deterministic decision path.

> The name is the guarantee: *verbatim*, with the AI where it belongs — reading,
> not deciding.

## Two routes, decided by the sentence

Not every policy states a computable test, and pretending otherwise is how a
threshold gets invented for a rule that never had one. Each record therefore
carries an `evaluation_mode` that says how it must be decided:

| Route | The source states its test as | Decided by |
|---|---|---|
| `deterministic` | A computable comparison — a threshold, a date, a count | The rule engine, from the record's `condition` |
| `ai_ready` | Words a reader has to weigh — "reasonable", "as deemed necessary" | A judge reading the record |

`ai_ready` is a **route, not a fault**. A policy is not lower quality for being
written in words; the document is what it is, and a platform that scored it as
a defect would be pressuring itself to fabricate a number. Neither route is
executed here — running or judging a record is a separate system's job. This
platform's product is the record.

## Built on published standards

Policy work is not a place to invent a format. Three standards do the load
bearing, and each is implemented rather than name-dropped:

| Standard | Governs | Where |
|---|---|---|
| [**OASIS XACML 3.0**](https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html) | Decisions (Permit / Deny / NotApplicable), Obligations vs Advice, target matching, attribute naming | Evaluator, rule scope, decision display |
| [**OMG DMN 1.5 / FEEL**](https://www.omg.org/spec/DMN/) | Decision tables, condition expressions, hit policies | AI formulation → executable conditions |
| [**OMG SBVR 1.5**](https://www.omg.org/spec/SBVR/) | Deontic categories — obligation, prohibition, permission, and what is merely definitional | Canonical rule types |

[**Standards**](docs/standards.md) states which one governs which decision, and —
just as important — what is **deliberately not claimed**. A half-claimed standard
is worse than none: it invites you to assume guarantees the code does not give.

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
# API — reads API_PORT from .env, defaults to 8010
.\scripts\run_api.ps1

# Web: Vite prints the URL
cd apps\web
npm run dev
```

Use `scripts/run_api.ps1` rather than invoking uvicorn directly. It clears
ambient `AZURE_OPENAI_*` variables first, which otherwise outrank `.env` and
pair one resource's endpoint with another's key — Azure answers that with a bare
`401` that reads like a bad key. It also binds `0.0.0.0`: `--host 127.0.0.1`
leaves the browser unable to connect when it resolves `localhost` to `::1`,
while `curl` still succeeds.

Interactive API documentation: `http://127.0.0.1:<API_PORT>/docs`.

### Document conversion (optional)

Docling conversion and graph discovery are an optional extra, because they pull
torch, torchvision, accelerate and scipy — a footprint the API neither imports
nor needs. Install them only to work on conversion itself:

```powershell
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install -e ".[dev,graph]"
```

This environment resolves `httpx` to 0.28 to satisfy `docling-graph`, above the
`<0.28` the API pins, so keep it separate from `.venv` rather than treating it
as the default. `scripts/run_api.ps1` prefers `.venv` and falls back to
`.venv-graph`. See [Docling](docs/docling.md).

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
- Docling 2.118.0 + docling-graph 1.9.1 for document conversion and graph discovery
- React 19, TypeScript, Vite, Ant Design
- Azure OpenAI and Azure AI Search through `httpx`
- Azure Container Apps/Bicep/azd assets for the pending Azure deployment

## Checks

```powershell
.\.venv-graph\Scripts\python.exe -m pytest tests -q   # the full suite; no database or network
cd apps\web
npx tsc --noEmit
npm run build
```

Guarantees are also mutation-checked — each one is broken on purpose to confirm
a test notices:

```powershell
.\.venv-graph\Scripts\python.exe scripts\mutation_check.py tests\mutations\core_guarantees.json
```

The suite needs the `graph` extra: 13 modules import Docling directly, and in a
`.venv` built from `.[dev]` alone they fail at collection. The torch footprint
matters for the runtime image, not for a development machine — so install
`.[dev,graph]` if you intend to run the tests.

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
| [How we work](docs/how-we-work.md) | Engineering agreements and the reasoning behind them |
| [Standards](docs/standards.md) | Which standard governs which decision |
| [Architecture](docs/architecture.md) | System boundaries and trust model |
| [Relationships](docs/relationships.md) | How rules are linked, and what is not claimed |
| [Docling](docs/docling.md) | Document conversion and graph discovery |
| [AI assistance](docs/ai-assistance.md) | Extraction, grounding, and validation |
| [Workflows](docs/workflows.md) | Concise operational flows |
| [Capability flows](docs/capability-flows.md) | Seven high-impact diagrams |
| [API](docs/api.md) | Endpoint groups and common sequences |
| [Configuration](docs/configuration.md) | Environment, local operation, and troubleshooting |
| [Testing](docs/testing.md) | Commands and coverage boundaries |
| [Azure deployment](docs/azure-deployment.md) | Pending Container Apps deployment |
| [Data model](docs/data-model.md) | Tables and lifecycle invariants |
| [Failure reports](docs/failures/README.md) | What went wrong, measured from the running system, and what generalises |

Ingestion specifications and the full standards survey remain under `docs/` as
technical reference.
