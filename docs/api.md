# API

The backend is a FastAPI application: `policy_platform.api.app:app`. There is no
`main.py`.

## Interactive API documentation

FastAPI generates and serves the OpenAPI description automatically. With the API
running on port 8010:

| URL | What it is |
|---|---|
| <http://127.0.0.1:8010/docs> | Swagger UI — browse every endpoint, see request/response schemas, and send live requests with **Try it out**. |
| <http://127.0.0.1:8010/redoc> | ReDoc — a reference-style rendering of the same description. |
| <http://127.0.0.1:8010/openapi.json> | The raw OpenAPI document, for client generation or import into other tooling. |

Swagger UI is the fastest way to explore the API: pick a tag, expand an
operation, and the exact schema for that request is right there. Treat the
generated description as authoritative — this page only orients you. The
description is generated from the same Pydantic contracts the evaluator consumes,
so it cannot drift from the implementation.

The current surface is **73 paths / 84 operations** across 11 tags.

## Endpoint groups

All routes are prefixed with `/api`, except `GET /health`.

| Tag | Prefix | Operations | What it covers |
|---|---|---|---|
| `policy-sets` | `/api/policy-sets` | 22 | Projects (policy sets): create, list, update, portfolio summary, workspace counts, periodic-review marking, trusted extraction config, versions, version rules, version export, active version, and aggregate limits (list/create/update/delete/propose/preview/eligibility). |
| `candidate-rules` | `/api/policy-sets/{key}/candidate-rules` | 10 | The review queue: draft, list, facets, edit, review, request-changes, override, bulk-review, export — plus `POST /api/policy-sets/{key}/publish`. |
| `ai` | `/api/ai` | 22 | Everything AI-assisted: status, ask, extract, extraction progress and runs, rewrite (+apply), rewrite preview, draft-from-text, scenario evaluation, compare, quality (published + candidates + history), policy-set summary, correlation runs/findings/dispositions, change explanation. |
| `evaluations` | `/api/evaluations` | 3 | Run a deterministic evaluation, and browse the append-only decision log (list + detail). |
| `documents` | `/api/documents` | 4 | List documents, multipart upload, list a version's clauses, assign a document to a project. |
| `policy-tests` | `/api/policy-tests` | 10 | Saved tests: list, create, propose (AI), review a proposal, run now, run history, failing tests, and validation batches. |
| `policy-exceptions` | `/api/policy-exceptions` | 4 | Request a waiver, list, read, and grant/deny it. |
| `policy-attestations` | `/api/policy-attestations` | 4 | Launch an acknowledgement campaign, list, search, acknowledge. |
| `notes` | `/api/notes` | 3 | Free-form notes attached to an entity. |
| `audit` | `/api/audit-events` | 1 | Read the immutable audit trail. |
| `system` | `/health` | 1 | Liveness plus the configured environment name. |

## Conventions

- **JSON in, JSON out**, except document upload (`multipart/form-data`) and
  export endpoints (which return JSON, JSONL or CSV as an attachment, selected
  with a `format` query parameter). See
  [Outputs and how to use them](../README.md#outputs-and-how-to-use-them) for
  what each output is for.
- **Policy sets are addressed by `key`** — a stable slug such as
  `expense-policy` — while most other resources use UUIDs.
- **AI endpoints require configuration.** Azure OpenAI is a product requirement,
  not an option: if it is not configured, every AI route returns `503` before
  doing any work and the platform is in a degraded diagnostic mode. Retrieval-
  backed grounding additionally needs `AZURE_SEARCH_*`. Check
  `GET /api/ai/status` first — it reports both `ai_enabled` and `search_enabled`.
- **Manager-only operations.** `request-changes`, `override`, and creating an
  attestation campaign require `actor_role: "policy_manager"` in the request body
  and return `403` otherwise. This is a lightweight local-trust boundary, not
  authentication.
- **Append-only resources.** Evaluations, policy-test runs and audit events are
  read-only once written; published versions are never edited in place.

## Common sequences

Create a policy set, import a version, and evaluate against it:

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

The AI-assisted path — check status, extract, inspect quality, bulk-approve,
publish:

```powershell
curl.exe -s http://127.0.0.1:8010/api/ai/status

curl.exe -s -X POST http://127.0.0.1:8010/api/ai/policy-sets/<key>/documents/<document_version_id>/extract

curl.exe -s http://127.0.0.1:8010/api/ai/policy-sets/<key>/candidates/quality

curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/<key>/candidate-rules/bulk-review `
  -H "Content-Type: application/json" `
  --data-binary "{`"candidate_ids`":[],`"decision`":`"approve`",`"reviewer`":`"me`"}"

curl.exe -s -X POST http://127.0.0.1:8010/api/policy-sets/<key>/publish `
  -H "Content-Type: application/json" --data-binary "{}"
```

Saved policy tests:

```powershell
curl.exe -s http://127.0.0.1:8010/api/policy-tests/policy-sets/<key>
curl.exe -s -X POST http://127.0.0.1:8010/api/policy-tests/policy-sets/<key>/propose `
  -H "Content-Type: application/json" --data-binary "{`"reasoning_effort`":`"medium`"}"
curl.exe -s http://127.0.0.1:8010/api/policy-tests/policy-sets/<key>/failing
```

Request bodies differ per endpoint — use `/docs` for the exact shape rather than
copying blindly.

## Client

The web app's typed client is `apps/web/src/api.ts`. It reads
`VITE_API_BASE_URL` (default `http://localhost:8010`) and mirrors the backend
contracts in TypeScript, so it doubles as a readable index of what the frontend
consumes.
