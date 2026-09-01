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

The current surface is **97 paths / 108 operations** across 15 tags.

### Where the API lives in a deployment

Locally the API is its own process on port 8010, and every example below uses that base. In the Azure topology the public FQDN is the **web** container app, whose nginx reverse-proxies `/api` to the API container; the API container itself stays internal and is not addressed directly. So an external integrator's base URL is the web FQDN — `https://<web-fqdn>` — and the paths on this page are unchanged beneath it. The receipt link a decision returns (`receipt_url`) is relative for the same reason: an absolute URL built server-side would name a host the caller never used.

## Endpoint groups

All routes are prefixed with `/api`, except `GET /health`.

| Tag | Prefix | Operations | What it covers |
|---|---|---|---|
| `policy-sets` | `/api/policy-sets` | 20 | Projects: CRUD, portfolio and workspace counts, review scheduling, versions, exports, and policy-index health. |
| `candidate-rules` | `/api/policy-sets/{key}/candidate-rules` | 11 | The review queue, the same rules grouped by passage, and publication. |
| `ai` | `/api/ai` | 31 | Everything AI-assisted: extraction, grounded answers, rewrites, quality, correlation, and case testing. |
| `policy-decisions` | `/api/policy-decisions` | 4 | External consumption: full or compact audited decisions, precision-ranked policy JSON, and receipt replay. Authenticated. [Detail below](#audited-external-decisions-policy-decisions). |
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
- **Case answering** works on one policy or a whole project. The project scope retrieves the policies bearing on the question from that project's own policy index and discards the rest before anything is evaluated — never the whole set. A question is read as asking for what the policies *state*, for a *verdict* on the case, or for both, and each requested answer is gathered in its own right over the same retrieved policies.

`POST /api/ai/policy-sets/{key}/case-answer` remains what it has always been: the in-product reviewer surface. It persists nothing, returns no decision identity, and its response keys are unchanged — `intent`, `informational` and `decision` all still mean what they meant, with `information_requested`, `verdict_requested` and `classifier_version` added beside them. When an external system needs a verdict it can cite later, use `policy-decisions` below instead.

## Audited external decisions (`policy-decisions`)

Four operations:

| Operation | What it does |
|---|---|
| `POST /api/policy-decisions/{project_key}/policies` | Semantically precision-ranks published policies, applies rule-level narrowing inside selected large policies, and returns their `grounding_projection_v1` records without classification, adjudication, or a receipt. |
| `POST /api/policy-decisions/{project_key}/case` | Puts a case to a project's published policies, records a receipt, and returns it. |
| `POST /api/policy-decisions/{project_key}/case/light` | Runs and stores the same decision as `/case`, then returns the compact `case_decision_light_v1` projection. |
| `GET /api/policy-decisions/{decision_id}` | Replays the stored receipt for one decision. **Content-equivalent**, not byte-identical: every field carries the value it was written with, and `decision_hash` verifies against the replayed content, but JSON key order may differ from the original response. Compare receipts by `decision_hash` or by parsed value, never by string. |

The receipt is `case_decision_v2`. A case is answered as **two independent tracks** — what the policies state, and what the case comes to — because a single question can ask for either or both. See [A case asks for information, a verdict, or both](#a-case-asks-for-information-a-verdict-or-both).

There is deliberately no list endpoint and no identity endpoint here. A caller composing a console already has `GET /api/policy-sets/{key}` and `GET /api/policy-sets/{key}/active-version`; a third read contract over the same data would be one more thing to keep in step with them.

For the integration-shaped view of this — what an agent, a Copilot extension or a workflow step actually needs — see [External consumption](external-consumption.md).

### Retrieval-only response

`POST /api/policy-decisions/{project_key}/policies` takes:

```json
{ "scenario": "Describe the situation whose governing policies you need." }
```

It returns `policy_retrieval_v1`: `policy_set`, the exact `active_version`, the original query and language-boundary provenance, retrieval disclosure, `policies`, service-reported `token_usage`, end-to-end `latency_ms`, and an optional `stage_latency_ms` breakdown of that time. Policy documents are semantically reranked and cut at the largest meaningful adjacent score gap; when there is no such gap, at most three remain. Each entry contains its stable identity, semantic rank/score and optional `rule_selection`, plus the selected `grounding_projection_v1` payload. Large policies contain only the rules named by `rule_selection`; the 15-rule ceiling remains unchanged. `precision_mode`, `semantic_candidates`, `semantic_selected`, `semantic_largest_gap`, and `semantic_cutoff_score` disclose the cut.

No classifier, plan, verdict gather, explanation renderer, decision hash, or receipt write runs on this route. `Idempotency-Key`, `reasoning_effort`, `calling_system_identity`, and `additional_instructions` therefore do not belong in this request. It also skips the decision path's own embedding call and the rule-document query.

It is **not**, however, a model-free route: the question still crosses the inbound language boundary before retrieval, even when it is already English. The returned policy records do not pass through the outbound prose renderer; they are served as selected, and their evidence text remains exactly as stored. Retrieval is cheaper than a decision, but it is not free, and `token_usage` reflects the inbound boundary call.

### Decision Light response

`POST /api/policy-decisions/{project_key}/case/light` accepts the same request and headers as `/case`. It executes the same single decision path and stores the full `case_decision_v2` receipt; only the immediate response is projected to `case_decision_light_v1`. The `decision_id`, `decision_hash`, `hash_basis`, and `receipt_url` identify that full receipt, so a caller can start compact and fetch the complete audit record later.

The fixed light schema contains:

```json
{
  "schema_version": "case_decision_light_v1",
  "response_type": "informational | decision | mixed | not_evaluated",
  "decision_id": "…",
  "correlation_id": "…",
  "idempotency_key": "…",
  "policy_set": { "id": "…", "key": "…", "name": "…" },
  "active_version": { "version_id": "…", "version_number": 1 },
  "request": { "scenario": "…", "scenario_hash": "…" },
  "asked": {
    "information_requested": false,
    "verdict_requested": true,
    "classifier_version": "ai-case-needs-v2"
  },
  "outcome": { "information": "not_requested", "verdict": "answered" },
  "information": null,
  "verdict": {
    "status": "answered",
    "reached": true,
    "decision": "…",
    "explanation": "…",
    "missing_information": [],
    "verification_requirements": [],
    "note": ""
  },
  "retrieval": {
    "status": "narrowed",
    "method": "direct_policy_rrf_elbow_rule_rescue_v1",
    "policies_retained": 1,
    "rule_rescued_policies": 0,
    "reason": null
  },
  "policies": [
    { "provision_id": "…", "provision_key": "…", "heading_path": ["…"] }
  ],
  "citations": [
    {
      "rule_id": "…",
      "policy": { "provision_id": "…", "provision_key": "…", "heading_path": ["…"] },
      "source": { "state": "quoted", "text": "…", "page": 1, "section": "…" },
      "serves": ["verdict"]
    }
  ],
  "trace": {
    "classifier_version": "…",
    "prompt_version": "…",
    "plan_profile": "…",
    "selector_catalogue_version": "…",
    "model_deployment": "…",
    "token_usage": {
      "calls": 6,
      "calls_without_usage": 0,
      "prompt_tokens": 21500,
      "completion_tokens": 1800,
      "total_tokens": 23300,
      "reasoning_tokens": 900
    },
    "stage_latency_ms": {
      "embedding": 1414,
      "retrieval_discovery_wall": 1740,
      "gather_wall": 18500
    }
  },
  "decision_hash": "…",
  "hash_basis": "case_decision_v2_lang_verification",
  "receipt_url": "/api/policy-decisions/…",
  "latency_ms": 24500
}
```

That example uses the repository's own contract helpers. A client that does not depend on this package must reproduce the documented preimage for the receipt's `hash_basis`; merely comparing the stored `decision_hash` with a previously kept hash checks identity, not whether the current fields still recompute to that seal.

Fields intentionally omitted from Decision Light: caller details, full retrieval counters, considered/excluded candidates, payload size, language-transport internals, grounding counters, duplicate section-level citations, and timestamps. It retains total `latency_ms`, per-stage `stage_latency_ms`, and service-reported `token_usage` for operational diagnosis. Usage figures remain `null` rather than estimated when no call reported them; when `calls_without_usage` is nonzero beside a numeric total, that total is a lower bound over the calls that did report usage. These fields are execution metadata, are not part of `decision_hash`, and may be absent on historical receipts. The full receipt remains authoritative and available at `receipt_url`.

### `project_key` is the public identifier

Routing is on the project's stable `key`, the same slug used everywhere else in this API. Every receipt also returns the project's UUID `id` as **trace identity** and its `name` as a **display string**, and neither is ever routed on. A display name in the path is a `404`, and that is the point: a URL built from a name would break the day someone renamed the project.

### Authentication

All four operations depend on a valid authenticated principal — independently of the global `RBAC_ENABLED` flag. A deployment that has not enabled global enforcement still refuses them to an unauthenticated caller with `401`: retrieval exposes filtered published policy JSON, and a receipt must name who asked. When global enforcement *is* on, the three `POST` operations are `use`, and the `GET` is `read`.

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
| `additional_instructions` | no (`""`) | Presentation guidance only. See [below](#additional_instructions--what-a-caller-may-steer). |
| `correlation_id` | no | May also travel as the `X-Correlation-Id` header. Sending both with different values is a `422`. |
| `calling_system_identity` | no | An unverified free-text label for the calling system. Recorded **beside**, never instead of, the authenticated principal. |

**`reasoning_effort` is the one request field that materially affects how long a decision takes.** A decision's wall-clock time is dominated by how much the model *reasons*, not by how much policy text was retrieved — a request with a small retrieved corpus and deep reasoning is slower than one with a large corpus and shallow reasoning. Lowering the effort trades adjudication depth for speed, and is a real trade rather than a free win: validate it against your own scenarios before adopting it. Everything else a caller can send — a shorter scenario, narrower guidance, a named `provision_id` — changes what is read and what it costs in tokens, not how long the reasoning takes.

### Correlation and idempotency headers

| Header | Direction | Behaviour |
|---|---|---|
| `X-Correlation-Id` | request and response | Your own id for this call. Also accepted as the body's `correlation_id`; if both are sent they must match, or `422`. When neither is sent the server generates one. Both `POST` responses echo it in the body and header; a receipt replay echoes the *stored* receipt's correlation id, because a replay is the same decision, not a new one. |
| `Idempotency-Key` | request only | Optional. Makes a retry safe. It is a header rather than a body field on purpose: it describes the delivery of the request, not the question being asked, and putting it in the body would make it part of the request hash it is compared against. |

The key is bound to the authenticated principal, the project, and a canonical hash of the request — which covers the scenario, the named policy, the reasoning effort **and** the normalised caller guidance. So:

- same key, same request, completed → the original receipt is replayed, same `decision_hash`, no second model call;
- same key, a different request → `409 idempotency_key_reused`;
- same key, a `pending` receipt exists → `409 decision_in_progress`; this normally means the first call is running, but the state is not a heartbeat and can be orphaned by a process failure;
- same key, first call failed → `409 decision_previously_failed`; a key is spent, and a retry needs a new one.

Without a key every call is a new decision. Two identical questions are two decisions, and this endpoint will not pretend otherwise: deduplicating by scenario alone would be wrong, because asking the same question twice is something people legitimately do.

A case is a multi-call model operation and takes **tens of seconds**, not a few. Across the evaluation matrices run against the current release, observed end-to-end times sat around **p50 22–32 s and p95 39–45 s**, with individual calls above that. The spread between matrices reflects the scenarios in them, not which operation was called: `/case/light` runs the same adjudication as `/case` and is not faster. Size a client timeout from the p95 end of that range with headroom — 120 s is a reasonable default — and use an `Idempotency-Key` rather than a retry loop. See [Timing and token telemetry](#timing-and-token-telemetry) for what the response reports about its own execution, and [Timeouts and recovery](external-consumption.md#timeouts-and-recovery) for what to do when a call does not return.

These figures are observations from a fixed set of evaluation scenarios, not a service level objective. No latency guarantee is made.

### A case asks for information, a verdict, or both

Your question is read as **two independent requests**, by one classifier call:

- **information** — what the retained published policies *state* on the subject;
- **verdict** — how the case *comes out* under them.

A question can ask for either or both. "What is the overtime limit?" is information-only. "Was my Tuesday shift allowed?" is verdict-only. "What is the limit, and was Tuesday within it?" asks for both, and both are gathered — over the same retrieved policies, concurrently.

**There is no request field for this.** Intent detection is the server's, because a caller who could declare "this is a verdict question" could choose the shape of their own answer, which is the first thing [`additional_instructions`](#additional_instructions--what-a-caller-may-steer) is not allowed to do. `asked` reports what the classifier read, including its reasoning, so you can see the routing rather than guess at it. A classification the server cannot read runs **both** tracks rather than dropping one.

### Read `outcome` before `information` or `verdict`

A completed receipt does not imply a determination. `outcome` carries one value per track and sits above both sections precisely so a client reads it first.

| `outcome.information` / `outcome.verdict` | Meaning | Section present? |
|---|---|---|
| `answered` | The track ran and produced an answer. For `verdict`, this is the only value that carries a determination. | yes |
| `missing_required_facts` *(verdict only)* | The rules bear on the case but the facts needed to apply them were not supplied. See `verdict.missing_information`. | yes |
| `not_settled_by_rules` *(verdict only)* | The evaluated rules do not settle the question. | yes |
| `no_rule_bears` | The rules were read and none of them bears on this. | yes |
| `declined` | The gather declined to answer. | yes |
| `failed` | The gather did not produce a usable answer. | yes |
| `not_requested` | The question was not read as asking for this track. It was never run. | **no** — the section is `null` |
| `not_evaluated` | Nothing was evaluated at all — the project may have published nothing, its policy index may not be built, or no published policy may bear on the question. Both tracks report this together. | **no** — the section is `null` |

`not_requested` and `not_evaluated` are kept apart deliberately: one says *you did not ask for this*, the other says *there was nothing to answer from*. Collapsing them would let a caller read their own silence as the corpus's, and would make an unbuilt index look like a question that never wanted an answer. When nothing was evaluated the classifier never ran either, so `asked` carries two `false` booleans and a null `classifier_version` — read `outcome` first and `asked` will make sense.

Every value in the table is a legitimate `200` carrying a full receipt.

### The verdict invariant

`verdict.decision` is non-empty **if and only if** `verdict.reached` is true, **if and only if** `verdict.status` is `answered`. The envelope enforces this; it is not a convention.

The consequence worth stating plainly: **"not compliant", "denied" and "no" are reached verdicts** and appear in `verdict.decision`. A case that could *not* be decided leaves `decision` empty and reports why in `status`. No client can mistake the second for the first, which was the failure mode a single status field beside an optional verdict string invited.

### A blocked verdict still answers the information you asked for

If the case cannot be decided until you supply facts, `outcome.verdict` is `missing_required_facts` and `verdict.missing_information` carries them in a shape a follow-up form can be built from:

```json
{ "fact": "weekly-hours",
  "label": "Hours worked this week",
  "why_needed": "The cap is measured against the weekly total.",
  "required_by_rule_ids": ["AI-hours-1"] }
```

`verdict.missing_required_facts` carries the same facts as a flat list of labels, preserved for clients that already read it. `required_by_rule_ids` is restricted to rules that were actually in front of the gather — a rule id there that named no retained rule is refused exactly as a fabricated citation is.

Crucially, **the information track is unaffected**: if you also asked what the policies state, `information` is populated and answered even though the verdict is blocked. And if you did *not* ask, `information` stays `null` — a blocked verdict never conjures an information answer you did not request.

### A reached verdict may still carry checks before acting

Asking whether a right *exists* and asking whether an action *may proceed* are two questions, and the receipt keeps them apart.

When the retained rules establish an entitlement from the facts you supplied, the verdict is **reached** — `status` is `answered` and `decision` is non-empty — even though conditions still stand between that entitlement and exercising it. Those conditions are carried additively in `verdict.verification_requirements`, in the same shape as a missing fact:

```json
{ "fact": "accrued-balance",
  "label": "Days accrued as at the requested date",
  "why_needed": "The entitlement is established; the balance decides how much of it is available now.",
  "required_by_rule_ids": ["AI-leave-3"] }
```

The distinction is the one a caller needs:

- **`missing_information`** holds facts that could change the answer. It is non-empty **only** when `status` is `missing_required_facts`, and the verdict is blocked.
- **`verification_requirements`** holds conditions that do **not** change the answer but must be confirmed before acting on it. It is non-empty **only** when `reached` is true.

The two lists are therefore mutually exclusive by shape, and the envelope enforces both rules. A client must not render verification requirements as missing facts, and must not downgrade the verdict because they are present — the determination stands; these are what to confirm before relying on it.

`fact` is drawn from the same closed selector catalogue as `missing_information`, resolved through the same aliases, and `required_by_rule_ids` is filtered to rules that were actually in front of the gather. An item the catalogue does not admit is discarded and reported in `verdict.grounding`, and — because it qualifies rather than establishes the verdict — discarding one never invalidates the determination it was attached to.

The field is additive. It defaults to `[]`, and a client that has never read it is unaffected.

### English is the only internal language

Every stage of a decision — retrieval, rule classification and both gathers — runs in **English**, whatever language the question arrived in. That is one boundary, drawn deliberately in one place: a pipeline that reasoned in two languages would score an Arabic question against English text, or the reverse, and score nothing.

The caller is not required to write English. A question in another language is rendered into English on the way in, the decision is made in English, and the whitelisted **prose** is rendered back on the way out. Everything else is left exactly as it arrived.

The original `request.scenario` is preserved, but the text used internally is still model-mediated. Every question, including English input, passes through the normaliser so transport encoding can be decoded and the source language can be reported. Its prompt requires already-English text to come back unchanged, but the service does not independently enforce byte equality. `language.processing_scenario` is the text retrieval and adjudication actually read, and `processing_scenario_hash` seals it; inspect those fields instead of assuming the two texts are identical.

**What is never translated**, in either direction:

- `request.scenario` and `request.additional_instructions` — the caller's own bytes, and their `scenario_hash` / `additional_instructions_hash` digests, which is also what the idempotency binding is taken over;
- **every verbatim source sentence and citation text.** A citation is the document's own words; a translated quotation is not a quotation. `citations[].source.text` is the original, in the language the document was written in, always;
- every machine-readable value — rule ids, provision keys, status codes, discard reasons, hashes, fact names, counters.

Only prose composed *by* the decision crosses back: `information.answer` / `explanation` / `note`, `verdict.decision` / `explanation` / `note`, and each `missing_information[].label` / `why_needed` and `verification_requirements[].label` / `why_needed`. So a receipt can hold an Arabic quotation under an English-reasoned, Arabic-rendered explanation, and that is the intended shape — not an inconsistency.

The corpus is crossed once, at index-build time rather than per query: the retrieval index stores an English **projection** of each policy beside its identity, and the original is never written into an English-labelled field. Two versioned contracts govern the two crossings, and both are on the receipt:
| Profile | Value | Governs |
|---|---|---|
| `language.input_translation_profile`, `language.output_translation_profile` | `case-language-v4` | The inbound and outbound renderings of the *question and prose* |
| `language.projection_profile`, `retrieval.projection_profile` | `policy-english-projection-v1` | The rendering of the *corpus* the index was built from |

They version independently: the projection contract did not move when the transport contract went to v4. A query and the text it is scored against must be rendered under one contract or the two are not comparable, which is what `retrieval.projection_profile` exists to state.

> **Projection quality is fail-closed.** Each rendering first passes a structural preservation check during the build. The completed `policy-projection-quality-v1` gate then compares the built projection with the authoritative records and records `passed`, `failed`, or `unavailable`; readiness requires `passed` under the expected profile as well as a `ready` manifest. Carried indexes built before this gate need one validation run. The live AIS and HW projections passed 138/138 and 115/115 documents respectively, with zero findings. This gate detects gross substitution but cannot reliably distinguish a faithful rendering from a near-identical sibling record; see [known limitations](known-limitations.md).

#### The `language` block

Present on every decision made under the boundary; absent only on receipts written before it existed.

```jsonc
"language": {
  "source_language": "ar",              // BCP 47 as observed; "und" if the tag was malformed
  "processing_language": "en",          // always: what retrieval and both gathers worked in
  "response_language": "ar",            // what the prose in this receipt is written in
  "boundary_state": "rendered",         // or "identity" — the call ran and reported no change
  "output_rendering_state": "rendered", // or "not_required" | "target_unknown"
  "guidance_rendering_state": "rendered",  // or "not_required" | "unrendered_dropped"
  "input_translation_profile": "case-language-v4",
  "output_translation_profile": "case-language-v4",   // null when nothing was rendered back
  "processing_scenario": "...",         // the question as every stage actually read it
  "processing_scenario_hash": "...",    // SHA-256 over it, sealed by decision_hash
  "processing_additional_instructions": "...",
  "projection_profile": "policy-english-projection-v1"
}
```

Three of these are worth reading carefully:

- **`boundary_state`** distinguishes `identity` (the rendering call ran and reported the question was already English) from a call that was never made. Those are different facts and are never collapsed.
- **`output_rendering_state: "not_required"`** covers two situations — the answer was owed in English anyway, *or* the evaluation composed no prose at all (nothing retrieved, no rule bore, a track failed). Read it beside `source_language` to tell them apart. Whenever it is not `rendered`, `output_translation_profile` is null and `response_language` is `processing_language`, because no string in the receipt is in another language.
- **`guidance_rendering_state: "unrendered_dropped"`** means the caller's presentation guidance could not be carried across and was **dropped rather than applied un-rendered**. The decision is unaffected either way — guidance never reaches retrieval or the classifier.

`processing_scenario` is the text that was actually adjudicated, and `processing_scenario_hash` seals it. That pairing is the point of the block: without it a receipt would show a question in one language and an answer derived from a rendering of it nobody could inspect.

### Retrieval narrows by policy, then by rule

In project scope the policies bearing on the question are retrieved from that project's own policy index and the rest are discarded **before** anything is evaluated. The receipt reports that narrowing in full: `retrieval` carries the status, method, budget and scan bounds and the counts; `considered` and `excluded` carry the policies themselves with their rank, score and discard reason. There is no mode in which the whole published set is put to a model.

**What the index holds, and how a rule can rescue its policy.** The index carries three kinds of document, all rendered under `policy-english-projection-v1`:

- one **policy** document per published provision, always;
- one **rule** document per rule, but only for a policy holding more than `retrieval.large_policy_rule_threshold` (15) rules. Below that a policy is one governing statement and its own document carries it; above it the policy is a schedule whose rows a single document cannot represent;
- exactly one **manifest** per project, carrying `manifest_state` (`ready` or `incomplete`), the `projection_profile` and language it was built under, and the document counts expected against those uploaded. The manifest is the readiness gate — see [rebuilding](#rebuilding-the-policy-index).

`retrieval.method` is `direct_policy_rrf_elbow_rule_rescue_v1`. Direct policy relevance owns the primary ranking; a large policy does not gain a second score merely because it also has rule documents. Semantic reranker scores determine whether a meaningful adjacent drop supports a smaller direct-policy count (`semantic_elbow_applied: true`). A strong semantic lead controls identity directly; otherwise symmetric Reciprocal Rank Fusion combines the hybrid and semantic rankings of those same policy documents, so every policy has the same two ranking opportunities. `direct_policy_order` names which path ran. A moderate RRF cut can be expanded when an omitted English indexed heading covers an explicit query term absent from the selected records and the policy also clears `coverage_semantic_floor`; `coverage_expanded_policies` discloses the result. When semantic scores are flat, no precision boundary has been established, so the full scanned direct-policy pool remains available in hybrid-search order to the existing duplicate/diversity pass. Only the final five-policy budget reaches the gathers. A policy omitted by the direct cut can still be rescued by one of its own rules, but only when the rule independently clears both the absolute `rule_rescue_floor` and the `rule_rescue_margin` above the direct cutoff. Rule documents never enter direct-policy RRF and rule scores are never added to policy scores.

Three counters report what that did, and they answer different questions:

| Field | Says |
|---|---|
| `policy_scan`, `rule_scan` | How many policy-level and rule-level documents the discovery search examined. |
| `policy_documents_matched`, `rule_documents_matched` | How many of each the search returned. |
| `semantic_candidates`, `semantic_selected`, `semantic_largest_gap`, `semantic_cutoff_score`, `semantic_elbow_applied` | What the direct-policy precision gate observed and whether it had evidence to narrow. |
| `direct_policy_order`, `coverage_expanded_policies`, `coverage_semantic_floor` | Which direct ordering ran and whether explicit, semantically supported heading coverage widened its cut. |
| `rule_rescue_candidates`, `rule_rescued_policies`, `rule_rescue_floor`, `rule_rescue_margin` | How many omitted parents independently cleared the rule-only gate, how many survived the final policy budget, and the thresholds applied. |
| `rule_semantic_window`, `rule_semantic_candidates` | Azure AI Search reranks at most 50 initial results; these disclose that bound and how many returned rules actually carried a reranker score. Unscored tail rules cannot satisfy semantic rescue. |
| `policies_elevated_by_rule` | Compatibility alias for `rule_rescued_policies`. It no longer means that a rule score was added to a policy score. |
| `projection_ready` | Whether the index reported a complete corpus projection under the expected contract. Only ever `true` on a served answer — anything else is refused, not answered. |
| `rule_index_state` | `matched` — the rule index was available for rule-only rescue and within-policy slicing. `degraded` — rule documents exist under the expected projection and the query against them failed recoverably. `unavailable` — it was not consulted. |

`rule_index_state` appears both on `retrieval` (project-wide) and on each `considered` entry's `rule_selection` (per policy), because a project-wide degradation and a policy that simply has no rule documents are different facts about different policies inside one answer.

Five further concerns then act between the ranked hits and the model, because rank says nothing about size, nor about whether you have already read the same thing.

**Diversity ordering, before the retention budget.** The budget is a budget of *distinct policies to read*, and a corpus that holds one policy twice spends two of five slots saying one thing. Two mechanisms handle that, and they are **not** the same claim:

- **Exact semantic collapse.** When two candidates are identical in everything the platform stores — every source sentence, condition, effect, type, mode, required fact, authority, scope, effective window, carve-out, and the resolved semantics of every rule they supersede or relate to — the later one is discarded with `discard_reason: "duplicate_policy_content"`, names the retrieved policy in `duplicate_of_provision_key`, and is counted in `retrieval.policies_duplicate_collapsed`. This is the **only** discard that asserts two policies are the same, and it is the only one whose terms still reached the model — in the policy it names.
- **Normative-content diversity ordering.** Two candidates can require the same thing without being provably identical: the measured case is one provision recorded twice where one copy carries forty-two `related_rule_ids` and the other carries none. That is a real difference in the record, so they are **not** duplicates and are never reported as any. They are merely *ordered*: candidates are grouped by what they require — `related_rule_ids` withheld, because being told which rules to read together is a reading aid rather than a term; **supersession kept**, because displacing one rule and displacing another are different acts — and the highest-ranked member of each group is offered before any second member of a group. `retrieval.policy_selection_order` names the ordering (`relevance_then_normative_content_v1`) and `retrieval.policies_diversity_deferred` counts what the ordering actually **cost**: candidates that ranked inside the retention budget and were displaced out of it. A same-group member that ranked outside the budget anyway is not counted, because nothing displaced it — when no group has two members inside the budget, the count is `0` and the ordering changed nothing.

A deferred candidate keeps its **own** rank and score, stays in `considered`, and carries the ordinary `discard_reason: "outside_budget"` — which therefore means *did not place inside the retention budget*, by rank or by this ordering, rather than *ranked below it*. Read `policy_selection_order` and `policies_diversity_deferred` together when a highly-ranked policy sits outside the budget while a lower-ranked one was retained; that pairing is the explanation, and a non-zero count is the assurance that at least one policy really was displaced rather than merely ranked low. Deferring is not discarding: a group's second member is read whenever the budget reaches it.

**Rule-level retrieval, for a policy that is really a table.** A provision with a dozen rules is one governing statement and goes to the model whole. Past `retrieval.large_policy_rule_threshold` (15) it is a *schedule* — the measured case is a Table of Violations and Penalties with seventy-four rows, one per violation, of which a question touches a handful. Such a policy is read **rule by rule**: its rules are ranked against the question by the policy's own words, and up to `retrieval.selected_rule_budget` (15) are selected.

The same two-mechanism split applies one level down, and the distinction matters more here than anywhere:

- **Exact rule collapse.** A rule identical to an earlier rule of the same policy — by the same full comparison used between policies — is not a candidate for a second slot. `rule_selection.duplicate_rules_collapsed` counts them, and `rule_selection.represented_rule_ids` names the unread ids that are exact copies of ones that were read, so `rules_discarded` is not misread as "unknown content".
- **Evidence diversity ordering.** **Repeated source text does not mean duplicate rule semantics.** One sentence commonly states several obligations and is extracted into one rule each, so four genuinely different rules — one permitting, one forbidding, one obliging, one routing — can rest on a single passage. They are four rules and are never collapsed. Among the rules that *do* match the question, the best of each distinct source passage is taken before a second rule from a passage already covered. This is selection priority, never a claim that two rules resting on one sentence are one rule, and it can only reorder rules that already matched — a rule that does not bear on the question is never promoted by it.

**The rule budget bounds the record, not one step of building it.** Each selected rule's explicit context — what it supersedes, what the drafter marked as read-together — follows it in, but **only into slots the selection left unused**: the total number of rules put in front of either gather, context included, never exceeds `selected_rule_budget` (15). `rule_selection.context_rules_added` is counted *inside* `selected_rules`, and any context that found no slot, or no room in characters, is named in `context_rules_omitted` rather than dropped in silence.

Every such policy carries `rule_selection` on its `considered` entry:

```jsonc
"rule_selection": {
  "total_rules": 74, "selected_rules": 15,
  "selected_rule_ids": ["AI-…-7", "AI-…-41", …],
  "rules_discarded": 59,
  "method": "hybrid_rule_v1",
  "sliced": true,
  "context_rules_added": 1, "context_rules_omitted": ["AI-…-52"],
  "duplicate_rules_collapsed": 0, "represented_rule_ids": [],
  "rule_index_state": "matched", "rule_index_hits": 9,
  "lexical_candidates": 12, "quantity_candidates": 4,
  "fused_candidates": 17, "evidence_diversity_quota": 8,
  "rules_without_projection": 0,
  "chars": 38679, "budget_chars": 200000, "oversize": false
}
```

The five candidate counters say how the selection was reached rather than what it chose: how many rules the rule index returned (`rule_index_hits`), how many the lexical and quantity rankings each produced, how many distinct rules the fusion had to choose from (`fused_candidates`), and `rules_without_projection` — rules the caller held no English rendering for. Those last score **zero on the lexical rank and are not scored against their stored text as a consolation**, because falling back would reintroduce exactly the cross-language match the projection removes. A zero there is not a dismissal: the rule can still be ranked by the rule index and by quantity, both of which are fused with it.

`evidence_diversity_quota` is how many of the budget's slots passage diversity may claim before relevance takes over — half the budget, rounded up. It is a **reserve, not a filter**: covering the best rule of every distinct passage first sounds right, but in a schedule there are more distinct passages than slots, so an unbounded version exhausts the budget inside the first-of-each pass and a paragraph stating two obligations can never contribute its second, however well it scores.

`selected_rules` always equals the number of rules in the record and the length of `selected_rule_ids`, is never greater than `selected_rule_budget`, and `rules_discarded` is always `total_rules` less `selected_rules`.

`method` is `whole_policy` when the policy was small enough to read entire, or one of three selection algorithms, named rather than described because they are different-sized claims:

| `method` | Means |
|---|---|
| `hybrid_rule_v1` | The rule index took part. Its ranking was fused with the lexical and quantity rankings, so a rule the policy document's own text could never have surfaced was reachable. |
| `scenario_relevance_v3` | Rule documents exist under the expected projection and the query against them failed recoverably. The selection is lexical and quantity over the English projection — a real selection over the right corpus, made without one of its rankings. |
| `scenario_relevance_v2` | The rule index was not consulted. The selection ranked the policy's own stored words, which is what a receipt written before the rule index existed also means. |
| `document_order` | **No rule matched the question's terms** and a bounded sample was taken instead. |

`document_order` is a real signal: it says the policy was retained on the search layer's judgement while the rule-level selection had nothing to key on, and an answer resting on such a policy deserves more scrutiny. Emitting any of the others when its ranking did not run would be claiming a ranking that never happened, which is the same class of untruth as claiming a rule was read.

Beside relevance the selection also ranks by **quantity compatibility**: a question stating a quantity ("26 months", "more than sixty minutes") is matched against the quantities and ranges the rules themselves state, so a threshold row is reachable even when it shares little vocabulary with the question. A rule stating no quantity is not dismissed by this — it is simply not ranked by it, and can still be ranked by the rule index and by the lexical pass.

The selection is deterministic — no second model call, no randomness, every tie broken by document order — which is what makes `selected_rule_ids` worth naming on a receipt. Lexical weighting is an inverse document frequency computed over *that policy's own rules*, so the words every row of a schedule shares score nothing and only what distinguishes one row from another can decide. It carries no wordlist for any language.

**Whole-policy fitting, as the backstop.** Slicing makes each record smaller; it does not promise that several together fit. So whole records are still admitted in rank order while they fit `retrieval.payload_budget_chars`, and one that would overflow is set aside with `discard_reason: "outside_payload_budget"` and counted in `retrieval.policies_over_payload_budget`. Later, smaller policies are still admitted, so one large record costs only itself.

Two guarantees hold over all of these passes:

- **Nothing is ever truncated.** A rule is selected whole or not at all; a policy is admitted whole or sliced to whole rules. Half a rule presented as a rule, or part of a policy presented as the policy, is the narrowing a reader cannot detect.
- **Nothing is silently omitted, and nothing is silently equated.** Every raw candidate stays in `considered` with the rank it achieved. A policy set aside for size, deferred by diversity, or collapsed as an exact duplicate is distinguishable from the others by its `discard_reason` and the counts beside it, and **only** `duplicate_policy_content` asserts sameness. A policy read as a slice says how many of its rules were read and which. **No answer may claim a policy was read whole when a slice of it was.**

When the relevant slice itself does not fit — the selected rules are already the narrowest honest set — the record is refused rather than cut down: `rule_selection.oversize` is `true`, `size.oversize` is `true`, and the affected track declines. The same holds for a policy under the threshold that is larger than one pass on its own. An empty retained set would read as "no published policy matched", which would be false.

In single scope — when you name a `provision_id` — retrieval is bypassed, but a policy over the rule threshold is still read rule by rule and still discloses its selection.

**Retrieval runs once, for the whole question.** Both tracks read the same retained records, and both narrowing passes run once over that one set. That is deliberate: retrieving separately per track would let the statement you are told and the verdict you are given rest on two different sets of policies inside one receipt. The limitation it accepts is [documented](known-limitations.md): a mixed question whose verdict half would have retrieved a different policy than its information half gets one retrieval, tuned to the whole question — and one rule selection, likewise.

### Envelope

The response is `case_decision_v2`, named in `schema_version` so a consumer can pin it and reject a shape it was not written against. `GET` may also serve `case_decision_v1` for a decision made before the two-track redesign — see [Reading an older receipt](#reading-an-older-receipt).

| Field | What it carries |
|---|---|
| `schema_version` | `case_decision_v2`. |
| `receipt_status` | `completed`. Only a completed receipt is served as a body; `pending` and `failed` are answered as errors. |
| `decision_id`, `correlation_id`, `idempotency_key` | Identity of this call. `decision_id` is what `GET /api/policy-decisions/{decision_id}` takes. |
| `policy_set` | `{id, key, name}` — trace identity, routing key, display name. |
| `active_version` | `{version_id, version_number, effective_from, effective_to}`, or `null` when the project has published nothing. This is the version the decider itself loaded, not a re-read of "current" taken after a call that runs for tens of seconds. |
| `caller` | `principal_identity`, `principal_role`, `authentication_source`, the caller-declared `calling_system_identity`, and `channel`. The proved identity and the declared label are two fields on purpose. |
| `request` | `scenario`, `scenario_hash`, `additional_instructions`, `additional_instructions_hash`, `scope` (`project` or `single`), `requested_provision_id`, `reasoning_effort_requested`, `received_at`. |
| `asked` | `information_requested`, `verdict_requested`, `classification_reasoning`, `classifier_version`. What the classifier read the question as asking for. |
| `outcome` | `{information, verdict}` — the two-value status above. **Read it first.** |
| `information` | `null`, or `{status, answered, answer, explanation, route, citations, note, grounding}`. `answer` is non-empty exactly when `answered` is true; `explanation` carries prose from a track that composed some *without* answering, and is otherwise `null`. |
| `verdict` | `null`, or `{status, reached, decision, explanation, missing_information, missing_required_facts, verification_requirements, route, citations, note, grounding}`. `verification_requirements` is non-empty only on a reached verdict; see [checks before acting](#a-reached-verdict-may-still-carry-checks-before-acting). |
| `retrieval` | `status`, `method` (`direct_policy_rrf_elbow_rule_rescue_v1`), direct semantic-gate fields (`semantic_candidates`, `semantic_selected`, `semantic_largest_gap`, `semantic_cutoff_score`, `semantic_elbow_applied`, `direct_policy_order`, `coverage_expanded_policies`, `coverage_semantic_floor`), rule-rescue fields (`rule_rescue_candidates`, `rule_rescued_policies`, `rule_rescue_floor`, `rule_rescue_margin`, `rule_semantic_window`, `rule_semantic_candidates`), `policy_budget`, `policy_scan`, `rule_scan`, `policies_retrieved`, `policies_considered`, `policies_retained`, `policies_discarded`, `policies_untestable`, plus `payload_budget_chars`, `policies_over_payload_budget`, `large_policy_rule_threshold`, `selected_rule_budget`, `policies_rule_sliced`, `policies_duplicate_collapsed`, `policy_selection_order`, `policies_diversity_deferred`, `projection_profile`, `projection_ready`, `policy_documents_matched`, `rule_documents_matched`, the compatibility alias `policies_elevated_by_rule`, `rule_index_state` and a `reason`. |
| `language` | `null`, or the block described in [English is the only internal language](#english-is-the-only-internal-language). Present on every decision made under the boundary. |
| `considered`, `excluded` | Policy references: `provision_id`, `provision_key`, `heading_path`, `rules`, `retained`, `best_rank`, `best_score`, `discard_reason` (`outside_budget`, `no_retrieval_match`, `stale_index_version`, `outside_payload_budget`, `duplicate_policy_content`), `duplicate_of_provision_key` (set **only** for `duplicate_policy_content`), `reason`, `payload_url`, and `rule_selection` when the policy was read by rule. |
| `citations` | Every rule either track rested on, **deduplicated by `rule_id`** and tagged with `serves: ["information"]`, `["verdict"]` or both. Per citation: `rule_id`, its `policy` reference, and `source` with `state` (`quoted`, `no_citation`, `unresolved`, `not_stored`), `text`, `page`, `section`. Each section also carries its own untagged list. |
| `size` | `combined_chars`, `budget_chars`, `oversize` for the record that was **actually evaluated** — after the payload-budget narrowing, so it describes what the model read rather than what retrieval first selected. |
| `trace` | `prompt_version`, `instruction_profile`, `model_deployment`, `retrieval_method`, `index_name`, `index_version_id`, `stage_latency_ms`, and `token_usage`. Timings and service-reported usage describe this execution, are excluded from `decision_hash`, and are nullable on historical receipts. |
| `decision_hash`, `hash_basis` | The integrity seal and the rule it was taken under. |
| `receipt_url` | Relative path where this receipt is read back. |
| `decided_at`, `latency_ms` | When the decision completed, and how long it took. |

Each section carries its **own** `grounding` report — including `fabricated_citations`, the citations the fabrication guard refused. The two tracks ground separately, on different prompts with different citation sets, so a single receipt-level block would have to pick one and present it as the whole.

**No policy record is inlined.** Policies are large and already served byte-for-byte by `GET /api/policy-payload/{provision_id}`; every policy reference in a receipt carries that `payload_url` instead. A receipt that embedded the record would double the corpus into the audit log and go stale the moment the projection changed.

There is no "reasoning effort used" in `trace`. The gather silently drops that parameter and retries when a deployment rejects it, so the effort actually used is not knowable from here. What the caller asked for is knowable, and is reported as `request.reasoning_effort_requested`.

### Reading an older receipt

`case_decision_v1` was the envelope before a case was read as two tracks. It reported one `decision_status` and one `decision` block, and answered a mixed question with only one of its halves. Nothing writes it any more.

Receipts already stored under it are still served as v1 — by `GET`, and by an idempotency replay of a key issued back then. They are **not** re-projected into v2: doing so would mean inventing the two booleans nobody ever classified for that decision, and a receipt whose content changed after the fact is not evidence of anything. `schema_version` tells the two apart, and the OpenAPI description models them as a discriminated union on that field.

If you are integrating now you will only ever see v2. If you hold receipts or idempotency keys from before, branch on `schema_version`.

### `additional_instructions` — what a caller may steer

The field exists so an integration can show a user the guidance being sent and let them add to it. Maximum **2000 characters after whitespace normalisation**; longer is a `422`. Normalisation unifies line endings, collapses runs of blank lines and intra-line whitespace, and strips — so a byte-for-byte retry from a text area still matches its idempotency binding.

It shapes **the emphasis, length and format of the explanation, and nothing else.** It cannot change:

- which policies were retrieved or read — it never reaches the retrieval step at all, so it cannot steer which policies are considered;
- **which tracks run** — it never reaches the classifier either, so it cannot turn an information request into a verdict request or the reverse;
- what any rule means, or the authority of the published policies;
- either track's status, or the verdict;
- the requirement to cite every rule the answer rests on;
- the prohibition on drawing on anything outside the published records.

Guidance asking for any of those is ignored for that part, and the affected section's `note` says so.

The normalised text is stored on the receipt, echoed back in `request.additional_instructions` so an integration can show exactly what was applied, bound into the idempotency request hash (so reusing a key with different guidance is a `409`, not a replay), and sealed by digest in `decision_hash`.

**The server's own instructions are never returned and are not caller-editable.** `trace.prompt_version` and `trace.instruction_profile` identify them instead — `instruction_profile` names the immutable server-side framing that caller guidance is applied under, and changes when that framing changes. It never contains prompt text. The asymmetry is the whole safety story of the field: what a caller can edit is theirs and is shown back to them, and what they cannot edit is named but not exposed.

### `decision_hash` — an integrity seal, not a determinism claim

`decision_hash` is a canonical SHA-256 over a **fixed, documented subset** of the receipt: `schema_version`, the project's routing key, the published version number, the scenario hash, the caller-guidance hash, the scope, the retrieval status, the considered policies by stable provision key with their retained/discarded state **and which of their rules were read** (`selected_rule_ids`, `total_rules`), **both `asked` booleans**, **both `outcome` values**, **both semantic sections in full** (including structured missing information and checks required before acting), and each merged citation's rule id, source state, verbatim text and `serves` tags.

Which rules were read is sealed because the same policy read whole and read as a slice of eight rows are two different accounts of the same question, and a hash that could not tell them apart would seal the weaker one. The booleans are sealed because they decide what the receipt answers: a receipt that could be re-labelled "you only asked for information" after the fact would let a missing verdict be explained away.

Excluded, and why: `asked.classification_reasoning` and `asked.classifier_version` — the reasoning is prose *about* a routing choice rather than part of what was decided, and sealing it would move the hash whenever a classifier reworded itself; the rule-selection *method* and counts (including `duplicate_rules_collapsed` and `represented_rule_ids`), which are derivable from the ids that are sealed; `policy_selection_order` and `policies_diversity_deferred`, which describe the *ordering* that produced the retained set rather than what it decided — the outcome of that ordering is already sealed, in each policy's retained/discarded state; `decision_id`, `correlation_id` and `idempotency_key` name the *call* rather than the decision; the project and version UUIDs are surrogate keys that differ between environments while the decision does not; `decided_at`, `received_at` and `latency_ms` mean a slower call did not decide something different; `receipt_url` is a routing detail; and the hash itself.

What it proves is that *this* receipt's decision-defining content has not been altered since it was written. It is **not** a replay or determinism guarantee: a language model is in the path, so the same scenario put twice to the same version may legitimately produce different prose and a different hash. `hash_basis` names the preimage rule so a future basis can be added without making an old hash ambiguous. Current receipts use `case_decision_v2_verification` or `case_decision_v2_lang_verification`; these names record that `verification_requirements` are sealed. Historical `case_decision_v2`, `case_decision_v2_lang`, and `case_decision_v1` receipts remain readable under the basis stored with them.

**`case_decision_v2_lang_verification`** is the basis for every current decision made under the language boundary. It seals everything `case_decision_v2_verification` does **plus two fields**:

- `processing_scenario_hash` — the digest of the text that was actually adjudicated. Without it, a receipt could show a question in one language while the English rendering the decision was really made from went unsealed and unverifiable.
- the whole `language` block — the observed source language, the processing and response languages, the three rendering states, and both translation profiles and the projection profile. Two contracts can reduce one question to two different English texts, so which contract was used is part of what was decided.

The caller's own `scenario_hash` remains sealed beside it, so both the words the caller sent and the words the decision read are covered, and neither can be swapped for the other.

To verify a stored receipt, `GET /api/policy-decisions/{decision_id}` and compare the `decision_hash` you kept against the one served. The envelope is replayed from storage rather than rebuilt, so the comparison is a real check. Compare the **hash**, not the response bytes: the replay is content-equivalent rather than byte-identical, and JSON key order may differ between the original response and the replay.

### Timing and token telemetry

Every decision response reports telemetry from its internal execution. These fields describe *how the answer was produced*, never *what was decided*, so they are excluded from `decision_hash` and may be `null` on receipts written before they existed. The decision envelope's `latency_ms` is not client-observed end-to-end latency; outbound rendering and final receipt persistence continue after its measurement point.

| Field | Where | What it is |
|---|---|---|
| `latency_ms` | `/case`, `/case/light` top level | Wall-clock from request execution start through internal adjudication, captured before outbound response rendering, policy-link lookup, envelope construction and final receipt persistence. |
| `trace.stage_latency_ms` | `/case` | Wall-clock milliseconds per named stage. Sparse: a stage that did not run has no key. |
| `trace.stage_latency_ms` | `/case/light` | The same map, carried through the projection unchanged. |
| `trace.token_usage` | `/case`, `/case/light` | Service-reported token counts for this request; Light carries the same report through its projection. |
| `token_usage`, `latency_ms` | `/policies` | The usage report and full retrieval-operation time at the top level — retrieval has no decision trace to hang them from. |
| `stage_latency_ms` | `/policies` | The same wall-clock map, at the top level beside `latency_ms` for the same reason. Additive and optional: it defaults to absent, and a client that has never read it is unaffected. This route reports far fewer keys than a decision does, because it runs far less. |

#### `stage_latency_ms` is wall-clock, and only wall-clock

Every value is a duration in milliseconds. No counter, score or size is ever expressed in this map, so a client may treat every entry as a time without inspecting the key. The keys that can appear:

| Key | Stage |
|---|---|
| `reservation` | **Cumulative from the start of the request** to the moment the `pending` receipt row is written and committed, before any model call. |
| `language_in` | Normalising the caller's question into the processing language, including transport decoding and already-English input. Recorded on every successful decision path. |
| `scope_load` | Loading the project's published scope. |
| `index_probe` | Asking the search service whether this project's index exists. A live round trip on its own connection, not a local check. Recorded even when the probe fails, because the request still waited for it. |
| `projection_readiness` | Checking the index manifest is `ready` under the expected projection. Runs **concurrently with `index_probe`** — the two are independent questions. |
| `embedding` | Embedding the query for semantic ranking. Runs **concurrently with the two probes above** — it needs only the scenario. Not run on `/policies`. |
| `retrieval_preflight_wall` | Wall time for that whole concurrent group — close to `max(index_probe, projection_readiness, embedding)`, **not** their sum. |
| `index_state_probe` | The follow-up round trips that tell "the index is empty", "the index is stale" and "nothing matched" apart. Present only when retrieval returned no hits at all. |
| `policy_search` | The policy-document query. |
| `rule_discovery` | The rule-document query. Runs concurrently with `policy_search`. |
| `retrieval_discovery_wall` | Wall time for the concurrent discovery phase as a whole — close to `max(policy_search, rule_discovery)`, **not** their sum. |
| `policy_selection` | Fusion, elbow cut, rule rescue, duplicate collapse and diversity ordering. |
| `retained_rule_ranking` | Ranking rules within retained policies. |
| `rule_slice_and_fit` | Slicing large policies to the rule budget and fitting the payload. |
| `classifier` | The single classification step that reads the question for both tracks. It completes **before** the gathers begin. |
| `information_gather` | The informational gather. Present only when that track was requested. |
| `verdict_gather` | The verdict gather. Present only when that track was requested. |
| `gather_wall` | Wall time for both gathers together. Because they run concurrently, this is close to `max(information_gather, verdict_gather)` rather than their sum. |
| `gather_total` | The classification and gather phase together — approximately `classifier + gather_wall`. **It already contains `classifier` and `gather_wall`.** |
| `decider_wall` | Wall time for the whole decider call: retrieval, classification and gathers. **It already contains every retrieval and gather stage above.** |
| `language_out` | Checking and, where needed, rendering composed prose into the caller's language. Recorded on every successful decision path; it may round to `0` when no model rendering was needed. |
| `policy_link_lookup` | Resolving `payload_url` links for the policies in the receipt. |
| `to_envelope` | **Cumulative from the start of the request** through outbound rendering and policy-link lookup to the point immediately before the envelope is built. Final receipt persistence still follows it. |

Three consequences worth building against:

- **Do not sum the stages and expect `latency_ms`.** The map deliberately mixes three kinds of value: leaf spans (`policy_search`, `classifier`), *overlapping wall measures* of phases that ran concurrently (`retrieval_preflight_wall`, `retrieval_discovery_wall`, `gather_wall`), and *cumulative* measures taken from the start of the request (`reservation`, `to_envelope`). `decider_wall` and `gather_total` are containers over other keys. Summing them double- and triple-counts.
- **Presence says the stage ran.** An unrequested gather key is absent. A present value of `0` means the measured work completed in less than one millisecond after integer rounding; it does not mean the stage was skipped.
- **The key set is not a contract to enumerate against.** Stages are added and renamed as the path changes. Read the map as a map, and treat an unrecognised key as a duration you do not yet have a label for.

#### What the receipt can never time

`to_envelope` is the last measurement a receipt can carry, and this is a property of what a receipt *is* rather than an omission. Building the envelope, computing its seal and writing it to storage all finish **after** the object that would have to report them, and the stored row is that object's own serialisation. There are only two ways to put those durations in the response, and both break the contract:

- changing the returned envelope after the write leaves you holding a receipt the database does not have, so your `POST` body and a later `GET` replay disagree;
- writing the row and then updating it stops persistence being one act, and a crash between the two stores a receipt that was never returned to anyone.

So they are measured and emitted **beside** the receipt, in the server's logs, as a `case_decision.finalisation` record carrying `envelope_build`, `receipt_finalize` and `request_total` alongside the decision id and the same stage map. They are operator telemetry, deliberately not caller telemetry, and the record is written whether or not the receipt could be stored — a finalisation that fails still spent the time it took to fail.

If you need end-to-end latency as a caller, measure it as a caller. `request_total` is the server's view of the same span and is not returned to you.

#### Token usage is a floor, not a total

`token_usage` sums the counts the model service itself reported. It is never estimated and never inferred from text length.

| Field | Meaning |
|---|---|
| `calls` | How many model calls ran under this request — chat and embedding both. A full decision is typically six or seven: one embedding, one language crossing, the classification step, and one or two gathers depending on whether the question asked for information, a verdict, or both. |
| `calls_without_usage` | How many of those returned no readable usage. |
| `prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens` | Sums over the calls that *did* report. `null` when no call reported at all. |

**When `calls_without_usage` is greater than zero, every numeric total is a lower bound.** A client, a dashboard or a billing view must present it as *at least N*, never as an exact figure — the calls that reported nothing consumed tokens that no number here contains. Presenting a floor as a total understates real consumption, and the field exists precisely so that it does not have to be guessed at.

`null` and `0` are different answers: `null` means nothing was reported, `0` means a report arrived and said zero.

### Rebuilding the policy index

`POST /api/policy-sets/{key}/policy-index/rebuild` → `PolicyIndexBuildResponse`

Rebuilds a project's policy index from the authoritative database: every published policy of the active approved version, re-rendered into English under `policy-english-projection-v1`, re-embedded, and re-uploaded. A project with no active version is a coherent **empty** build, not an error — the response carries `version_number: null` and `document_count: 0`.

Response: `state`, `policy_set_key`, `index_name`, `version_number`, `document_count`, `policy_document_count`, `rule_document_count`, `projection_profile`, `manifest_state`, `indexed_at`, `error`.

**It runs inline, in the request.** The call is held open for the whole rendering and indexing pass and its duration scales with the size of the corpus. Set a generous client timeout and do not run it concurrently against one project. See [known limitations](known-limitations.md) for the cost.

**Atomicity is a manifest state machine, not a transaction.** Azure AI Search has no transaction to enrol in, so the build sequences its writes so that no partial corpus is ever queryable:

1. The manifest is first moved to `incomplete`. If that write is not acknowledged, **the rebuild stops before writing anything** and the corpus that was there is the one that is still there.
2. The policy, rule and manifest documents are uploaded, and acknowledgements are counted **by key** rather than trusting an HTTP status. If fewer come back than were sent, the build fails here — leaving the manifest `incomplete`.
3. Documents belonging to this project that are no longer live are swept, *after* the upload succeeds, never before.
4. Only then is the manifest moved to `ready`.

Because the readiness gate matches on `manifest_state eq 'ready'` **and** the expected `projection_profile`, a project whose rebuild failed at any step answers `503 index_projection_unavailable` rather than serving a half-built corpus. The old documents are not deleted until a new complete set is in place.

**There is no automatic retry and no rollback.** The rebuild is a pure function of the database, so re-running it *is* the recovery: the same input produces the same document ids and overwrites in place. A build that failed leaves the project unmatchable until a rebuild succeeds, which is the intended failure direction — an unmatchable project is visible, a silently half-indexed one is not.

A rendering failure for *any* policy fails the whole build. Stamping a corpus that is English in part would make the profile mean something it must never mean.

The same build also runs **best-effort on publish**, in the publish request, after the publish transaction has committed. A failure there does not fail the publish: it is logged, recorded as a failed build state, and reported by `GET /api/policy-sets/{key}/policy-index`, and this endpoint is the repair.

### Validating the policy index

`POST /api/policy-sets/{key}/policy-index/validate` → `PolicyIndexValidationResponse`

Checks a projection that is **already built**, without rebuilding any of it. The endpoint reads what the index holds, re-derives the authoritative text from PostgreSQL, and compares the two. **No rendering call is made and no content document is written.**

It exists because a corpus that was *transported* successfully is not a corpus that is *faithful*: a rendering call that returned, an embedding that returned and an upload that was acknowledged are facts about carriage, not about meaning. Every corpus built before the faithfulness gate is complete, `ready` and unvalidated — and the gate refuses all of them until something checks. This is how they get checked, at the cost of one embedding pass instead of a full re-render.

Response: `state` (`validated`, `skipped` or `failed`), `policy_set_key`, `index_name`, `projection_profile`, `recorded`, `validated_at`, `error`, and `quality`.

`quality` carries the verdict and nothing that could leak policy text — `state` (`passed`, `failed` or `unavailable`), the `profile` it was reached under, `checked_documents`, `structural_findings`, `below_floor`, `minimum_similarity`, `mean_similarity`, `validated_at`, and `findings` as `{ code, document_id }` pairs. A document id is a digest of platform-generated identifiers, so a finding names a document without quoting one.

`unavailable` is **not** a pass. A check nobody could perform is exactly as much evidence as a check that failed, and the readiness gate treats the two identically — the states are kept apart only because their repairs differ.

`recorded` is the load-bearing field. The verdict is in force only once it reaches the manifest document the readiness gate reads, so a `passed` that was not recorded has changed nothing about what the project may answer. The manifest is written before the state row, so this endpoint can lag what is in force and can never be ahead of it.

**On failure nothing is deleted.** The verdict is recorded, the readiness gate stops matching against the corpus, and every document stays where it is. A failed validation is not proof the documents are wrong; it is proof this build cannot vouch for them, and destroying the evidence would turn a reversible finding into an outage. `manifest_state` is left alone — whether every expected document landed is a fact about a build that already happened, and a validation has no standing to revise it.

### Errors

Error bodies follow this API's convention: FastAPI's `{"detail": ...}` with a structured object carrying `code`, `message` and, where one exists, `decision_id` and `correlation_id`. **Branch on `code`, never on the message** — messages are prose and are reworded; codes are the contract.

Every failure below is also classified by who can actually resolve it, because that decides what your integration should do with it:

| Class | Meaning | What your client should do |
|---|---|---|
| **Caller** | The request is wrong and will stay wrong. | Fix the request. Do not retry it unchanged; a retry loop here is an infinite loop. |
| **Operator** | The deployment is not in a state that can answer. | Surface it to a human with the `code`. Retrying will not clear it. |
| **Transient** | A dependency was briefly unavailable and the row below says the key remains reusable. | Retry with backoff under the same `Idempotency-Key` if you had one. |
| **Transient dependency, spent key** | A dependency may recover, but this decision receipt was finalized as failed. | Back off, then start a new call with a new `Idempotency-Key`. |
| **Terminal** | The call ran and cannot be repeated under this key. | Do not retry under the same key. Start a new call with a new key if you still need an answer. |

`POST /api/policy-decisions/{project_key}/case` and `POST /api/policy-decisions/{project_key}/case/light` — the light route accepts the same request and headers and fails in exactly the same ways, because it runs the same decision:

| Status | `code` | Class | When |
|---|---|---|---|
| `401` | `authentication_required` | Caller | No authenticated caller. |
| `404` | `project_not_found` | Caller | Unknown project key. |
| `404` | `policy_not_in_project` | Caller | A `provision_id` naming a policy in another project. |
| `422` | `correlation_id_conflict` | Caller | The header and body correlation ids differ. |
| `422` | `correlation_id_too_long` | Caller | `X-Correlation-Id` or `correlation_id` longer than 200 characters. |
| `422` | `idempotency_key_too_long` | Caller | `Idempotency-Key` longer than 200 characters. |
| `422` | `calling_system_identity_too_long` | Caller | Longer than 200 characters. |
| `422` | `provision_id_too_long` | Caller | Longer than 200 characters. |
| `422` | `reasoning_effort_invalid` | Caller | Not one of `low`, `medium`, `high`. Refused rather than coerced, so the receipt cannot record an effort the call did not run at. |
| `422` | `reasoning_effort_too_long` | Caller | Longer than 20 characters. |
| `422` | `additional_instructions_too_long` | Caller | Guidance longer than 2000 characters after normalisation. |
| `422` | `scenario_too_long` | Caller | `scenario` longer than 20,000 characters. Refused before the receipt is reserved and before any model call, so a permanent input fault never returns as a retryable `503`. |
| `422` | `invalid_request` | Caller | A malformed id or other rejected input. |
| `409` | `idempotency_key_reused` | Caller | The key was already used for a different request. Send the original request, or use a new key. |
| `409` | `decision_in_progress` | Transient or operator | A `pending` receipt exists for this key. During a live call, wait and retry the same key. The state has no lease or heartbeat; if it persists after the process is known to have stopped, operator repair is required. Starting a new key before liveness is known can duplicate the decision. |
| `409` | `decision_previously_failed` | Terminal | The decision for this key failed and carries no verdict. A key is spent; a retry needs a new one. |
| `409` | `decision_reservation_conflict` | Transient | The receipt could not be reserved because a conflicting record exists. |
| `503` | `ai_unavailable` | Operator | Azure OpenAI is not configured, or the decider reported it unavailable. |
| `503` | `scenario_translation_unavailable` | Transient dependency, spent key | The question could not be rendered into the processing language. **No decision was attempted**, but the failed receipt finalized the key. |
| `503` | `scenario_translation_empty` | Transient dependency, spent key | The inbound rendering returned, but with no usable text. Refused rather than adjudicating an empty question; retry later with a new key. |
| `503` | `response_translation_unavailable` | Transient dependency, spent key | A decision was made, but its prose could not be rendered back into the caller's language. Refused rather than returning English prose labelled as the caller's language; retry later with a new key. |
| `503` | `index_projection_unavailable` | Operator | The project's index has no manifest that is `ready` under `policy-english-projection-v1` and quality-passed under `policy-projection-quality-v1`. Retrieval is refused rather than run against an unmatchable or unvalidated corpus. The operator must [rebuild](#rebuilding-the-policy-index) or [validate](#validating-the-policy-index) as the recorded state requires. This failure occurs after reservation, so the original key is spent; submit the repaired request under a new `Idempotency-Key`. |
| `503` | `decision_receipt_unavailable` | Transient | The receipt could not be reserved — **no decision was attempted.** Retry. |
| `500` | `decision_failed` | Terminal | The decider faulted; the receipt records the failure. |
| `500` | `decision_receipt_failed` | Terminal | A decision was made and could **not** be stored. It carries the decision and correlation ids and deliberately carries no verdict — a verdict that cannot be cited later is exactly what this endpoint exists to stop shipping. Retry with a new `Idempotency-Key`. |

For the decision operations, failures discovered after receipt reservation close that receipt as failed and spend its idempotency key. That includes `policy_not_in_project`, decider-side `invalid_request`, the three translation failures, `index_projection_unavailable`, a runtime `ai_unavailable`, `decision_failed`, and `decision_receipt_failed`. Errors rejected before reservation do not create a receipt. `ai_unavailable` can occur on either side of that boundary: a missing server configuration is rejected before reservation, while a dependency failure reported by the running decider carries a `decision_id` and spends the key.

`POST /api/policy-decisions/{project_key}/policies` refuses far less, because it reserves nothing and decides nothing:

| Status | `code` | Class | When |
|---|---|---|---|
| `401` | `authentication_required` | Caller | No authenticated caller. Retrieval exposes approved policy records, so it is authenticated like the decision routes. |
| `404` | `project_not_found` | Caller | Unknown project key. |
| `422` | *(FastAPI validation detail)* | Caller | The required `scenario` field was omitted or had the wrong JSON type; request-model validation rejects it before the route runs. |
| `422` | `scenario_empty` | Caller | `scenario` was present but empty or only whitespace. |
| `422` | `scenario_too_long` | Caller | `scenario` longer than 20,000 characters. |
| `422` | `correlation_id_conflict`, `correlation_id_too_long` | Caller | As above. |
| `503` | `ai_unavailable` | Operator | Azure OpenAI is not configured. |
| `503` | `index_projection_unavailable` | Operator | As above. |
| `503` | `scenario_translation_unavailable`, `scenario_translation_empty` | Transient | The question could not be rendered into the processing language. |

There is no `409` here and no `decision_receipt_*`: this route holds no idempotency key and writes no receipt. A failed retrieval is simply safe to repeat.

`GET /api/policy-decisions/{decision_id}`:

| Status | `code` | Class | When |
|---|---|---|---|
| `401` | `authentication_required` | Caller | No authenticated caller. |
| `403` | `decision_not_readable` | Caller | Not the caller who made the decision, and not a policy author or administrator. |
| `404` | `decision_not_found` | Caller | No decision with that id. |
| `409` | `decision_in_progress` | Transient or operator | The receipt is reserved but not completed. Poll while the call may still be live; a persistent row after confirmed process loss is orphaned and has no automatic expiry or repair API. |
| `410` | *(the recorded failure code)* | Terminal | The decision failed and has no verdict to serve. |


### Examples

These examples use `$POLICY_SUBSCRIPTION_KEY` from the environment. A bearer token works identically — send `Authorization: Bearer $POLICY_API_TOKEN` instead of the header below. Never put a live credential in a snippet, a URL, a log or a page.

#### Full Decision

```bash
CORRELATION_ID="$(uuidgen)"
IDEMPOTENCY_KEY="$(uuidgen)"

curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/expense-policy/case" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $CORRELATION_ID" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  --max-time 120 \
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
    # A decision runs for tens of seconds. Size this from the p95 end of the
    # observed range with headroom, not from an average.
    timeout=120,
)
response.raise_for_status()
decision = response.json()

# Read `outcome` before either section. Only "answered" carries a verdict, and
# the section itself is null for `not_requested` and `not_evaluated` — so check
# the section for null before reading anything out of it.
outcome = decision["outcome"]

if decision["information"] is not None:
    print("What the policies state:", decision["information"]["answer"])

verdict = decision["verdict"]  # null for `not_requested` and `not_evaluated`

if verdict is None:
    if outcome["verdict"] == "not_requested":
        print("No verdict was asked for.")
    else:  # not_evaluated — nothing was evaluated, so there is no section at all
        print("Nothing was evaluated:", decision["retrieval"]["status"])
        print("  ", decision["retrieval"].get("reason"))
elif outcome["verdict"] == "answered":
    print("Verdict:", verdict["decision"])
    # Additive, and only ever present here: the determination stands, and these
    # are the conditions to confirm before acting on it.
    for item in verdict.get("verification_requirements", []):
        print(f"  check before acting — {item['label']}: {item['why_needed']}")
elif outcome["verdict"] == "missing_required_facts":
    print("No verdict yet — supply:")
    for item in verdict["missing_information"]:
        print(f"  {item['label']}: {item['why_needed']}")
else:
    # `not_settled_by_rules`, `no_rule_bears`, `declined`, `failed`: the rules
    # were read and no verdict followed. `decision` is empty by the invariant,
    # and `note` says why.
    print("No verdict:", outcome["verdict"], "—", verdict["note"])

for citation in decision["citations"]:
    print(citation["rule_id"], citation["serves"], citation["source"].get("text"))

# Verify the receipt was stored, and stored unchanged.
stored = requests.get(
    f"{BASE}/api/policy-decisions/{decision['decision_id']}",
    headers={"X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"]},
    timeout=30,
)
stored.raise_for_status()
assert stored.json()["decision_hash"] == decision["decision_hash"]
```

Reading `decision["verdict"]["decision"]` without branching on `outcome` is the one mistake this envelope exists to prevent, so the example does not do it — and it cannot be made silently, because `verdict` is `null` rather than an empty string when no verdict was reached. That null is also why the example tests the section itself before any branch that reads a field out of it: `not_evaluated` has no `verdict` object, so reaching for `verdict["note"]` on that path would raise rather than report the one outcome that says the corpus had nothing to answer from.

#### Decision Light

The same request, projected to the compact envelope. Note that it is *not* a cheaper call — it runs and stores the identical decision — so the timeout is the same.

```bash
LIGHT_CORRELATION_ID="$(uuidgen)"
LIGHT_IDEMPOTENCY_KEY="$(uuidgen)"

curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/expense-policy/case/light" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $LIGHT_CORRELATION_ID" \
  -H "Idempotency-Key: $LIGHT_IDEMPOTENCY_KEY" \
  --max-time 120 \
  -d '{"scenario": "A contractor submits a 180 EUR client dinner without an itemised receipt."}'
```

Keep `LIGHT_IDEMPOTENCY_KEY` with the request. A timeout retry must reuse that value so it observes the original decision instead of starting another one.

The response carries `decision_id`, `decision_hash`, `hash_basis` and `receipt_url` for the *full* receipt that was stored, so a client can render the compact answer now and fetch the complete audit record later from `receipt_url`.

#### Policy JSON

Retrieval only. No `Idempotency-Key`, no `reasoning_effort`, no `additional_instructions`, no `calling_system_identity` — none of them apply, because nothing is classified, adjudicated or stored.

```bash
curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/expense-policy/policies" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $(uuidgen)" \
  --max-time 60 \
  -d '{"scenario": "Expense claims for client entertainment without an itemised receipt."}'
```

```python
import os
import uuid

import requests

BASE = os.environ["POLICY_API_BASE"]

response = requests.post(
    f"{BASE}/api/policy-decisions/expense-policy/policies",
    headers={
        "X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"],
        "Content-Type": "application/json",
        "X-Correlation-Id": str(uuid.uuid4()),
    },
    json={"scenario": "Expense claims for client entertainment without an itemised receipt."},
    timeout=60,
)
response.raise_for_status()
retrieval = response.json()

# There is no verdict here and no receipt. Do not present this as a determination.
assert retrieval["schema_version"] == "policy_retrieval_v1"

for policy in retrieval["policies"]:
    identity = policy["policy"]
    slice_info = policy["match"].get("rule_selection")
    if slice_info:
        # The policy was read as a slice. Say so, with the numbers.
        print(
            f"{identity['provision_key']}: "
            f"{slice_info['selected_rules']} of {slice_info['total_rules']} rules selected"
        )
    else:
        print(f"{identity['provision_key']}: read whole")

usage = retrieval.get("token_usage") or {}
total = usage.get("total_tokens")
if total is not None:
    # A floor when any call reported no usage. Never render it as an exact total.
    prefix = "at least " if usage.get("calls_without_usage", 0) else ""
    print(f"tokens: {prefix}{total}")
```

#### Raw HTTP, behind a reverse proxy

A deployment may be reached through a gateway that mounts this API under a path prefix. **The prefix is part of the request target.** With a base URL of `https://policy.example.com/gateway`, the request line is:

```http
POST /gateway/api/policy-decisions/expense-policy/case HTTP/1.1
Host: policy.example.com
X-Policy-Subscription-Key: ${POLICY_SUBSCRIPTION_KEY}
Content-Type: application/json
X-Correlation-Id: <uuid>
Idempotency-Key: <uuid>

{"scenario":"Describe the situation you want decided.","reasoning_effort":"medium","calling_system_identity":"my-agent"}
```

Dropping the prefix and sending `POST /api/policy-decisions/...` is the single most common integration mistake against a proxied deployment, and it fails as a `404` from the *gateway*, with no `code` from this API to explain it. Build the target by joining your configured base URL with the path, and keep the base URL's own path segment — do not take only the host.

The same holds for the other three operations; only the path after the prefix changes:

```http
POST /gateway/api/policy-decisions/expense-policy/case/light HTTP/1.1
POST /gateway/api/policy-decisions/expense-policy/policies HTTP/1.1
GET  /gateway/api/policy-decisions/<decision-id> HTTP/1.1
```

`receipt_url` is returned **relative** for exactly this reason: an absolute URL built on the server would name the internal host rather than the gateway the caller used. Join it onto your own base URL the same way.

#### Receipt replay and hash verification

```bash
curl -sS "$POLICY_API_BASE/api/policy-decisions/$DECISION_ID" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  --max-time 30
```

Compare `decision_hash`, not bytes, and branch on the `hash_basis` the receipt names rather than assuming one:

```python
from policy_platform.contracts.case_decision import (
    CaseDecisionEnvelopeV2,
    compute_decision_hash,
    compute_decision_hash_v2,
    validate_receipt,
)

response = requests.get(
    f"{BASE}/api/policy-decisions/{decision_id}",
    headers={"X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"]},
    timeout=30,
)
response.raise_for_status()
stored = response.json()

receipt = validate_receipt(stored)
recomputed = (
    compute_decision_hash_v2(receipt)
    if isinstance(receipt, CaseDecisionEnvelopeV2)
    else compute_decision_hash(receipt)
)
assert recomputed == receipt.decision_hash, "stored content no longer matches its seal"
assert receipt.decision_hash == kept_hash, "this is not the receipt hash the caller kept"

# The basis names the preimage rule this hash was taken under. An independent
# verifier must branch on it; the bases are not interchangeable.
assert receipt.hash_basis in {
    "case_decision_v2_lang_verification",  # current, decisions under the language boundary
    "case_decision_v2_verification",       # current
    "case_decision_v2_lang",               # historical
    "case_decision_v2",                    # historical
    "case_decision_v1",                    # historical, pre two-track envelope
}
```

## Conventions

- **JSON in, JSON out**, except document upload (`multipart/form-data`) and export endpoints (which return JSON, JSONL or CSV as an attachment, selected with a `format` query parameter). See [Capabilities](../README.md#capabilities) for what each output is for.
- **Policy sets are addressed by `key`** — a stable slug such as `expense-policy` — while most other resources use UUIDs. A project's UUID `id` is trace identity and its `name` is a display string; neither is ever a path segment.
- **AI endpoints require configuration.** Azure OpenAI is a product requirement, not an option: if it is not configured, every AI route returns `503` before doing any work and the platform is in a degraded diagnostic mode. Retrieval- backed grounding additionally needs `AZURE_SEARCH_*`. Check `GET /api/ai/status` first — it reports both `ai_enabled` and `search_enabled`.
- **Role-based access control, off by default.** All 108 operations are classified into a capability band — read, use, author, administer — and one dependency enforces the whole registry, so a route cannot be reachable without a classification. It is disabled unless `RBAC_ENABLED` is set; see [configuration](configuration.md) for what to set up first. When enabled, an insufficient role gets `403` with a structured `detail` carrying `code`, `required_role` and `band` rather than a sentence, so clients can render their own wording. Note that the bands do not follow HTTP verbs: many `POST /api/ai/*` routes change nothing and are readable by any role, while a few that write nothing — the ones that exist to compose an edit — require an author.
- **Four operations require authentication regardless of that flag.** `POST /api/policy-decisions/{project_key}/policies`, both full and light case `POST`s, and `GET /api/policy-decisions/{decision_id}` refuse an unauthenticated caller with `401` even where global enforcement is off. The retrieval route exposes filtered policy JSON; the other three write, project, or serve an audited receipt that must name who asked. Nothing else bypasses the flag.
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
