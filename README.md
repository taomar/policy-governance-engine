# Policy Platform — Deterministic Policy Formalization

Turn enterprise policy documents (HR handbooks, IT provisioning policies, expense
policies, labour law) into **structured, machine-evaluable rules** — and evaluate
them the same way every time.

AI reads documents and *drafts* rules. A human reviews and approves them. A pure
Python engine — with no model call anywhere in its path — makes the actual
decision. Published policy versions are immutable snapshots that can always be
traced back to the verbatim sentence they came from.

> **Maturity: working prototype with a prepared Azure deployment kit.** The
> application remains single tenant and its actor roles are not production
> authorization. No Azure environment was deployed while preparing this repository.

---

## Why this system exists

Policy is written as prose, and prose is difficult to govern. A handbook
sentence cannot be tested, cannot be executed identically twice, and cannot
prove which paragraph a decision came from. In practice that means three
recurring failures: two people read the same clause and act differently; nobody
can tell whether a policy change broke a case that used to work; and an auditor
asking "why was this approved?" gets a recollection rather than a record.

This platform closes those gaps with what it actually builds:

- **Prose becomes structured, reviewable policy.** Source documents are parsed
  into offset-anchored clauses, and an AI pipeline drafts candidate rules from
  them — always as drafts, never as published policy.
- **Every rule keeps its receipt.** Extracted passages must be verbatim
  substrings of the source, re-checked in Python, and the clause linkage is
  persisted as `evidence_references` when the rule is published.
- **Decisions are deterministic.** A pure Python engine — no model call anywhere
  in its path — turns facts into a decision with a per-rule breakdown and a
  stable result hash. The same inputs always produce the same output.
- **Policy can be tested like code.** Named scenarios are pinned as regression
  tests and re-run automatically on every publish, so a change that breaks a
  known case is visible immediately.
- **Humans stay in control.** Nothing a model produces reaches a published
  version without an explicit human approval, and every approval, publication
  and disposition is recorded in an append-only audit trail.

What it is not: it does not replace legal or compliance judgement, it does not
authenticate anyone, and it does not decide anything a human has not first
approved.

## What it does

| Capability | Summary |
|---|---|
| **Document ingestion** | Upload PDF/DOCX; layout-aware parsing produces stable `Clause` records with source offsets, reconstructed across page breaks. |
| **AI-assisted extraction** | A two-stage agent pipeline drafts candidate rules from clauses — always as `candidate` rows, never auto-published. |
| **Human review & governance** | Draft, edit, approve, reject, request-changes, manager override, bulk review — with an audit trail. |
| **Immutable publishing** | Approved candidates are published as a full, versioned, immutable rule snapshot. |
| **Deterministic evaluation** | Facts in → decision out, with rule-by-rule status, precedence resolution, exceptions, aggregate caps, advice notes and a stable result hash. |
| **Quality analysis** | Deterministic structural checks plus an AI review pass, for published versions *and* pre-publish candidates. |
| **Cross-rule correlation** | Deterministic grouping + AI classification of contradictions, overlaps, duplicates and gaps. |
| **Policy tests** | Named regression tests — AI may propose them, only the deterministic engine executes them; re-run automatically on publish. |
| **Version compare** | Deterministic rule-level diff between two published versions, with an AI plain-English narrative. |
| **Grounded chat** | "Ask AI" answers questions about a policy set, citing the source clauses it used. |
| **Export & decision log** | JSON / JSONL / CSV export of rules and candidates; append-only log of every evaluation call. |

Azure OpenAI and a grounding/search layer are **required**, not optional. The
intended product is AI-assisted throughout: extraction, quality review,
correlation, rewrite, test proposal and grounded chat all need Azure OpenAI, and
grounded answers additionally need a retrieval layer — today **Azure AI Search**,
which is what the code integrates directly.

> **Current runtime enforcement is weaker than that requirement.** The process
> still starts with the `AZURE_*` variables blank. That is a **degraded,
> diagnostic mode allowed by the current code**, not a supported full-product
> deployment: AI endpoints return a clean `503`, the UI shows an "AI disabled"
> pill, clause indexing is skipped, and only deterministic features (import,
> evaluate, policy tests, export, decision log, audit) keep working. There is no
> fail-fast startup check.

How the models are grounded — sources, indexing, hybrid retrieval, citation and
verbatim verification — is documented in
[AI assistance → How the AI is grounded](docs/ai-assistance.md#how-the-ai-is-grounded).

A diagram and a short write-up for each capability — plus search, aggregate
limits, exceptions and attestations — is in
[`docs/capability-flows.md`](docs/capability-flows.md), and what each capability
is defended by in the test suite is in
[`docs/testing.md`](docs/testing.md#active-test-capability-groups).

## Standards and design principles

Each row states what the repository actually does. **Implemented** means the
mechanism is in the code; **aligned** means the design deliberately follows the
standard's vocabulary without claiming conformance; **partial** and **deferred**
mean what they say. No row asserts certification or formal compliance.

| Standard / principle | Status | Where, and why it matters |
|---|---|---|
| **OpenAPI 3.x** | Implemented | Generated by FastAPI at `/openapi.json`, rendered at `/docs` and `/redoc`. The contract is derived from the same models the code runs on, so it cannot drift from the implementation. |
| **JSON Schema via Pydantic v2** | Implemented | Every canonical rule, condition node and evaluation payload is a Pydantic model in `src/policy_platform/contracts/`. A malformed rule is rejected at the boundary instead of failing at decision time. |
| **Canonical condition AST, allowlist-only** | Implemented | 20 allowlisted operators, four node types, no `eval` and no dynamic dispatch. A policy condition cannot become arbitrary code. |
| **Deterministic evaluation with a stable hash** | Implemented | `evaluator/` has no database, network or AI dependency; results are hashed over canonically serialised JSON (sorted keys, ISO dates). A caller can prove a result was not altered afterwards. |
| **Explicit indeterminacy** | Implemented | A missing fact yields `INDETERMINATE` with the exact list of what was missing — never a guess and never silently false. |
| **Provenance and verbatim evidence** | Implemented | Clause offsets are exact by construction; extracted passages are re-verified as substrings; `evidence_references` survive publication. Traceability is what makes a rule defensible. |
| **Immutable published versions** | Implemented | `approved_policy_versions` are full snapshots, never edited in place; exactly one is active per policy set. A decision can always be replayed against the version that produced it. |
| **Append-only records** | Implemented | `evaluations`, `policy_test_runs` and `audit_events` are write-once, and published versions are never edited in place. Evidence that can be edited is not evidence. |
| **OASIS XACML 3.0** | Aligned | Target/scope matching, the Permit/Deny axis, precedence-ordered first-applicable combining, the 8 precedence dimensions, and the Obligations-vs-Advice split. Borrowing a named mechanism beats inventing ad hoc conflict resolution. |
| **OMG DMN 1.3+ and FEEL** | Partial | The formulator emits DMN-shaped JSON, and aggregate limits implement the Collect hit policy with a SUM aggregator. The FEEL parser is a strict subset: an expression it does not fully understand yields *no* condition rather than a plausible guess. |
| **OPA-style decision logging** | Implemented | Every evaluation call is persisted with its facts, result and hash, and is browsable read-only in the Decision Log. |
| **ISO 37301 / ISO 27001 governance practice** | Partial | Periodic review dates, attestation campaigns, exception/waiver records and RACI ownership fields exist. No control-to-framework mapping and no audit-evidence generation. |
| **Semantic versioning** | Not implemented | Published versions carry a monotonically increasing integer `version_number` per policy set. There is no major/minor/patch semantics anywhere. |
| **ODRL** | Not implemented | The canonical rule model is deontic in spirit — permission, prohibition, obligation — but it is not an ODRL profile and no ODRL serialisation exists. |
| **Microsoft Agent Framework (MAF)** | Not used | No MAF package, import, workflow graph, checkpoint store or tool-registration runtime exists. The current request-driven workflows use explicit FastAPI services, PostgreSQL state and direct Azure OpenAI/Search REST calls. Adding MAF now would duplicate orchestration; reconsider it if the product needs resumable multi-agent workflows, dynamic tool routing, parallel branches or framework-managed pause/resume. |
| **Authentication and multi-tenancy** | Not implemented | Deliberately out of scope for a local prototype; see [Configuration & operations](docs/configuration.md#security-status). |

Full standards comparison — XACML, OPA, DMN, AWS IAM, Azure Policy, ISO, NIST —
with a prioritised gap list lives in
[`docs/policy-standards-research.md`](docs/policy-standards-research.md).
Microsoft-specific relationships are in
[`docs/microsoft-technologies.md`](docs/microsoft-technologies.md).

## Outputs and how to use them

Everything the platform produces, what shape it comes in, and what it is good
for. Downloadable files are marked as such; the rest are API responses or
database records read through the UI.

### Downloadable files

| Output | Format | Produced by | Use it for |
|---|---|---|---|
| **Published rule export** | JSON array, JSONL, or CSV — `GET /api/policy-sets/{key}/versions/{id}/export?format=` | Policies tab export menu | Handing an immutable version to another system, an archive, or a spreadsheet review. A verbatim re-serialisation — nothing is summarised or reworded. |
| **Candidate rule export** | Same three formats — `GET /api/policy-sets/{key}/candidate-rules/export?format=` | Review tab export menu | Reviewing a large extraction offline, or sharing a draft set with legal before anyone approves. Optionally filtered by review status, and includes the review metadata (status, reviewer, notes) alongside each `rule_`-prefixed rule field. |
| **Selected-policy JSONL** | JSONL, generated in the browser | Policies tab, selected or all rules | Pulling a specific subset — one family of rules, one topic — without exporting the whole version. |

CSV nests structured fields such as `condition` and `exceptions` as JSON in a
single cell so no information is dropped, and is written with a UTF-8 BOM so
Excel opens it correctly.

### API responses and persisted records

| Output | Shape | Produced by | Use it for |
|---|---|---|---|
| **Canonical rule** | `CanonicalRule` JSON — rule type, effect, condition AST, required facts, exceptions, advice, scope, precedence fields, evidence | Extraction, manual drafting, publish | The unit everything else consumes: it is what the evaluator reads, what exports serialise, and what a reviewer edits. |
| **Approved policy version** | Immutable snapshot of every rule plus aggregate limits, with a version number and effective dates | `POST /api/policy-sets/{key}/publish` | The releasable artifact. Pin an evaluation to it, diff it against another version, or attach an attestation campaign to it. |
| **Evaluation result** | Overall status, outcome, per-rule results with `overridden_by`, triggered exceptions, aggregate breaches, advice notes, evidence references, `result_hash` | `POST /api/evaluations` | Driving a downstream decision, and proving afterwards exactly which rules fired and why. The hash lets a consumer verify the result was not altered. |
| **Decision log entry** | The full request facts and response, queryable by status, correlation ID or calling system | Every evaluation call; read at `GET /api/evaluations/policy-sets/{key}` | Answering "what did we decide for this case, and under which version?" — the audit question that prose policy cannot answer. |
| **Policy test run** | Pass/fail, explanation listing every mismatch, the version it ran against, the trigger, and a committed expectation hash | Manual run, validation batch, or automatic re-run on publish | Regression evidence. A failing run after a publish tells you precisely which expectation the new version broke. |
| **Quality run** | Findings tagged `deterministic` or `ai_review`, each with severity, category, impact, acceptance boundaries, reviewer questions and affected rule IDs, plus a methodology version | Quality tab, published or candidate scope | Deciding what to fix before publishing, and showing later that a fix stuck — runs are immutable, so two runs are directly comparable. |
| **Correlation run and findings** | Relationship classification between grouped rules, each with a reviewer disposition (`open` / `accepted` / `dismissed` / `resolved`), the deciding actor and notes | `POST /api/ai/policy-sets/{key}/correlate` | Finding contradictions, duplicates and overlaps that per-rule review structurally cannot see. |
| **Version diff** | Added / removed / changed / unchanged rules with field-level deltas, plus an optional AI narrative | Compare tab | Change review and release notes. The diff is deterministic; only the narrative is generated. |
| **Audit event** | Immutable record of an approval, publication or disposition, with actor and details | Written by `infrastructure/audit.py` | Governance evidence: who did what, when, to which entity. |
| **Attestation record** | Person, published version, due date, and computed `pending` / `acknowledged` / `overdue` status | Attestation campaigns *(backend and UI built, hidden in this phase)* | Showing that the people bound by a policy version have acknowledged it. |
| **Indexed clause** | Clause text plus embedding in Azure AI Search, keyed and filtered to this platform's documents | Document upload (indexing is best-effort; see [grounding](docs/ai-assistance.md#how-the-ai-is-grounded)) | Grounding Ask AI answers and scenario generation in the organisation's own wording rather than model recall. |

### What this gets you

Structured rules make policy diffable and reviewable. Evidence references make a
decision defensible back to a sentence. Deterministic results with a hash make a
decision reproducible and verifiable. Test runs turn "we think this still works"
into a checkable claim. Exports let the same governed rule set feed a
spreadsheet review, an archive, or another system without a re-typing step where
meaning gets lost.

---

## Stack

- **Backend** — Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2
- **Database** — PostgreSQL 16 via Docker Compose (host port **5433**)
- **Frontend** — React 19 + TypeScript + Vite, Ant Design v6
- **AI (required)** — Azure OpenAI (reasoning + fast deployments) and a
  grounding/search layer, today Azure AI Search, called through thin `httpx`
  REST clients

Full detail — what each framework is responsible for, where it is configured, and
what is deliberately *not* used — is in
[`docs/frameworks.md`](docs/frameworks.md).

## Azure deployment preparation

A deployment-ready **Azure Container Apps + Bicep + azd** kit is available under
`infra/`. It provisions a VNet-integrated public web app and internal API,
private PostgreSQL, Azure Files, Key Vault, Azure OpenAI, Azure AI Search,
monitoring, and a fresh schema/index initialization job. No free service tier is
selected.

The Azure database starts empty: Alembic creates the schema, Search index
schemas are initialized, and no local policies, files, samples or rows are
migrated.

Start with:

- [Azure deployment](docs/azure-deployment.md)
- [Prerequisites](docs/azure-prerequisites.md)
- [Deployment variants](docs/azure-deployment-variants.md)
- [Azure operations](docs/azure-operations.md)

The documented future entry point is `azd up`; it was **not** executed during
preparation.

## Pending implementation

Three requested workstreams are **pending**. Some enabling pieces already exist
(the Entra web ingress gate and managed identities for ACR and Key Vault), but
none of the workstreams is complete or ready to claim.

| Workstream | Status | Why it matters |
|---|---|---|
| Application authentication, RBAC, user management and admin page | `PENDING` | The API does not validate caller identity. Authorization is a client-supplied `actor_role` field in the request body, and the acting role is a dropdown backed by browser `localStorage` — so a caller that can reach the API can claim `policy_manager`. This must be replaced by server-validated Microsoft Entra ID claims, an explicit role/permission model, and an admin page for application access. |
| Azure security hardening with managed identities | `PENDING` | Managed identity currently covers only registry pulls and Key Vault secret reads. Azure OpenAI and Azure AI Search are called with API keys, PostgreSQL uses an administrator password, and the Azure Files mount uses a storage account key. The plan moves each supported dependency to managed identity and is explicit about the one that cannot become keyless without moving document storage to Blob Storage. |
| Live Azure deployment validation | `PENDING` | The deployment kit has only been validated statically — schema, Bicep lint, container builds, parameter and secret scanning. No subscription has ever been provisioned from it, so identity, role enforcement, private DNS, quota, model availability, restore and rollback are all unproven. |

The admin page in that plan manages **application access only**. It does not
create, modify or delete Microsoft Entra tenant accounts.

## Quick start

Prerequisites: Docker Desktop, Python 3.11+, Node.js 18+.

```powershell
# 1. Configuration
Copy-Item .env.example .env      # skip if .env already exists

# 2. Database
docker compose -f infra/local/docker-compose.yml up -d

# 3. Backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head

# 4. Frontend
cd apps\web; npm install; cd ..\..
```

Run the API and the web app in two terminals:

```powershell
# Terminal 1 — API on http://127.0.0.1:8010
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010 --app-dir src

# Terminal 2 — web app (Vite prints the actual port)
cd apps\web; npm run dev
```

Then open the URL Vite printed, and the interactive API docs at
<http://127.0.0.1:8010/docs>.

Run the checks (see [`docs/testing.md`](docs/testing.md) for the full guide):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q   # active Python unit-test process
cd apps\web; npm run build                            # type-check + build (not a test suite)
cd apps\web; npm run lint                             # oxlint
```

There are no automated frontend tests; `build` and `lint` are type/lint checks
only.

> Run the API **without** `--reload`: file-watcher restarts can interrupt
> long-running extraction requests.

Sample fixtures live in `samples/`:

```powershell
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets `
  -H "Content-Type: application/json" `
  --data-binary "@samples/policies/expense-policy-set.json"

curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/expense-policy/versions `
  -H "Content-Type: application/json" `
  --data-binary "@samples/policies/expense-policy-v1-import.json"

curl.exe -s -X POST http://127.0.0.1:8010/api/evaluations `
  -H "Content-Type: application/json" `
  --data-binary "@samples/evaluation-requests/satisfied-small-expense.json"
```

## Repository structure

```
src/policy_platform/
  contracts/        Pydantic contracts: canonical rule, condition AST, evaluation DTOs
  evaluator/        Pure deterministic engine (no I/O, no AI): conditions, precedence,
                    engine, test_runner
  domain/           SQLAlchemy ORM entities
  infrastructure/   DB session, repositories, mappers, settings, ingestion,
                    AI services, search clients, prompts, export, audit
  api/              FastAPI app + 10 routers
  worker/           Reserved placeholder (currently empty)
apps/web/           React + TypeScript frontend (Vite)
alembic/            Database migrations
samples/            Sample policy sets, versions, evaluation requests, source documents
scripts/            One-off backfill/utility scripts (see docs/testing.md)
tests/unit/         pytest suite (see docs/testing.md)
infra/              Azure Bicep/azd assets plus local Docker Compose under infra/local
docs/               Documentation (see below)
```

## Documentation

Start at the **[documentation index](docs/README.md)**.

| Page | For |
|---|---|
| [Architecture](docs/architecture.md) | Components, boundaries, invocation paths |
| [Capability flows](docs/capability-flows.md) | A diagram per capability — ingestion, review, publish, evaluate, test, quality, search, exports |
| [Azure deployment](docs/azure-deployment.md) | Recommended Container Apps architecture, SKUs, network, parameters and future azd flow |
| [Azure variants](docs/azure-deployment-variants.md) | Container Apps, App Service, hardened-private and Foundry IQ alternatives |
| [Azure prerequisites](docs/azure-prerequisites.md) | Tools, roles, providers, quotas, Entra, models and network inputs |
| [Azure operations](docs/azure-operations.md) | Fresh initialization, scaling, backups, rotation and troubleshooting |
| [Testing and scripts](docs/testing.md) | Active pytest capability groups, commands, expected behavior, isolation, and coverage gaps |
| [Workflows](docs/workflows.md) | UI navigation and the end-to-end flows |
| [Frameworks & technologies](docs/frameworks.md) | What each framework does here, and what is not used |
| [Microsoft technologies](docs/microsoft-technologies.md) | Azure services and Microsoft patterns, with first-party references |
| [AI assistance](docs/ai-assistance.md) | What the AI components actually do, and [how they are grounded](docs/ai-assistance.md#how-the-ai-is-grounded) |
| [API](docs/api.md) | Endpoint groups and interactive API docs |
| [Data model](docs/data-model.md) | Tables and lifecycle invariants |
| [Configuration & operations](docs/configuration.md) | Env vars, setup, security, observability |
| [Known limitations](docs/known-limitations.md) | What is deliberately not built |

Deeper public background lives in `docs/specs/` (ingestion and extraction
details) and `docs/policy-standards-research.md`. `PRODUCT.md` and `DESIGN.md`
capture product positioning and the visual design language.
