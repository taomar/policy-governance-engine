# External consumption

This page is for someone building a system that needs a governed answer — an agent, a Copilot extension, a workflow step, a service. It explains what to call, what you get back, and what you may and may not rely on. The endpoint reference is in [API → audited external decisions](api.md#audited-external-decisions-policy-decisions); this page is the integration-shaped view of the same two operations.

## What is on offer

One audited channel:

```
POST /api/policy-decisions/{project_key}/case   → decide, and record
GET  /api/policy-decisions/{decision_id}        → read the receipt back
```

You send a case in natural language. The published policies bearing on it are retrieved from that project's own policy index, the rest are discarded, and the retained records are evaluated. You receive a **receipt** — `case_decision_v1` — carrying a decision identity, the authenticated caller, the exact published version that decided, what was retrieved and what was set aside, the decision, the rules it cited with their verbatim source text, and an integrity seal. The same receipt is stored and can be read back by id.

That is the whole point of this seam. The older in-product route, `POST /api/ai/policy-sets/{key}/case-answer`, answers a reviewer looking at a screen: it persists nothing and returns no identity, so nothing correlates a caller's request to a server-side record. It remains available and unchanged for the product's own use. It is not the integration contract.

## There is no packaged connector

There is **no** native Copilot plugin, no Power Platform / Logic Apps custom connector package, no agent-framework tool package and no client SDK shipped from this repository. Integration is plain REST over HTTP with JSON, described by the API's own OpenAPI document at `{base}/openapi.json` and browsable at `{base}/docs`.

That is enough for every one of those platforms, because each of them can consume an OpenAPI description or make an HTTP call — but the mapping is yours to author and yours to maintain. Nothing here is certified, published to a marketplace, or version-managed on your behalf.

Practically:

| If you are building | Do this |
|---|---|
| An agent or Copilot-style tool | Register one tool per operation from the OpenAPI description. Give the tool the project key, and make the tool's own description say that `decision_status` must be read before `decision.verdict`. |
| A workflow or automation step | An HTTP action carrying your credential, `X-Correlation-Id` from the workflow run id, and `Idempotency-Key` from the workflow's own retry-safe key. |
| A service or backend | Call it directly. Persist `decision_id`, `correlation_id` and `decision_hash` alongside whatever your system decided as a result. |

## Identity: use the key

Route on the project's stable `key`. The receipt also returns the project's UUID `id` and its display `name` — the first is trace identity for support and audit conversations, the second is for showing a human. Neither is ever a path segment: a URL built from a display name breaks the day someone renames the project.

## Authentication

Both operations require a **proved identity** and refuse an unauthenticated caller with `401`, independently of whether the deployment has enabled global role enforcement. A receipt that cannot name who asked for it is not a receipt.

Two credentials are accepted.

### A bearer token

`Authorization: Bearer <token>`, issued by the OIDC issuer the API validates. Use this when the caller is a person, or when you need per-caller attribution, expiry, or revocation without restarting the API. See [Configuration → signing in](configuration.md#signing-in).

### A subscription key

`X-Policy-Subscription-Key: <key>`, for a non-interactive caller — an agent, a workflow, a scheduled job — that has no user and no issuer.

```bash
export POLICY_SUBSCRIPTION_KEY="<the key your operator issued>"
curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/$PROJECT_KEY/case" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -d '{"scenario": "Describe the situation you want decided."}'
```

Know exactly what you are holding:

- **It is one operator-configured key**, and this increment ships one. Every caller presenting it resolves to the same configured identity and role, so it groups callers rather than distinguishing them. Two systems sharing a key are indistinguishable in every receipt they produce; if you need to tell them apart, use tokens.
- **Rotation is: the operator changes `POLICY_SUBSCRIPTION_KEY` and restarts the API.** There is no overlap window, no second key, no revocation list and no expiry. In-flight callers get `401` during the restart.
- **A wrong key is a `401 subscription_key_rejected`**, never a silent downgrade to an anonymous request. An integration with a stale key fails immediately rather than appearing to work.
- **A valid bearer token wins over a key** if you send both — it names an individual and can be revoked, and the key does neither. A token that is presented and rejected still ends the request; a subscription key will not rescue it.
- **It is not an Azure or API Management subscription key.** Nothing here integrates with APIM, Azure subscriptions or any gateway product. It is a pre-shared value this application compares against its own configuration.

### Where the credential may live

In your service's secret store, and in the request. The examples throughout this documentation read it from `$POLICY_SUBSCRIPTION_KEY` and never contain a literal value, and the in-product **Call from your app** panel does the same — it has no access to the operator's key and never displays one.

**Do not put a subscription key in a browser client.** It is a shared credential, and a browser application ships its configuration to everyone who loads the page; anything Vite inlines under a `VITE_` name is in the built bundle. If a browser needs a decision, put your own server in front of this API and let it hold the credential.

The local playground at `apps/consume-demo` deliberately breaks that rule and is the one place it is acceptable: it exists to demonstrate the exact request an integrator must reproduce, against a local API and a key an operator generated for local use. It therefore shows the key in clear, includes it in its Raw HTTP tab, and can be prefilled from a git-ignored `.env.local`. It is a demonstration, not a template — running `npm run build` there produces a bundle containing whatever key was configured, which is why `dist/` is git-ignored and why the committed `.env.example` leaves the value empty.

A receipt may be read back by the caller who made the decision, or by a policy author or administrator. A service that calls under its own principal — token or key — can always verify its own receipts.

## Validation the API performs before it decides

A request that could never be stored is refused with `422` before any receipt is reserved and before the model is called, so a permanent input fault never comes back as a retryable `503`:

| Field | Limit | Code |
|---|---|---|
| `X-Correlation-Id`, `correlation_id` | 200 characters | `correlation_id_too_long` |
| `Idempotency-Key` | 200 characters | `idempotency_key_too_long` |
| `calling_system_identity` | 200 characters | `calling_system_identity_too_long` |
| `provision_id` | 200 characters | `provision_id_too_long` |
| `reasoning_effort` | `low`, `medium` or `high` | `reasoning_effort_invalid` / `reasoning_effort_too_long` |
| `additional_instructions` | 2000 characters after normalisation | `additional_instructions_too_long` |

`reasoning_effort` is refused rather than silently coerced: a receipt recording `reasoning_effort_requested: "maximum"` for a call that ran at `medium` would disagree with what happened.

## Reading a response correctly

1. **`decision_status` first.** Seven values, one of which — `answered` — carries a verdict. `not_evaluated` means retrieval produced no evaluation at all, which is a legitimate `200` with a full receipt. A client that reads `decision.verdict` without branching on the status will silently present an empty string as an answer.
2. **`citations` are the evidence.** Each names a rule and, where the source text was stored, the verbatim sentence behind it. `grounding.fabricated_citations` reports the citations the fabrication guard refused; show that you refused them rather than hiding it.
3. **`retrieval` is disclosure, not decoration.** It says how many published policies were considered, retained and discarded, and why. Surface it. An answer drawn from a shortlist should be presented as one.
4. **No policy record is inlined.** Every policy reference carries a `payload_url` to the lean published record; fetch it if you need the full content.

## Correlation, idempotency and retries

- Send `X-Correlation-Id` (or `correlation_id` in the body — not both with different values) so both sides can name the same event. It is echoed in the response body and header.
- Send `Idempotency-Key` to make a retry safe. It is bound to your authenticated principal, the project, and a canonical hash of the request including your caller guidance. Replaying the same request returns the original receipt with the same `decision_hash` and no second model call; changing the request under the same key is a `409`.
- A case takes on the order of ten seconds. Set your timeout accordingly and do not build a retry loop without an idempotency key.

## What a caller may steer

`additional_instructions` (≤ 2000 characters after normalisation) shapes **how the explanation is presented** — what to emphasise, how long to be, what format to use. It cannot change which policies were retrieved, what a rule means, the `decision_status`, the verdict, the citation requirement, or the prohibition on drawing on anything outside the published records. It never reaches retrieval, so it cannot steer which policies are considered. Guidance asking for any of that is ignored for that part and `decision.note` says so.

The server's own instructions are not returned and are not editable. `trace.prompt_version` and `trace.instruction_profile` name them so a receipt can be traced to the framing that produced it, without that framing becoming a public surface someone could edit.

If your product exposes this field to an end user, show the constraint alongside it. Do not offer an "edit the system prompt" affordance; there is nothing to unlock.

## What `decision_hash` is worth

It is an **integrity seal** over a fixed, documented subset of the receipt — enough to prove that *this* receipt's decision-defining content has not been altered since it was written. Store it with your own record and compare it against `GET /api/policy-decisions/{decision_id}` whenever you need to show the decision is unmodified.

It is **not** a determinism or replay guarantee. A language model is in the path, so the same scenario put twice to the same published version may legitimately produce different prose and a different hash. Do not build a control that expects two independent calls to seal identically; use an `Idempotency-Key` if you need the same receipt back.

## What this contract does not claim

- No accuracy, precision or benchmark claim is made about the answers. The receipt tells you what was retrieved, what decided and what was cited so a human can check it — that is the guarantee on offer.
- The evaluation is model-mediated. The platform's deterministic decision path is a different endpoint (`POST /api/evaluations`) taking structured facts and returning a `result_hash`; see [API](api.md). Use it when you need reproducibility rather than natural language.
- Nothing here is a substitute for the published policy itself, which remains the authoritative contract.

## Related pages

- [API](api.md#audited-external-decisions-policy-decisions) — the full endpoint, envelope and error reference.
- [User guide → serve decisions to other systems](user-guide.md#14-serve-decisions-to-other-systems) — the in-product **Call from your app** panel and the external playground.
- [Architecture](architecture.md#one-decider-two-surfaces) — why there is one decider behind two surfaces.
- [Known limitations](known-limitations.md) — retention of stored scenarios, the RBAC posture, and what is not shipped.
