# API

The backend is a FastAPI application: `policy_platform.api.app:app`. There is no `main.py`.

## Interactive API documentation

FastAPI generates and serves the OpenAPI description automatically. With the API running on port 8010:

| URL | What it is |
|---|---|
| <http://127.0.0.1:8010/docs> | Swagger UI — browse every endpoint, see request/response schemas, and send live requests with **Try it out**. |
| <http://127.0.0.1:8010/redoc> | ReDoc — a reference-style rendering of the same description. |
| <http://127.0.0.1:8010/openapi.json> | The raw OpenAPI document, for client generation or import into other tooling. |

Swagger UI is the fastest way to explore the API: pick a tag, expand an operation, and the exact schema for that request is right there. Treat the generated description as authoritative — this page only orients you. The description is generated from the same Pydantic contracts the evaluator consumes, so it cannot drift from the implementation.

The current surface is **92 paths / 103 operations** across 14 tags.

## Endpoint groups

All routes are prefixed with `/api`, except `GET /health`.

| Tag | Prefix | Operations | What it covers |
|---|---|---|---|
| `policy-sets` | `/api/policy-sets` | 19 | Projects: CRUD, portfolio and workspace counts, review scheduling, versions, exports, and policy-index health. |
| `candidate-rules` | `/api/policy-sets/{key}/candidate-rules` | 11 | The review queue, the same rules grouped by passage, and publication. |
| `ai` | `/api/ai` | 31 | Everything AI-assisted: extraction, grounded answers, rewrites, quality, correlation, and case testing. |
| `evaluations` | `/api/evaluations` | 3 | Run a deterministic evaluation, and browse the append-only decision log (list + detail). |
| `extraction` | `/api/extraction/{document_version_id}` | 4 | What a run actually saw: the canonical document, its structural graph, the reading plan, and element coverage. |
| `documents` | `/api/documents` | 4 | List documents, multipart upload, list a version's clauses, assign a document to a project. |
| `policy-tests` | `/api/policy-tests` | 10 | Saved tests: list, create, propose (AI), review a proposal, run now, run history, failing tests, and validation batches. |
| `policy-exceptions` | `/api/policy-exceptions` | 4 | Request a waiver, list, read, and grant/deny it. |
| `policy-attestations` | `/api/policy-attestations` | 4 | Launch an acknowledgement campaign, list, search, acknowledge. |
| `policy-review-requests` | `/api/policy-review-requests` | 5 | Viewer feedback on published versions: submit, list, acknowledge, resolve, withdraw. |
| `policy-payload` | `/api/policy-payload` | 1 | The lean projection of one policy for a model to read. |
| `notes` | `/api/notes` | 3 | Free-form notes attached to an entity. |
| `audit` | `/api/audit-events` | 1 | Read the immutable audit trail. |
| `system` | `/health`, `/api/auth/*` | 3 | Liveness, local sign-in, and resolved principal. |

The three largest groups carry more than a table cell can hold, so their detail is below rather than inside the row. `extraction` is read-only, and the fastest way to answer "why was this clause not extracted?".

### What `policy-sets` covers

Create, list, update and delete projects; portfolio summary and workspace counts; periodic-review marking; trusted extraction config; versions, version rules, version policies, provision history across versions, version export and the active version. It also reports whether a project's own policy index still represents the active published version, and rebuilds that index when a best-effort build after publishing did not complete.

### What `candidate-rules` covers

The review queue — draft, list, facets, edit, review, request-changes, override, bulk-review and export — plus `GET /api/policy-sets/{key}/policies`, which is the same rules grouped under the passage that stated them, and `POST /api/policy-sets/{key}/publish`.

### What `ai` covers

Status, ask, extract, extraction progress and runs, rewrite and apply, rewrite preview, draft-from-text, compare, policy-set summary, correlation runs, findings and dispositions, change explanation, generated subject names for a set's policies, generated handles for its rules and the lookup that serves them, and a plain-words reading of one policy's extracted record.

Three of its groups are worth stating precisely:

- **Scenario evaluation** is split by the route the rule takes, so a rule read by a judge and a rule computed by the engine are each put to the decider its route names.
- **Quality** covers published rules and candidates, each split into a `POST` that evaluates and a `GET` that reads the last result, plus history.
- **Case answering** works on one policy or a whole project. The project scope retrieves the policies bearing on the question from that project's own policy index and discards the rest before anything is evaluated — never the whole set. Both surfaces sort the question into an informational one, which the policy answers from what it states, or a determination assessed against the rules, and each is answered in its own right.

## Conventions

- **JSON in, JSON out**, except document upload (`multipart/form-data`) and export endpoints (which return JSON, JSONL or CSV as an attachment, selected with a `format` query parameter). See [Capabilities](../README.md#capabilities) for what each output is for.
- **Policy sets are addressed by `key`** — a stable slug such as `expense-policy` — while most other resources use UUIDs.
- **AI endpoints require configuration.** Azure OpenAI is a product requirement, not an option: if it is not configured, every AI route returns `503` before doing any work and the platform is in a degraded diagnostic mode. Retrieval- backed grounding additionally needs `AZURE_SEARCH_*`. Check `GET /api/ai/status` first — it reports both `ai_enabled` and `search_enabled`.
- **Role-based access control, off by default.** All 103 operations are classified into a capability band — read, use, author, administer — and one dependency enforces the whole registry, so a route cannot be reachable without a classification. It is disabled unless `RBAC_ENABLED` is set; see [configuration](configuration.md) for what to set up first. When enabled, an insufficient role gets `403` with a structured `detail` carrying `code`, `required_role` and `band` rather than a sentence, so clients can render their own wording. Note that the bands do not follow HTTP verbs: many `POST /api/ai/*` routes change nothing and are readable by any role, while a few that write nothing — the ones that exist to compose an edit — require an author.
- **Getting a token.** `POST /api/auth/login` with `{username, password}` returns `access_token`; send it as `Authorization: Bearer <token>`. `GET /api/auth/me` reports the principal the server resolved, which is the quickest way to see what a token is actually granting. Both are `read`-band, so a caller who has not signed in can reach them — an unauthenticated request resolves to the least privilege, which satisfies `read`. A wrong password and an unknown username both return `401`, deliberately indistinguishable.
- **`401` and `403` mean different things.** `401` is "this session is not valid" — the token is missing, expired or not verifiable. `403` is "your role may not do this". A client should clear its session on the first and explain the refusal on the second; merging them logs people out for asking to do something they were never allowed to do.
- **Manager-only operations.** `request-changes`, `override`, and creating an attestation campaign additionally require `actor_role: "policy_manager"` in the request body. This is the older, narrower check and is not a security boundary on its own; the capability layer above is what enforces access.
- **Append-only resources.** Evaluations, policy-test runs and audit events are read-only once written; published versions are never edited in place.
- **Deleting a project is the one destructive operation.** `DELETE /api/policy-sets/{key}` removes the project and everything scoped to it — documents, clauses, extraction runs, candidate rules, published versions, quality runs, notes and search-index entries. It requires `actor` and `confirm={key}`: echoing the name is the cheapest guard that a mistyped URL cannot satisfy by accident. It returns a body rather than `204`, because someone who has just removed hundreds of extracted rules should be told what went. The audit trail is deliberately **kept** — a `policy_set.deleted` event records that the project existed and who removed it, since erasing that is the opposite of governance. The `search_index` field reads `clean`, `skipped` or `orphaned` rather than a count, because the index is a separate service and a failure to clean it must be reported rather than hidden.

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

The AI-assisted path — check status, extract, inspect quality, bulk-approve, publish:

```powershell
curl.exe -s http://127.0.0.1:8010/api/ai/status

curl.exe -s -X POST http://127.0.0.1:8010/api/ai/policy-sets/<key>/documents/<document_version_id>/extract

curl.exe -s -X POST http://127.0.0.1:8010/api/ai/policy-sets/<key>/candidates/quality/runs

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

Request bodies differ per endpoint — use `/docs` for the exact shape rather than copying blindly.

## Client

The web app's typed client is `apps/web/src/api.ts`. It reads `VITE_API_BASE_URL` (default `http://localhost:8010`) and mirrors the backend contracts in TypeScript, so it doubles as a readable index of what the frontend consumes.
