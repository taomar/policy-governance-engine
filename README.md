# Enterprise Policy Formalization and Deterministic Policy Platform (Local Build)

Local-first implementation of the deterministic-evaluation core described in the
project spec (`Instructions for Claude Opus 5_*.md`), **plus** a real Azure
OpenAI + Azure AI Search integration layer for AI-assisted extraction, quality
review, rewrite suggestions, version comparison, and grounded chat. Canonical
policy contracts, a pure-Python deterministic evaluator, and PostgreSQL-backed
persistence form the trust boundary — **no LLM participates in the runtime
evaluation decision**; AI only assists with drafting/reviewing candidates that
still go through human approve/reject/publish.

See `AGENT_PROGRESS.md` for the full milestone log, `docs/adr/` for architecture
decisions (`ADR-0007` covers the AI integration in detail), and
`docs/known-limitations.md` for what is intentionally deferred (MAF graph
workflows, real auth, CSV export, multi-tenant scoping).

## Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2.
- **AI**: Azure OpenAI (`gpt-5.6-sol` reasoning deployment for extraction/
  quality/rewrite/compare, `gpt-5.4-mini` fast deployment for interactive
  chat) + Azure AI Search, via thin `httpx` REST clients (no SDK dependency —
  see ADR-0007). Fully optional: unset the `AZURE_OPENAI_*` / `AZURE_SEARCH_*`
  variables in `.env` and the platform runs with AI features disabled.
- **Frontend**: React + TypeScript, Vite.
- **Database**: PostgreSQL 16 (Docker), local port **5433** (non-default —
  5432 was already in use by an unrelated container on this machine).
- **API port**: **8010** (non-default — 8000 was already in use by an
  unrelated local process).
- **Frontend dev port**: Vite defaults to 5173; if that's occupied by another
  project on your machine, Vite falls back to **5174** (confirmed locally —
  check the terminal output for the actual port Vite printed on startup).

## Prerequisites

- Docker Desktop
- Python 3.11+ and `pip`
- Node.js 18+ and `npm`

## First-time setup

```powershell
# 1. Copy env template (already pre-filled for local dev; edit if needed)
Copy-Item .env.example .env   # skip if .env already exists

# 2. Start PostgreSQL
docker compose -f infra/local/docker-compose.yml up -d

# 3. Create and activate a Python virtualenv, install the backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 4. Apply database migrations
.\.venv\Scripts\python.exe -m alembic upgrade head

# 5. Install frontend dependencies
cd apps\web
npm install
cd ..\..
```

## Running

Start the API (from repo root, with the venv available):

```powershell
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010 --app-dir src
```

Start the frontend (separate terminal):

```powershell
cd apps\web
npm run dev
```

Open the printed local URL (Vite prints the actual port on startup — usually
`5173`, or `5174`/higher if another project's dev server already holds 5173
on your machine). The UI is a sidebar-nav admin shell with seven sections
plus a global **Ask AI** chat drawer:

1. **Dashboard** — summary cards (policy set count, active versions, pending
   candidate rules, uploaded documents) aggregated live from the API, with
   quick-link buttons into each section.
2. **Policy Sets** — card-grid list of policy sets → click into a detail view
   → expandable version-history timeline → each version expands into readable
   **rule cards** (title, rule-type/effect badges, authority, effective dates,
   priority, a recursively-rendered condition tree with operator symbols like
   `>`/`≥`/`in` instead of raw JSON, required-fact chips, exceptions, scope).
   A collapsible "+ New Policy Set" form and a collapsible "+ Import Version
   (Advanced/Bulk)" JSON form (paste a canonical rules array to import
   directly as an approved version — a fast-path for bulk/bootstrap imports,
   bypassing individual review) remain available as secondary flows.
3. **Documents** — real multipart file upload (title/owner/PDF or DOCX) wired
   to the document-ingestion endpoint, plus a list of uploaded documents with
   a version-history table per document (uploading a new file under an
   existing title adds a new version, e.g. tracking v3.2 → v3.3 revisions).
   Each document version has an **✨ Extract with AI** button that runs Azure
   OpenAI extraction against the document and drops the results into the
   Review Queue as `candidate` rows — nothing is auto-published.
4. **Review Queue** — a policy-set selector, a structured candidate-drafting
   form (dropdowns for rule type/effect, plain inputs for title/authority/
   priority/dates, a row-based "AND of comparisons" condition builder, with
   an "Advanced JSON" checkbox escape hatch for OR/NOT/nested logic), a
   status-filterable candidate list rendered as rule cards with approve/reject
   actions (reviewer name required), **checkbox-based bulk select** ("select
   all N in this filter" + bulk approve/reject buttons — needed once AI
   extraction produces hundreds of candidates from one document), a
   per-candidate **✨ Suggest Rewrite** action (give the AI a plain-English
   instruction, e.g. "name concrete tribunals instead of 'appropriate legal
   body'", review the suggested payload, apply or discard it), and a publish
   panel that merges all approved-but-unpublished candidates into a
   brand-new approved version. Publishing always carries forward every rule
   from the current active version (versions are full immutable snapshots,
   not deltas).
5. **Quality** — runs deterministic checks (duplicate IDs, ambiguity,
   conflicting effects, expired rules, review backlog) plus an AI review pass,
   with a toggle between two scopes: **Published version** (evaluates the
   active approved version) and **Extracted candidates (pre-publish)**
   (evaluates unpublished `CandidateRule` rows directly — the way to answer
   "are these 400 freshly-extracted candidates any good?" *before* deciding
   what to approve/publish). Findings are filterable by severity and source
   (deterministic vs. AI review) and each carries a concrete recommendation.
6. **Compare** — pick two published versions of a policy set; get a
   rule-level diff (added/removed/changed/unchanged, each expandable) plus an
   AI-generated plain-English narrative summarizing what changed and why it
   matters.
7. **Evaluate** — policy-set + version selector (active or a specific pinned
   version), a facts form **dynamically generated** from the union of
   `required_facts` across the target version's rules (with an "Advanced JSON
   facts" checkbox escape hatch), and a result view: overall status, outcome,
   result hash, triggered exceptions, and a per-rule status/effect breakdown
   table.

**✨ Ask AI** (top-right drawer, available from any page) — a grounded chat:
scope a question to one policy set or "All policy sets," ask in plain
English ("What is the P1 support response time?"), and get an answer that
cites the specific source clauses it's grounded in. Uses the fast
(`gpt-5.4-mini`) deployment for lower latency.

Sample fixtures are in `samples/policies/` and `samples/evaluation-requests/`
and can be used directly via curl, e.g.:

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

A second, larger sample policy set — **`hardware-provisioning-policy`** — is
sourced from two real DOCX policy documents (copied into
`samples/source-documents/`; see `scripts/generate_hardware_policy_samples.py`
for the extraction/authoring script). It has 10 rules across two versions
(v3.2/v3.3) that differ in a real, meaningful way (contractor permanent-device
entitlement threshold: 20 vs 10 working days), useful for exercising
version-pinned evaluation (`use_active_version: false`) against a policy that
actually changed between versions:

```powershell
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets `
  -H "Content-Type: application/json" `
  --data-binary "@samples/policies/hardware-provisioning-policy-set.json"

curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/hardware-provisioning-policy/versions `
  -H "Content-Type: application/json" `
  --data-binary "@samples/policies/hardware-policy-v3.2-import.json"

curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/hardware-provisioning-policy/versions `
  -H "Content-Type: application/json" `
  --data-binary "@samples/policies/hardware-policy-v3.3-import.json"
```

## AI features (Azure OpenAI + Azure AI Search)

AI features are configured entirely via `.env` — `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (reasoning model, used for
extraction/quality/rewrite/compare), `AZURE_OPENAI_FAST_DEPLOYMENT` (used for
Ask AI chat), `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`/`_MODEL`/`_DIMENSIONS`,
`AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, `AZURE_SEARCH_API_VERSION`.
Leave them unset/blank to run with AI disabled — every AI endpoint checks
`GET /api/ai/status` internally and returns a clean error instead of crashing.
See ADR-0007 (`docs/adr/ADR-0007-ai-integration.md`) for the full design
rationale, including why direct `httpx` REST calls are used instead of the
official SDKs, and the reasoning-model token-budget gotcha.

```powershell
# Check whether AI is enabled and which deployments are configured
curl.exe -s http://127.0.0.1:8010/api/ai/status

# Extract candidate rules from an uploaded document version
curl.exe -s -X POST http://127.0.0.1:8010/api/ai/policy-sets/hr-guide-policy/documents/<document_version_id>/extract

# Evaluate quality of the currently PUBLISHED active version
curl.exe -s http://127.0.0.1:8010/api/ai/policy-sets/hr-guide-policy/quality

# Evaluate quality of unpublished candidates BEFORE deciding what to approve
curl.exe -s http://127.0.0.1:8010/api/ai/policy-sets/hr-guide-policy/candidates/quality

# Bulk-approve a batch of reviewed candidates (empty candidate_ids = all pending)
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/hr-guide-policy/candidate-rules/bulk-review `
  -H "Content-Type: application/json" `
  --data-binary "{`"candidate_ids`":[],`"decision`":`"approve`",`"reviewer`":`"me`"}"

# Suggest + apply an AI rewrite for one candidate
curl.exe -s -X POST http://127.0.0.1:8010/api/ai/candidate-rules/<candidate_id>/rewrite `
  -H "Content-Type: application/json" `
  --data-binary "{`"instruction`":`"Name concrete tribunals instead of vague wording`"}"

# Compare two published versions with an AI narrative summary
curl.exe -s "http://127.0.0.1:8010/api/ai/policy-sets/hardware-provisioning-policy/compare?version_a=1&version_b=3"

# Ask a grounded question (omit policy_set_key to search across all policy sets)
curl.exe -s -X POST http://127.0.0.1:8010/api/ai/ask `
  -H "Content-Type: application/json" `
  --data-binary "{`"question`":`"What is the P1 support response time?`",`"policy_set_key`":`"hardware-provisioning-policy`"}"
```

## Policy tests (Section 21.6 / 9.11 step 6)

Named, saved test cases for a policy set — distinct from the ad hoc **Evaluate**
page (Section 9.12), which is unsaved and exploratory. Azure OpenAI *proposes*
tests; the real deterministic evaluator always *executes* them and decides
pass/fail. Every active test is automatically re-run whenever a new version is
published, and any that fail appear in the Quality page's "Failed policy tests"
section. See ADR-0010 (`docs/adr/ADR-0010-policy-tests.md`).

AI-proposed tests start as `pending_review` and must be accepted before they run
on publish or count as findings; manually-created tests are active immediately.

```powershell
# List tests for a policy set (each item = the test + its latest run)
curl.exe -s http://127.0.0.1:8010/api/policy-tests/policy-sets/expense-policy

# Ask Azure OpenAI to propose tests across the applicable kinds
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-tests/policy-sets/expense-policy/propose `
  -H "Content-Type: application/json" `
  --data-binary "{`"reasoning_effort`":`"medium`"}"

# Accept (activate) or reject an AI-proposed test
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-tests/<test_id>/review `
  -H "Content-Type: application/json" `
  --data-binary "{`"decision`":`"accept`",`"reviewer`":`"me`"}"

# Run one test on demand against the active published version
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-tests/<test_id>/run `
  -H "Content-Type: application/json" --data-binary "{`"triggered_by`":`"me`"}"

# Immutable run history for one test (newest first)
curl.exe -s http://127.0.0.1:8010/api/policy-tests/<test_id>/runs

# Active tests whose most recent run did not pass (drives the Quality page)
curl.exe -s http://127.0.0.1:8010/api/policy-tests/policy-sets/expense-policy/failing
```

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -v
```

99 unit tests cover condition evaluation semantics, rule precedence ordering,
canonical hashing/determinism, the full evaluation engine (missing facts,
exceptions, authority precedence), and policy-test pass/fail assertion logic.

```powershell
cd apps\web
npm run build
```

Verifies the frontend type-checks and builds cleanly.

## Project layout

```
src/policy_platform/
  contracts/       canonical policy schema, condition AST, evaluation DTOs (Pydantic v2)
  evaluator/        pure-Python deterministic evaluation engine (zero I/O, zero AI/network)
                    engine.py: rule evaluation; test_runner.py: PolicyTest pass/fail assertions
  domain/           SQLAlchemy ORM entities (19 tables)
  infrastructure/   async engine/session, mappers, repositories, settings
    ai/             thin httpx Azure OpenAI REST client (openai_client.py)
    search/         thin httpx Azure AI Search REST client + indexing scoping strategy
    ai_extraction.py  document -> CandidateRule draft extraction
    ai_quality.py     deterministic + AI-review quality checks (published version AND pre-publish candidates)
    ai_rewrite.py     targeted AI rewrite suggestion + apply
    ai_compare.py     version-to-version rule diff + AI narrative summary
    ai_chat.py        grounded Ask-AI chat
    ai_test_proposal.py  AI-proposed PolicyTest cases (proposal only — never executes)
    policy_test_execution.py  runs a saved PolicyTest via the real evaluator, records a run
  api/              FastAPI app + routers (policy-sets, evaluations, documents, candidate-rules, policy-tests, ai)
  worker/           reserved for future MAF Python SDK workflow integration
apps/web/           React + TypeScript frontend (Vite)
alembic/            database migrations
samples/            sample policy set / approved version / evaluation request fixtures
  source-documents/ copies of real attached policy documents used as extraction sources
scripts/            one-off utility scripts (e.g. hardware-policy sample generator)
tests/unit/         pytest suite for the evaluator
docs/adr/           architecture decision records (ADR-0007: AI integration; ADR-0010: policy tests)
infra/local/        docker-compose for local PostgreSQL
```
