# Architecture

This page is for implementers and architecture reviewers. It is a light map of the runtime: what the pieces are, what each is responsible for, and how they call each other. For per-capability detail — one diagram per capability, with triggers, outputs and limits — see [Capability flows](capability-flows.md), which is the detailed companion to this page rather than a duplicate of it. For what the automated suite actually defends, see [Testing and scripts](testing.md#test-architecture). For the frameworks involved see [Frameworks and technologies](frameworks.md); deeper ingestion and extraction detail is available in the [specs](specs/).

## Shape of the system

Three processes plus the Azure services the product requires:

```mermaid
flowchart LR
    User(["Reviewer / Manager / Operator"])
    Web["React + Vite web app<br/>apps/web"]
    API["FastAPI backend<br/>src/policy_platform/api"]
    DB[("PostgreSQL 16<br/>Docker, port 5433")]
    Files[["Local file store<br/>data/documents/"]]
    AOAI["Azure OpenAI<br/>(required)"]
    Search["Azure AI Search<br/>(required grounding layer)"]

    User --> Web
    Web -- "JSON over HTTP" --> API
    API --> DB
    API --> Files
    API -. "httpx REST" .-> AOAI
    API -. "httpx REST" .-> Search
```

Azure OpenAI and a grounding/search layer are product requirements, not add-ons: without them the platform has no extraction, quality, correlation or grounded chat. The current code nevertheless *starts* without them, which is a degraded diagnostic mode — AI routes return `503`, clause indexing is skipped — rather than a supported deployment. See [AI assistance](ai-assistance.md) and [Configuration and operations](configuration.md#environment).

The web app is a pure client: it holds no policy logic, and every decision, extraction and quality result comes from the API. Extraction runs inside the request that starts it, which is why a large document takes minutes rather than returning immediately.

## Backend layers

The backend is layered by dependency direction: contracts and the evaluator sit at the centre and depend on nothing else in the codebase.

| Layer | Package | Responsibility |
|---|---|---|
| Contracts | `policy_platform.contracts` | Pydantic models for the canonical rule, the condition AST, evaluation request/response, policy tests, correlation findings, and the canonical hash. No I/O. |
| Evaluator | `policy_platform.evaluator` | The deterministic decision core: condition interpretation, precedence resolution, the evaluation engine, and the policy-test runner. No database, no network, no AI. |
| Domain | `policy_platform.domain` | SQLAlchemy ORM entities and table definitions. |
| Application | `policy_platform.application` | Use cases that coordinate infrastructure for more than one entry point. Currently one module, `policy_case_decision.py`, which owns the project-case decision for both the in-product route and the audited external API. |
| Infrastructure | `policy_platform.infrastructure` | Everything that touches the outside world, grouped into thirteen sub-packages by responsibility (see below). Two modules stay at the root: `settings.py`, imported across every sub-package, and `prompt_assets.py`, which must sit level with the `prompts/` directory it locates. |
| API | `policy_platform.api` | FastAPI app, request/response schemas, and fifteen routers. |

### Inside infrastructure

Grouped by the question each answers, not by the technology each uses. A module that calls a model sits with the capability it serves — `quality/ai_quality.py`, `extraction/ai_extraction.py` — because "calls an LLM" is a transport detail while "is part of extraction" is what someone changing extraction needs to find together. `ai/` holds the client itself.

| Sub-package | Responsibility |
|---|---|
| `persistence/` | Async engine and session, repositories, mappers, version import, audit |
| `ingestion/` | PDF/DOCX parsing into clauses, source numbering, manual entry |
| `docling/` | Docling conversion and graph discovery, under its own dependency boundary — see [Docling](docling.md) |
| `extraction/` | The two model stages, then the condition compiler and what a record can support |
| `consolidation/` | Collapsing a record the model emitted more than once into a single record |
| `assembly/` | Grouping rules into the policies their source stated, with provision history and the rule-name and topic-label lookups |
| `projection/` | Restating an approved rule: XACML, DMN parity, version diff, export |
| `quality/` | Faithfulness to source, and the duplicate/contradiction/instability passes |
| `correlation/` | Deterministic relationship discovery, and model-assisted contradiction finding |
| `policy_tests/` | Proposing, committing to and running saved tests |
| `assistants/` | Chat, draft, rewrite, summary, compare, scenario — advisory only |
| `ai/`, `search/` | Azure OpenAI and Azure AI Search clients |

### Key modules

| Concern | Module |
|---|---|
| App factory, CORS, startup reconciliation | `api/app.py` |
| Deterministic decision | `evaluator/engine.py`, `evaluator/conditions.py`, `evaluator/precedence.py` |
| Policy-test execution | `evaluator/test_runner.py` (pure) + `infrastructure/policy_tests/policy_test_execution.py` (DB-aware) |
| Document parsing | `infrastructure/ingestion/document_ingestion.py` → `infrastructure/ingestion/document_extraction.py` |
| Document conversion & graph discovery | `infrastructure/docling/` (converter, pipeline, verification, handoff) — see [Docling](docling.md) |
| Extraction pipeline | `infrastructure/extraction/ai_extraction.py`, `passage_extractor.py`, `policy_formulator.py`, `formulation_mapping.py` |
| Rule relationships | `contracts/relationships.py`, `infrastructure/correlation/relationship_discovery.py` — see [Relationships](relationships.md) |
| Quality analysis | `infrastructure/quality/ai_quality.py` |
| Cross-rule correlation | `infrastructure/correlation/correlation_service.py` + `correlation_agent.py` |
| Version diff & narrative | `infrastructure/projection/rule_delta.py` (computes) + `infrastructure/assistants/ai_compare.py`, `infrastructure/assistants/rule_change_explainer.py` (narrate) |
| Grounded chat | `infrastructure/assistants/ai_chat.py` |
| Project-case decision | `application/policy_case_decision.py` (reserve/decide/finalise, idempotency, envelope) + `contracts/case_decision.py` (`case_decision_v1`, the hash preimage) + `infrastructure/assistants/ai_case_project.py` (retrieval and evaluation) |
| Azure clients | `infrastructure/ai/openai_client.py`, `infrastructure/search/search_client.py`, `search/indexing.py` |
| Configuration | `infrastructure/settings.py` |
| Persistence access | `infrastructure/persistence/repositories/` (seven modules, one per part of the lifecycle), `infrastructure/persistence/mappers.py`, `infrastructure/persistence/db.py` |

## How components are invoked

Everything is request-driven: a call arrives, the work happens inside that request, and the response carries the result. Extraction is the visible consequence — a large document takes minutes rather than returning a job id.

- **Browser → API.** The web app calls the API over HTTP/JSON from `apps/web/src/api.ts`, using `VITE_API_BASE_URL`. CORS is configured in `api/app.py` for the local Vite ports.
- **Router → service.** Each router injects an `AsyncSession` via FastAPI dependency injection and calls one infrastructure service or repository.
- **Service → Azure.** AI services construct an `AzureOpenAIClient` / `AzureSearchClient` and issue direct REST calls with `httpx`. If Azure OpenAI is not configured, AI routes reject with `503` before any work starts; if search is not configured, clause indexing is skipped and retrieval-backed grounding is unavailable. `ai_chat.py` and `ai_test_proposal.py` read the shared clause index; `ai_case_project.py` reads a project's own policy index, and `search/policy_index.py` is the only module that creates, rebuilds or drops one — see [AI assistance → How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).
- **Anything → evaluator.** The evaluator is called as a plain function with an in-memory `ApprovedPolicyPackage` and a fact dictionary. Callers are the evaluation endpoint, the policy-test executor, and the AI scenario tester.
- **Startup.** A lifespan hook marks an `extraction_runs` row it owns (`owner_kind == OWNER_API`) still flagged `running`/`pending` as `failed`, because an in-process extraction does not survive an API restart. Runs owned by another process are left untouched, so the API only cleans up after itself.

## The document-to-decision path

```mermaid
flowchart TD
    Upload["Upload PDF/DOCX<br/>POST /api/documents/upload"]
    Ingest["Layout-aware ingestion<br/>document_ingestion"]
    Clauses[("clauses")]
    Index["Best-effort search indexing<br/>search/indexing"]

    Extract["Extraction run<br/>POST /api/ai/.../extract"]
    Stage1["Stage 1 — verbatim passages<br/>passage_extractor"]
    Stage2["Stage 2 — canonical + DMN JSON<br/>policy_formulator"]
    Map["Deterministic mapping<br/>formulation_mapping"]
    Cand[("candidate_rules")]

    Review["Human review<br/>approve / reject / edit / override"]
    Publish["Publish immutable version<br/>POST /api/policy-sets/:key/publish"]
    Approved[("approved_policy_versions<br/>approved_rules")]

    Eval["Deterministic evaluation<br/>POST /api/evaluations"]
    Log[("evaluations — append-only")]

    Upload --> Ingest --> Clauses
    Clauses -.-> Index
    Clauses --> Extract --> Stage1 --> Stage2 --> Map --> Cand
    Cand --> Review --> Publish --> Approved
    Approved --> Eval --> Log
```

Solid arrows are the governed path. The dotted arrow is best-effort: a search indexing failure is logged and swallowed so an upload never fails because Azure is unavailable. That resilience is deliberate, but it means a document can be fully usable while being invisible to retrieval — see [grounding limitations](ai-assistance.md#limitations).

## Where the trust boundary sits

This is the single most important architectural property of the platform.

```mermaid
flowchart LR
    subgraph Probabilistic["Probabilistic — advisory only"]
        P1["Passage extraction"]
        P2["Policy formulation"]
        P3["Quality review pass"]
        P4["Correlation classification"]
        P5["Rewrite, draft, compare narrative"]
        P6["Test proposal"]
        P7["Ask AI chat"]
    end

    subgraph Human["Human decision"]
        H1["Approve, reject, request changes"]
        H2["Publish version"]
        H3["Accept or reject a proposed test"]
    end

    subgraph Deterministic["Deterministic — code only"]
        D1["Condition AST interpreter"]
        D2["Precedence resolution"]
        D3["Evaluation engine and result hash"]
        D4["Policy test runner"]
        D5["Rule diff, structural quality checks, export"]
    end

    Probabilistic --> Human --> Deterministic
```

No model participates in a runtime decision. Every AI output is a *draft* or an *observation* that a human accepts before it can influence a published version, and the evaluator only ever reads approved, versioned rules.

That statement is about the deterministic decision path — `POST /api/evaluations` and the policy-test runner. A **project case** is a different thing and is labelled as one: a model reads published, human-approved records and answers a question in prose. It cannot alter a rule, a version or a determination made by the evaluator, and its receipt names the route that produced it so a reader never mistakes it for an engine result. See [one decider, two surfaces](#one-decider-two-surfaces).

Supporting invariants, all enforced in code:

- Stage 1 passages are re-checked in Python for verbatim containment; a fabricated quote is caught by string comparison, not by re-reading.
- Structured rule identity, rule-type mapping and condition compilation are plain Python in `formulation_mapping.py`; an expression the parser does not fully understand yields *no* condition rather than a guess.
- Published versions are full immutable snapshots, never edited in place.
- `evaluations`, `policy_test_runs` and `audit_events` are append-only.
- Quality and correlation findings are stored as *runs*, so a finding is always a statement about the rules as they stood at that moment.

Each invariant above has a test module behind it — the mapping is in [Testing and scripts → active test capability groups](testing.md#active-test-capability-groups), and the boundaries the suite deliberately does not cross are in [gaps](testing.md#current-coverage-gaps).

## One decider, two surfaces

A project case — a question in plain English, put to a project's published policies — is reachable two ways, and the difference between them is not the decision but what is owed to the caller afterwards.

```mermaid
flowchart TD
    Reviewer(["Reviewer in the product"])
    External(["External system"])

    Legacy["POST /api/ai/policy-sets/{key}/case-answer<br/>in-product reviewer surface"]
    Audited["POST /api/policy-decisions/{project_key}/case<br/>audited external contract"]

    App["application/policy_case_decision.py<br/>the only caller of the decider"]
    Decider["assistants/ai_case_project<br/>retrieval, then evaluation"]
    Receipts[("policy_case_decisions<br/>append-only receipts")]

    Reviewer --> Legacy --> App
    External --> Audited --> App
    App --> Decider
    Audited -. "reserve → decide → finalise" .-> Receipts
```

Both routes go through one application module, and that module is the **only** place in the codebase that calls the project-case decider — a static test counts the call sites and fails when a second appears. Wiring the external route straight into the decider would have turned every reviewer click into an audited external call; wiring it into a copy would have produced two deciders that agree until one is edited.

**The legacy reviewer route is unchanged.** It persists nothing, returns no decision identity, and its response shape is byte-compatible with what it always returned. A reviewer exercising a policy is not making an external commitment, and the audit trail should not fill with screen work.

**The external route is reserve → decide → finalise.** A case costs on the order of ten seconds of model time, and that single fact shapes the order:

1. **Reserve, and commit.** A `pending` receipt row is written and committed *before* the model is called. If the process dies mid-call, the evidence that the call was made survives. If the reservation cannot be written, no model call is made and the caller gets a non-2xx.
2. **Decide, holding no transaction.** The model call runs with nothing open.
3. **Finalise, in a short transaction.** `completed` with the full envelope and its hash, or `failed` with a reason and no outcome.

If finalisation fails, the caller is told so and is **not** given the verdict. There is no "here is your answer, but we could not save it" response: a verdict that cannot be cited later is precisely what this endpoint exists to stop shipping.

### Two records, two meanings

| Record | Written by | Holds |
|---|---|---|
| `evaluations` | `POST /api/evaluations` | A deterministic decision: structured facts in, per-rule determinations out, a `result_hash` that reproduces. The evaluator is a pure function — no database, no network, no model. |
| `policy_case_decisions` | `POST /api/policy-decisions/{project_key}/case` | A model-mediated case decision: prose in, a receipt out, with retrieval disclosure, citations and a `decision_hash` that seals content rather than promising reproduction. |

They are separate tables because generalising one over the other would be a lie rather than an abstraction: `Evaluation` requires a non-null policy version (a case can legitimately answer with none published), requires structured facts (a case has prose), and carries the XACML status enum (a case has its own seven-value vocabulary). Keeping them apart is what lets each state exactly what it is.

### Public identity

External routing is on the project's stable `key`. The UUID `id` is returned on every receipt as trace identity and is never routed on; the `name` is a display string and changes. A URL built from a display name would break the first time someone renamed a project, so a name in the path is a `404`.

Both decision operations additionally require a proved authenticated principal, resolved independently of the global `RBAC_ENABLED` flag — see [API](api.md#audited-external-decisions-policy-decisions) and [External consumption](external-consumption.md).

## Evaluation call, end to end

```mermaid
sequenceDiagram
    participant UI as Web app
    participant R as evaluations router
    participant Repo as Repositories
    participant M as mappers
    participant E as evaluator.engine
    participant DB as PostgreSQL

    UI->>R: POST /api/evaluations (facts, policy set, version pin)
    R->>Repo: resolve active or pinned version
    Repo->>DB: read approved rules
    R->>M: approved_policy_version_to_package(...)
    M-->>R: ApprovedPolicyPackage
    R->>E: evaluate_policy(package, request)
    Note over E: pure function — no DB, no network, no AI
    E-->>R: status, outcome, per-rule results,<br/>exceptions, advice, result hash
    R->>DB: append evaluation record
    R-->>UI: EvaluationResponse
```

The same `ApprovedPolicyPackage` mapper feeds the live evaluation endpoint, the policy-test executor and the on-publish test re-run, so all three share identical semantics.

## Frontend structure

`apps/web/src` is a single-page app with local state (no router library):

- `App.tsx` — the shell: sidebar navigation, health/AI status pills, the actor switcher, and the global Ask AI drawer.
- `api.ts` — one typed client for the whole backend surface.
- `ActorContext.tsx` — the "acting as" identity (name + role), persisted in `localStorage`. It is not authentication, but the backend does enforce `policy_manager` on manager-only endpoints.
- `components/` — pages and building blocks; `ProjectWorkspace.tsx` hosts the per-project tabs, and `RuleCard` / `ConditionView` / `PolicyInspector` render canonical rules and their condition trees.

See [Workflows](workflows.md) for what each screen does.

## Deployment shape

Local development continues to use `infra/local/docker-compose.yml` for PostgreSQL and separate API/Vite processes.

A deployment-ready Azure design now exists under `infra/` for future use with Bicep and `azd`. The recommended topology is a public React/Nginx Container App that reverse-proxies to an internal FastAPI Container App, all inside a VNet-integrated Container Apps environment. PostgreSQL uses its own delegated subnet; Key Vault, Azure Files, Azure OpenAI and Azure AI Search use a private endpoint subnet. Uploaded documents persist through an Azure Files mount at the existing `data/documents` path.

The initialization job creates a **fresh** PostgreSQL schema with Alembic and creates Search index definitions. It does not migrate local policy rows or files. See [Azure deployment](azure-deployment.md) and [deployment options](azure-deployment-options.md).

No Azure deployment was executed while preparing these assets. CI/CD remains outside this repository; a future operator invokes the documented `azd up` workflow interactively.
