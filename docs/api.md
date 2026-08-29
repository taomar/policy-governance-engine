# API

This page is for integrators and operators who need the public HTTP surface. The backend is a FastAPI application: `policy_platform.api.app:app`. There is no `main.py`.

## Interactive API documentation

FastAPI generates and serves the OpenAPI description automatically. With the API running on port 8010:

| URL | What it is |
|---|---|
| <http://127.0.0.1:8010/docs> | Swagger UI — browse every endpoint, see request/response schemas, and send live requests with **Try it out**. |
| <http://127.0.0.1:8010/redoc> | ReDoc — a reference-style rendering of the same description. |
| <http://127.0.0.1:8010/openapi.json> | The raw OpenAPI document, for client generation or import into other tooling. |

Swagger UI is the fastest way to explore the API: pick a tag, expand an operation, and the exact schema for that request is right there. Treat the generated description as authoritative — this page only orients you. The description is generated from the same Pydantic contracts the evaluator consumes, so it cannot drift from the implementation.

The current surface is **94 paths / 105 operations** across 15 tags.

### Where the API lives in a deployment

Locally the API is its own process on port 8010, and every example below uses that base. In the Azure topology the public FQDN is the **web** container app, whose nginx reverse-proxies `/api` to the API container; the API container itself stays internal and is not addressed directly. So an external integrator's base URL is the web FQDN — `https://<web-fqdn>` — and the paths on this page are unchanged beneath it. The receipt link a decision returns (`receipt_url`) is relative for the same reason: an absolute URL built server-side would name a host the caller never used.

## Endpoint groups

All routes are prefixed with `/api`, except `GET /health`.

| Tag | Prefix | Operations | What it covers |
|---|---|---|---|
| `policy-sets` | `/api/policy-sets` | 19 | Projects: CRUD, portfolio and workspace counts, review scheduling, versions, exports, and policy-index health. |
| `candidate-rules` | `/api/policy-sets/{key}/candidate-rules` | 11 | The review queue, the same rules grouped by passage, and publication. |
| `ai` | `/api/ai` | 31 | Everything AI-assisted: extraction, grounded answers, rewrites, quality, correlation, and case testing. |
| `policy-decisions` | `/api/policy-decisions` | 2 | The audited external contract: put a case to a project's published policies and receive a stored receipt, then read that receipt back by id. Authenticated. [Detail below](#audited-external-decisions-policy-decisions). |
| `evaluations` | `/api/evaluations` | 3 | Run a deterministic evaluation, and browse the append-only decision log (list + detail). |
| `extraction` | `/api/extraction/{document_version_id}` | 4 | What a run actually saw: the canonical document, its structural graph, the reading plan, and element coverage. |
| `documents` | `/api/documents` | 4 | List documents, multipart upload, list a version's clauses, assign a document to a project. Upload returns `clauses_search_indexed`, the count written to the search index. |
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

#### Cursor pagination on the candidate-rules list

`GET /api/policy-sets/{key}/candidate-rules` supports opt-in cursor pagination:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1–500) | absent | When present, return at most this many records and wrap the response in a `{ items, next_cursor, total }` envelope. When absent, the response is a bare JSON array (backward-compatible). |
| `cursor` | string | absent | Opaque cursor from a previous page's `next_cursor`. Ignored when `limit` is absent. A malformed cursor returns 422. |

**Response shape changes based on `limit`:** without `limit` the response is `CandidateRuleResponse[]`. With `limit` it is `{ items: CandidateRuleResponse[], next_cursor: string | null, total: int }`. This is a deliberate trade-off — a permanently-wrapped response would break every existing caller, while a parameter-gated shape lets new callers opt in.

Uses keyset pagination over `(created_at, id)` so that mutations (e.g. approving a rule) during a walk do not cause records to be skipped — unlike offset pagination, the cursor anchors to a fixed point in the ordered set.

### What `ai` covers

Status, ask, extract, extraction progress and runs, rewrite and apply, rewrite preview, draft-from-text, compare, policy-set summary, correlation runs, findings and dispositions, change explanation, generated subject names for a set's policies, generated handles for its rules and the lookup that serves them, and a plain-words reading of one policy's extracted record.

Three of its groups are worth stating precisely:

- **Scenario evaluation** is split by the route the rule takes, so a rule read by a judge and a rule computed by the engine are each put to the decider its route names.
- **Quality** covers published rules and candidates, each split into a `POST` that evaluates and a `GET` that reads the last result, plus history.
- **Case answering** works on one policy or a whole project. The project scope retrieves the policies bearing on the question from that project's own policy index and discards the rest before anything is evaluated — never the whole set. Both surfaces sort the question into an informational one, which the policy answers from what it states, or a determination assessed against the rules, and each is answered in its own right.

`POST /api/ai/policy-sets/{key}/case-answer` remains what it has always been: the in-product reviewer surface. It persists nothing, returns no decision identity, and its response shape is unchanged. When an external system needs a verdict it can cite later, use `policy-decisions` below instead.

## Audited external decisions (`policy-decisions`)

Two operations, and no others:

| Operation | What it does |
|---|---|
| `POST /api/policy-decisions/{project_key}/case` | Puts a case to a project's published policies, records a receipt, and returns it. |
| `GET /api/policy-decisions/{decision_id}` | Replays the stored receipt for one decision, byte-identical to what was returned. |

There is deliberately no list endpoint and no identity endpoint here. A caller composing a console already has `GET /api/policy-sets/{key}` and `GET /api/policy-sets/{key}/active-version`; a third read contract over the same data would be one more thing to keep in step with them.

For the integration-shaped view of this — what an agent, a Copilot extension or a workflow step actually needs — see [External consumption](external-consumption.md).

### `project_key` is the public identifier

Routing is on the project's stable `key`, the same slug used everywhere else in this API. Every receipt also returns the project's UUID `id` as **trace identity** and its `name` as a **display string**, and neither is ever routed on. A display name in the path is a `404`, and that is the point: a URL built from a name would break the day someone renamed the project.

### Authentication

Both operations depend on a valid authenticated principal — independently of the global `RBAC_ENABLED` flag. A deployment that has not enabled global enforcement still refuses these two routes to an unauthenticated caller with `401`, because a receipt that cannot name who asked for it is not a receipt. When global enforcement *is* on, the capability bands apply on top: the `POST` is `use`, the `GET` is `read`.

Two credentials establish that principal:

| Credential | Header | Use it when |
|---|---|---|
| Bearer token | `Authorization: Bearer <token>` | The caller is a person, or you need per-caller attribution, expiry, or revocation without a restart. |
| Subscription key | `X-Policy-Subscription-Key: <key>` | The caller is a non-interactive system and the deployment has set `POLICY_SUBSCRIPTION_KEY`. |

The key path does not exist until an operator configures it: with `POLICY_SUBSCRIPTION_KEY` blank the header is not read at all, and presenting one answers `401 subscription_key_rejected`. A key that is presented and wrong is also `401` and never falls through to an anonymous request. If a caller sends both a token and a key, a *valid* token decides — it names an individual, and the key names one shared system identity configured for the whole deployment. See [External consumption → authentication](external-consumption.md#authentication) for the operational limits, including that rotation means changing the value and restarting.

Receipt reads are additionally narrowed at the record: a receipt may be read by the caller who made the decision, or by a policy author or administrator. Anyone else gets `403` — the receipt carries the requester's own free-text scenario, so it is not readable by an unrelated viewer.

### Request body

```json
{
  "scenario": "A supplier in a sanctioned jurisdiction asks whether we may proceed with a 90-day payment term.",
  "provision_id": null,
  "reasoning_effort": "medium",
  "additional_instructions": "",
  "correlation_id": null,
  "calling_system_identity": "my-service"
}
```

| Field | Required | Meaning |
|---|---|---|
| `scenario` | yes | The case in natural language. Stored on the receipt so it shows the question it answered. |
| `provision_id` | no | Naming one policy bypasses retrieval and decides against that policy alone. Omitted, the case is put to the project and the policies bearing on it are retrieved. A `provision_id` naming a policy in another project is a `404`. |
| `reasoning_effort` | no (`medium`) | What the caller asked for. A deployment may reject it and the call is retried without it, so only the *request* is recorded — as `request.reasoning_effort_requested`. |
| `additional_instructions` | no (`""`) | Presentation guidance only. See [below](#additional_instructions-what-a-caller-may-steer). |
| `correlation_id` | no | May also travel as the `X-Correlation-Id` header. Sending both with different values is a `422`. |
| `calling_system_identity` | no | An unverified free-text label for the calling system. Recorded **beside**, never instead of, the authenticated principal. |

### Correlation and idempotency headers

| Header | Direction | Behaviour |
|---|---|---|
| `X-Correlation-Id` | request and response | Your own id for this call. Also accepted as the body's `correlation_id`; if both are sent they must match, or `422`. When neither is sent the server generates one. Echoed in the response body and in the response header on both operations — and on a replay it is the *stored* receipt's correlation id, because a replay is the same decision, not a new one. |
| `Idempotency-Key` | request only | Optional. Makes a retry safe. It is a header rather than a body field on purpose: it describes the delivery of the request, not the question being asked, and putting it in the body would make it part of the request hash it is compared against. |

The key is bound to the authenticated principal, the project, and a canonical hash of the request — which covers the scenario, the named policy, the reasoning effort **and** the normalised caller guidance. So:

- same key, same request, completed → the original receipt is replayed, same `decision_hash`, no second model call;
- same key, a different request → `409 idempotency_key_reused`;
- same key, first call still running → `409 decision_in_progress`;
- same key, first call failed → `409 decision_previously_failed`; a key is spent, and a retry needs a new one.

Without a key every call is a new decision. Two identical questions are two decisions, and this endpoint will not pretend otherwise: deduplicating by scenario alone would be wrong, because asking the same question twice is something people legitimately do.

A case takes on the order of ten seconds of model time. Allow for it in your client timeout, and use an idempotency key rather than a retry loop.

### Read `decision_status` before `decision.verdict`

A completed receipt does not imply a determination. `decision_status` sits at the top level, above `decision`, precisely so a client reads it first:

| `decision_status` | Meaning | Verdict? |
|---|---|---|
| `answered` | The rules were applied to the case and a determination was reached. | yes |
| `missing_required_facts` | The rules bear on the case but the facts needed to apply them were not supplied. | no |
| `not_settled_by_rules` | The evaluated rules do not settle the question. | no |
| `no_rule_bears` | The rules were read and none of them bears on the case. | no |
| `declined` | The decider declined to answer. | no |
| `failed` | The gather did not produce a usable answer. | no |
| `not_evaluated` | Retrieval produced no evaluation at all — the project may have published nothing, its policy index may not be built, or no published policy may bear on the question. | no |

`not_evaluated` is this layer's own status and is kept apart from every status the decider can return, so "nothing was evaluated" can never be read as "the policies were evaluated and said nothing". All seven are legitimate `200` responses carrying a full receipt. `decision.verdict` is an empty string for every status except `answered`.

### Retrieval narrows; it does not evaluate everything

In project scope the policies bearing on the question are retrieved from that project's own policy index and the rest are discarded **before** anything is evaluated. The receipt reports that narrowing in full: `retrieval` carries the status, method, budget and scan bounds and the counts; `considered` and `excluded` carry the policies themselves with their rank, score and discard reason. There is no mode in which the whole published set is put to a model — when a project has fewer published policies than the retention budget, retrieval reports that nothing needed setting aside rather than claiming a wider evaluation.

In single scope — when you name a `provision_id` — retrieval is bypassed and that policy alone is evaluated.

### Envelope

The response is `case_decision_v1`, named in `schema_version` so a consumer can pin it and reject a shape it was not written against.

| Field | What it carries |
|---|---|
| `schema_version` | `case_decision_v1`. |
| `decision_id`, `correlation_id`, `idempotency_key` | Identity of this call. `decision_id` is what `GET /api/policy-decisions/{decision_id}` takes. |
| `policy_set` | `{id, key, name}` — trace identity, routing key, display name. |
| `active_version` | `{version_id, version_number, effective_from, effective_to}`, or `null` when the project has published nothing. This is the version the decider itself loaded, not a re-read of "current" around a ten-second call. |
| `caller` | `principal_identity`, `principal_role`, `authentication_source`, the caller-declared `calling_system_identity`, and `channel`. The proved identity and the declared label are two fields on purpose. |
| `request` | `scenario`, `scenario_hash`, `additional_instructions`, `additional_instructions_hash`, `scope` (`project` or `single`), `requested_provision_id`, `reasoning_effort_requested`, `received_at`. |
| `decision_status` | The seven-value status above. Read it first. |
| `retrieval` | `status`, `method`, `policy_budget`, `policy_scan`, and the retrieved / considered / retained / discarded / untestable counts, plus a `reason`. |
| `considered`, `excluded` | Policy references: `provision_id`, `provision_key`, `heading_path`, `rules`, `retained`, `best_rank`, `best_score`, `discard_reason`, `reason`, `payload_url`. |
| `decision` | `intent`, `classification_reasoning`, `status`, `verdict`, `explanation`, `missing_required_facts`, `note`, `decider_route` (`informational` or `decision`). |
| `citations` | Per cited rule: `rule_id`, its `policy` reference, and `source` with `state` (`quoted`, `no_citation`, `unresolved`, `not_stored`), `text`, `page`, `section`. |
| `grounding` | The decider's own grounding report, including `fabricated_citations` — citations the fabrication guard refused. |
| `size` | `combined_chars`, `budget_chars`, `oversize` for the evaluated record against the one-pass budget. |
| `trace` | `prompt_version`, `instruction_profile`, `model_deployment`, `retrieval_method`, `index_name`, `index_version_id`. Every field is nullable and omitted when unknown. |
| `decision_hash`, `hash_basis` | The integrity seal and the rule it was taken under. |
| `receipt_url` | Relative path where this receipt is read back. |
| `decided_at`, `latency_ms` | When the decision completed, and how long it took. |

**No policy record is inlined.** Policies are large and already served byte-for-byte by `GET /api/policy-payload/{provision_id}`; every policy reference in a receipt carries that `payload_url` instead. A receipt that embedded the record would double the corpus into the audit log and go stale the moment the projection changed.

There is no "reasoning effort used" in `trace`. The gather silently drops that parameter and retries when a deployment rejects it, so the effort actually used is not knowable from here. What the caller asked for is knowable, and is reported as `request.reasoning_effort_requested`.

### `additional_instructions` — what a caller may steer

The field exists so an integration can show a user the guidance being sent and let them add to it. Maximum **2000 characters after whitespace normalisation**; longer is a `422`. Normalisation unifies line endings, collapses runs of blank lines and intra-line whitespace, and strips — so a byte-for-byte retry from a text area still matches its idempotency binding.

It shapes **the emphasis, length and format of the explanation, and nothing else.** It cannot change:

- which policies were retrieved or read — it never reaches the retrieval step at all, so it cannot steer which policies are considered;
- what any rule means, or the authority of the published policies;
- the `decision_status` or the verdict;
- the requirement to cite every rule the answer rests on;
- the prohibition on drawing on anything outside the published records.

Guidance asking for any of those is ignored for that part, and `decision.note` says so.

The normalised text is stored on the receipt, echoed back in `request.additional_instructions` so an integration can show exactly what was applied, bound into the idempotency request hash (so reusing a key with different guidance is a `409`, not a replay), and sealed by digest in `decision_hash`.

**The server's own instructions are never returned and are not caller-editable.** `trace.prompt_version` and `trace.instruction_profile` identify them instead — `instruction_profile` names the immutable server-side framing that caller guidance is applied under, and changes when that framing changes. It never contains prompt text. The asymmetry is the whole safety story of the field: what a caller can edit is theirs and is shown back to them, and what they cannot edit is named but not exposed.

### `decision_hash` — an integrity seal, not a determinism claim

`decision_hash` is a canonical SHA-256 over a **fixed, documented subset** of the receipt: `schema_version`, the project's routing key, the published version number, the scenario hash, the caller-guidance hash, the scope, the retrieval status, the considered policies by stable provision key with their retained/discarded state, the decision's status, verdict, explanation, missing facts, note and route, and each citation's rule id, source state and verbatim text.

Excluded, and why: `decision_id`, `correlation_id` and `idempotency_key` name the *call* rather than the decision; the project and version UUIDs are surrogate keys that differ between environments while the decision does not; `decided_at`, `received_at` and `latency_ms` mean a slower call did not decide something different; `receipt_url` is a routing detail; and the hash itself.

What it proves is that *this* receipt's decision-defining content has not been altered since it was written. It is **not** a replay or determinism guarantee: a language model is in the path, so the same scenario put twice to the same version may legitimately produce different prose and a different hash. `hash_basis` names the preimage rule so a future basis can be added without making an old hash ambiguous.

To verify a stored receipt, `GET /api/policy-decisions/{decision_id}` and compare the `decision_hash` you kept against the one served. The envelope is replayed from storage rather than rebuilt, so the comparison is a real check.

### Errors

`POST /api/policy-decisions/{project_key}/case`:

| Status | `code` | When |
|---|---|---|
| `401` | `authentication_required` | No authenticated caller. |
| `404` | `project_not_found` | Unknown project key. |
| `404` | `policy_not_in_project` | A `provision_id` naming a policy in another project. |
| `422` | `correlation_id_conflict` | The header and body correlation ids differ. |
| `422` | `correlation_id_too_long` | `X-Correlation-Id` or `correlation_id` longer than 200 characters. |
| `422` | `idempotency_key_too_long` | `Idempotency-Key` longer than 200 characters. |
| `422` | `calling_system_identity_too_long` | Longer than 200 characters. |
| `422` | `provision_id_too_long` | Longer than 200 characters. |
| `422` | `reasoning_effort_invalid` | Not one of `low`, `medium`, `high`. Refused rather than coerced, so the receipt cannot record an effort the call did not run at. |
| `422` | `reasoning_effort_too_long` | Longer than 20 characters. |
| `422` | `additional_instructions_too_long` | Guidance longer than 2000 characters after normalisation. |
| `422` | `invalid_request` | A malformed id or other rejected input. |
| `409` | `idempotency_key_reused` | The key was already used for a different request. |
| `409` | `decision_in_progress` | A decision for this key is still running. |
| `409` | `decision_previously_failed` | The decision for this key failed and carries no verdict. |
| `409` | `decision_reservation_conflict` | The receipt could not be reserved because a conflicting record exists. |
| `503` | `ai_unavailable` | Azure OpenAI is not configured, or the decider reported it unavailable. |
| `503` | `decision_receipt_unavailable` | The receipt could not be reserved — **no decision was attempted**. Retry. |
| `500` | `decision_failed` | The decider faulted; the receipt records the failure. |
| `500` | `decision_receipt_failed` | A decision was made and could **not** be stored. It carries the decision and correlation ids and deliberately carries no verdict — a verdict that cannot be cited later is exactly what this endpoint exists to stop shipping. Retry with a new `Idempotency-Key`. |

`GET /api/policy-decisions/{decision_id}`:

| Status | `code` | When |
|---|---|---|
| `401` | `authentication_required` | No authenticated caller. |
| `403` | `decision_not_readable` | Not the caller who made the decision, and not a policy author or administrator. |
| `404` | `decision_not_found` | No decision with that id. |
| `409` | `decision_in_progress` | The receipt is reserved but not yet completed. |
| `410` | *(the recorded failure code)* | The decision failed and has no verdict to serve. |

Error bodies follow this API's convention: FastAPI's `{"detail": ...}` with a structured object carrying `code`, `message` and, where one exists, `decision_id` and `correlation_id`.

### Examples

Both use `$POLICY_SUBSCRIPTION_KEY` from the environment. A bearer token works identically — send `Authorization: Bearer $POLICY_API_TOKEN` instead of the header below. Never put a live credential in a snippet, a URL, a log or a page.

```bash
curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/expense-policy/case" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $(uuidgen)" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "scenario": "A contractor submits a 180 EUR client dinner without an itemised receipt.",
    "reasoning_effort": "medium",
    "calling_system_identity": "expense-bot"
  }'
```

```python
import os
import uuid

import requests

BASE = os.environ["POLICY_API_BASE"]
PROJECT_KEY = "expense-policy"

response = requests.post(
    f"{BASE}/api/policy-decisions/{PROJECT_KEY}/case",
    headers={
        "X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"],
        "Content-Type": "application/json",
        "X-Correlation-Id": str(uuid.uuid4()),
        "Idempotency-Key": str(uuid.uuid4()),
    },
    json={
        "scenario": "A contractor submits a 180 EUR client dinner without an itemised receipt.",
        "reasoning_effort": "medium",
        "calling_system_identity": "expense-bot",
    },
    timeout=60,
)
response.raise_for_status()
decision = response.json()

# Read the status before the verdict. Only "answered" carries one.
if decision["decision_status"] == "answered":
    print(decision["decision"]["verdict"])
    for citation in decision["citations"]:
        print(citation["rule_id"], citation["source"].get("text"))
else:
    print("No verdict:", decision["decision_status"], "—", decision["decision"]["note"])

# Verify the receipt was stored, and stored unchanged.
stored = requests.get(
    f"{BASE}/api/policy-decisions/{decision['decision_id']}",
    headers={"X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"]},
    timeout=30,
)
stored.raise_for_status()
assert stored.json()["decision_hash"] == decision["decision_hash"]
```

Reading `decision["decision"]["verdict"]` without the status branch is the one mistake this envelope exists to prevent, so neither example does it.

## Conventions

- **JSON in, JSON out**, except document upload (`multipart/form-data`) and export endpoints (which return JSON, JSONL or CSV as an attachment, selected with a `format` query parameter). See [Capabilities](../README.md#capabilities) for what each output is for.
- **Policy sets are addressed by `key`** — a stable slug such as `expense-policy` — while most other resources use UUIDs. A project's UUID `id` is trace identity and its `name` is a display string; neither is ever a path segment.
- **AI endpoints require configuration.** Azure OpenAI is a product requirement, not an option: if it is not configured, every AI route returns `503` before doing any work and the platform is in a degraded diagnostic mode. Retrieval- backed grounding additionally needs `AZURE_SEARCH_*`. Check `GET /api/ai/status` first — it reports both `ai_enabled` and `search_enabled`.
- **Role-based access control, off by default.** All 105 operations are classified into a capability band — read, use, author, administer — and one dependency enforces the whole registry, so a route cannot be reachable without a classification. It is disabled unless `RBAC_ENABLED` is set; see [configuration](configuration.md) for what to set up first. When enabled, an insufficient role gets `403` with a structured `detail` carrying `code`, `required_role` and `band` rather than a sentence, so clients can render their own wording. Note that the bands do not follow HTTP verbs: many `POST /api/ai/*` routes change nothing and are readable by any role, while a few that write nothing — the ones that exist to compose an edit — require an author.
- **Two operations require authentication regardless of that flag.** `POST /api/policy-decisions/{project_key}/case` and `GET /api/policy-decisions/{decision_id}` refuse an unauthenticated caller with `401` even where global enforcement is off, because they write and serve an audited receipt that must name who asked. Nothing else bypasses the flag.
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
