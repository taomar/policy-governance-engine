# External consumption

This page is for someone building a system that needs governed policy data or a governed answer — an agent, a Copilot extension, a workflow step, a service. It explains what to call, what you get back, and what you may and may not rely on. The endpoint reference is in [API → audited external decisions](api.md#audited-external-decisions-policy-decisions); this page is the integration-shaped view of the same four operations.

## What is on offer

Three response modes, plus receipt read-back:

```
POST /api/policy-decisions/{project_key}/case      → filtered policies + reasoning + receipt
POST /api/policy-decisions/{project_key}/case/light → same stored decision, compact fixed schema
POST /api/policy-decisions/{project_key}/policies  → filtered policy JSON only
GET  /api/policy-decisions/{decision_id}           → read a stored receipt back
```

The two decision operations use the same approved index, language boundary, selector, duplicate collapse, large-policy rule slicing, payload fitting, classifier, and gathers. Decision Light is an output projection, not a cheaper or different decision. Policy JSON stops before classification and adjudication. Their policy cuts differ deliberately:

- **Decision JSON — `case_decision_v2`.** Direct policy relevance is primary. A clear semantic score elbow sets a smaller count: a strong lead controls identity directly, while a moderate lead uses symmetric RRF over hybrid and semantic ranks of the same direct policy documents. Explicit query aspects omitted by that cut can add a policy only when its English indexed heading names the aspect and its semantic score clears the disclosed coverage floor. A flat semantic ranking preserves the hybrid direct-policy pool for the final five-policy duplicate/diversity budget. A strong rule-only match may rescue its parent, but rule documents never enter the direct fusion and rule scores are never added to policy scores. The response carries information, a verdict when one is reached, explanations, evidence, operational stage timings, an integrity hash, and a stored receipt id.
- **Decision Light — `case_decision_light_v1`.** The exact same selection and decision are made and the same full receipt is stored. The response keeps only response type, essential ids, project/version, request hash, outcomes, information/verdict with explanation and missing/check fields, cited policies, necessary citations, total and stage timing, service-reported token usage, compact trace data, and the integrity seal.
- **Policy JSON — `policy_retrieval_v1`.** Precision is favoured because there is no gather to reject filler. Policy documents are semantically reranked, the set is cut at a meaningful score gap (or bounded to three when no gap exists), and selected large policies are then sliced by rule. The response carries `retrieval`, `policies`, `size`, and language provenance. It has no decision id, verdict, explanation, synthesized citations, hash, or receipt URL.

Use Decision JSON when this platform should make and record the governed determination. Use Policy JSON when your own agent should reason over the approved, filtered records.

The older in-product route, `POST /api/ai/policy-sets/{key}/case-answer`, answers a reviewer looking at a screen and is not the external integration contract.

## A case asks for information, a verdict, or both

This is the thing to design your integration around, and it is not obvious from the endpoint name.

A question put to a governed policy can ask for two different things, and they are independent:

- **information** — *what do the policies say about X?*
- **verdict** — *given these facts, how does it come out?*

One classifier call reads your question for both, and each requested track is gathered. So `outcome` has two values, and the receipt has two nullable sections:

```jsonc
{
  "asked":   { "information_requested": true, "verdict_requested": true, "classification_reasoning": "…" },
  "outcome": { "information": "answered", "verdict": "missing_required_facts" },
  "information": { "answered": true,  "answer": "…", "citations": [ … ] },
  "verdict":     { "reached": false, "decision": "", "missing_information": [ … ] }
}
```

Three consequences worth building against:

1. **You do not declare what you want.** There is no `needs` field and no mode flag. A caller who could declare "give me a verdict" could choose the shape of their own answer, which is exactly what `additional_instructions` is forbidden from doing; putting it in a different field would not make it a different thing. `asked` shows you the reading, with the classifier's own reasoning, so you can display or log the routing.
2. **A blocked verdict does not cost you the information.** If the case cannot be decided until facts are supplied, `verdict.status` is `missing_required_facts` — and if you also asked what the policies say, `information` is populated and answered anyway. This was the concrete failure of the previous contract: such a caller got a status, a list of bare strings, and nothing else.
3. **A section you did not ask for is `null`, not empty.** `outcome.verdict: "not_requested"` with `verdict: null` cannot be rendered as "verdict: —". An empty string can.

## There is no packaged connector

There is **no** native Copilot plugin, no Power Platform / Logic Apps custom connector package, no agent-framework tool package and no client SDK shipped from this repository. Integration is plain REST over HTTP with JSON, described by the API's own OpenAPI document at `{base}/openapi.json` and browsable at `{base}/docs`.

That is enough for every one of those platforms, because each of them can consume an OpenAPI description or make an HTTP call — but the mapping is yours to author and yours to maintain. Nothing here is certified, published to a marketplace, or version-managed on your behalf.

Practically:

| If you are building | Do this |
|---|---|
| An agent or Copilot-style tool | Register the three `POST` operations as separate tools. Describe `/case` as the full audited decision, `/case/light` as its compact fixed-schema response, and `/policies` as retrieval-only; never let the last tool's output be presented as a verdict. |
| A workflow or automation step | An HTTP action carrying your credential, `X-Correlation-Id` from the workflow run id, and `Idempotency-Key` from the workflow's own retry-safe key. |
| A service or backend | Call it directly. Persist `decision_id`, `correlation_id` and `decision_hash` alongside whatever your system decided as a result. |

### Writing the tool descriptions

If a model chooses between these operations, the description it reads is the whole control. The failure to design against is not a wrong endpoint — it is an agent that calls `/policies`, receives approved policy text, and narrates a verdict the platform never made and never sealed.

Three rules make that hard to do by accident:

- **Name the output in the description, not the action.** "Returns the governing policy records, with no determination and no receipt" is a boundary. "Look up policies" is an invitation to summarise them into an answer.
- **Give the retrieval tool an explicit prohibition.** Something to the effect of *do not state whether the situation is permitted, compliant or approved from this output; call the decision tool for that.* A tool description is the only place that constraint can live, because the endpoint cannot tell what its caller will do with the JSON.
- **Do not offer `/case` and `/case/light` as a fast/slow pair.** They cost the same. The only reason to choose Light is that the caller wants a small fixed-shape response; if the agent may later need evidence, it already has `receipt_url`. Describing Light as "quicker" will make a model choose it for latency it does not get.

A workable split:

| Tool | Description to give the model |
|---|---|
| `get_governing_policies` | Retrieves the approved policy records that bear on a described situation. Returns policy text and rule selection only. **Does not decide anything.** Do not present its output as a ruling, an approval, or a compliance answer. |
| `decide_case` | Puts a described situation to the approved policies and returns an audited determination with citations, an integrity hash, and a stored receipt id. Use when the caller needs an answer that can be cited and verified later. |
| `decide_case_compact` | The same audited determination as `decide_case`, returned in a compact fixed schema. Same cost and same latency. Use only when the caller needs a small response shape. |
| `get_decision_receipt` | Reads back a previously stored decision by its id, for verification. Makes no new determination. |

## Base URL and path prefixes

Everything here is relative to a base URL you configure. Locally that is `http://127.0.0.1:8010`. In the Azure topology it is the public web FQDN, whose nginx reverse-proxies `/api` to an API container that is never addressed directly.

**If your base URL carries a path of its own, that path is part of every request.** A gateway that mounts this API at `https://policy.example.com/gateway` must be called as:

```
POST /gateway/api/policy-decisions/{project_key}/case
```

not `POST /api/policy-decisions/...`. Build the target by joining your configured base URL to the path and **keep the base URL's own path segment** — taking only the host is the mistake, and it fails at the gateway as a bare `404` with no `code` from this API to explain it. The playground's Integration Guide examples perform this join. Its request inspector does not: that tab assumes an origin-only API base and emits a root-relative `/api/...` target.

`receipt_url` comes back **relative** for the same reason: an absolute URL composed on the server would name a host the caller never used. Join it onto your own base URL exactly as you joined the path.

## Identity: use the key

Route on the project's stable `key`. The receipt also returns the project's UUID `id` and its display `name` — the first is trace identity for support and audit conversations, the second is for showing a human. Neither is ever a path segment: a URL built from a display name breaks the day someone renames the project.

## Authentication

All four operations require a **proved identity** and refuse an unauthenticated caller with `401`, independently of whether the deployment has enabled global role enforcement. The policy route exposes approved records; the decision routes create or expose receipt data.

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

curl -sS -X POST "$POLICY_API_BASE/api/policy-decisions/$PROJECT_KEY/policies" \
  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \
  -H "Content-Type: application/json" \
  -d '{"scenario": "Describe the situation whose governing policies you need."}'
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
| `scenario` | 20,000 characters | `scenario_too_long` |
| `Idempotency-Key` | 200 characters | `idempotency_key_too_long` |
| `calling_system_identity` | 200 characters | `calling_system_identity_too_long` |
| `provision_id` | 200 characters | `provision_id_too_long` |
| `reasoning_effort` | `low`, `medium` or `high` | `reasoning_effort_invalid` / `reasoning_effort_too_long` |
| `additional_instructions` | 2000 characters after normalisation | `additional_instructions_too_long` |

`reasoning_effort` is refused rather than silently coerced: a receipt recording `reasoning_effort_requested: "maximum"` for a call that ran at `medium` would disagree with what happened.

## Reading a response correctly

1. **`outcome` first, one value per track.** `outcome.information` and `outcome.verdict` each carry that track's status, plus `not_requested` (you did not ask; the section is `null`) and `not_evaluated` (nothing was evaluated at all — a legitimate `200` with a full receipt; both tracks report it together). Only `outcome.verdict: "answered"` carries a determination.
2. **The verdict invariant.** `verdict.decision` is non-empty *if and only if* `verdict.reached` is true *if and only if* `verdict.status` is `answered`. So **"not compliant", "denied" and "no" are reached verdicts** and live in `decision`; a case that could not be decided leaves `decision` empty. Never render "no verdict" and "the answer is no" the same way.
3. **`missing_information` is what to ask the user next.** When a verdict is blocked, each item carries the `fact`, a `label` to show, `why_needed`, and `required_by_rule_ids`. `missing_required_facts` is the same facts as a flat list, kept for clients that already read it.
4. **`verification_requirements` is what to confirm before acting, and is not the same thing.** On a **reached** verdict it carries conditions — a current balance, an approval, a roster, a date — that do not change the determination but stand between it and acting on it. Same item shape, same closed catalogue, same rule-id filtering. It is non-empty only when `reached` is true, so it can never overlap `missing_information`. Render it as a separate "check before acting" section: do **not** show it as missing facts, and do **not** downgrade the verdict because it is present. It defaults to `[]`, so a client that ignores it is unaffected.
5. **`citations` are the evidence.** The top-level list is deduplicated by `rule_id` and tagged `serves: ["information"]`, `["verdict"]` or both — a rule cited by both halves appears once, not twice. Each names a rule and, where the source text was stored, the verbatim sentence behind it. Each section's `grounding.fabricated_citations` reports the citations the fabrication guard refused; show that you refused them rather than hiding it.
6. **`retrieval` is disclosure, not decoration.** Several narrowings are reported, not one, and they are different claims. Search sets policies aside by *relevance* (`outside_budget`, `no_retrieval_match`). Whole policies that will not fit together are set aside by *size* (`outside_payload_budget`, counted in `policies_over_payload_budget`). A policy holding more rules than one case can read is narrowed to a *slice of its rules* — its `considered` entry carries `rule_selection`, and `retrieval.policies_rule_sliced` counts them. Surface all of them. **Never present a sliced policy as though it was read whole** — the disclosure a user is owed reads "Table of Violations and Penalties · 74 rules · 15 selected for this case".
7. **Tell "the same policy twice" apart from "the same thing said twice".** They are two different findings and only one of them asserts sameness:
   - `discard_reason: "duplicate_policy_content"` (counted in `retrieval.policies_duplicate_collapsed`) means the corpus really held that policy twice — identical in every sentence, effect, date, scope, carve-out and supersession. It is the **only** discard that claims two policies are the same, and the only one whose terms still reached the model: `duplicate_of_provision_key` names the policy that was read in its place. Render it as "already covered by X", never as "not read".
   - `retrieval.policies_diversity_deferred`, with `retrieval.policy_selection_order: "relevance_then_normative_content_v1"`, means something weaker and must be rendered differently. Candidates requiring the same thing were *ordered* so that the highest-ranked is offered before any second member of the group. The count is what that ordering **cost**: candidates that ranked inside the retention budget and were displaced out of it. One that ranked outside the budget anyway is not counted, so `0` means the ordering changed nothing. A deferred candidate is **not** a duplicate, carries no `duplicate_of_provision_key`, keeps its own rank and score, and carries the ordinary `outside_budget`. Do not label it a duplicate anywhere in your UI.

   Note the consequence for `outside_budget`: it means *did not place inside the retention budget*, by rank **or** by that ordering — not *ranked below it*. If you show a rank-3 policy outside the budget beside a retained rank-5 one, `policy_selection_order` and `policies_diversity_deferred` are the explanation to show with it.
8. **Repeated source text is not duplicate rule semantics.** One sentence often states several obligations and is extracted into one rule each, so four genuinely different rules — one permitting, one forbidding, one obliging, one routing — can rest on a single passage. The platform never collapses those. What it does report is `rule_selection.duplicate_rules_collapsed` (rules that were *exactly* identical to an earlier rule of the same policy, by the full comparison) and `rule_selection.represented_rule_ids` (unread ids that are exact copies of ones that were read, so `rules_discarded` is not misread as "unknown content"). Separately, among rules that matched, the best of each distinct source passage is taken before a second rule from a passage already covered — selection priority, not a claim of equality. Do not write UI copy that infers "duplicate rule" from two rules quoting one sentence.
9. **The rule budget bounds the record.** `rule_selection.selected_rules` — the total put in front of the model, **including** the `context_rules_added` that followed a selected rule in — never exceeds `retrieval.selected_rule_budget` (15). Context fills only slots the selection left unused; anything that found no slot or no room is named in `context_rules_omitted`. `selected_rules` always equals the length of `selected_rule_ids`, and `rules_discarded` is always `total_rules` less `selected_rules`.
10. **Watch for `rule_selection.method`.** `hybrid_rule_v1` means the rule index took part and a rule beyond what its policy's own document could carry was reachable. `scenario_relevance_v3` means rule documents exist but the query against them failed recoverably, so the selection ran without that ranking — still a real selection over the right corpus, made with one ranking missing. `scenario_relevance_v2` means the rule index was not consulted. `document_order` means no rule matched your question's terms at all and a bounded sample was read; an answer resting on such a policy deserves more scrutiny. At retrieval level, `rule_index_state` says whether rule search was available; `rule_rescued_policies` says how many parents it independently rescued through the final budget. `policies_elevated_by_rule` is the compatibility alias. No rule score is added to a direct policy score.
11. **No policy record is inlined.** Every policy reference carries a `payload_url` to the lean published record; fetch it if you need the full content — including the rules a slice did not read.
12. **Your question does not have to be in English; your citations will not be translated.** Every stage of the decision runs in English, so a question in another language is rendered in on the way in and the answer's **prose** is rendered back on the way out. What is *never* translated: your own `scenario` and `additional_instructions` (and their hashes, which the idempotency binding is taken over), every machine-readable value, and **every verbatim source sentence**. `citations[].source.text` is the document's own words in the document's own language — a translated quotation is not a quotation. A receipt holding an Arabic quotation beneath an Arabic explanation that was reasoned in English is the intended shape; do not "fix" it by translating the quote in your UI, and do not present a translated quote as the source.

    English input does not bypass the model boundary. The normaliser's contract requires it to return already-English text unchanged, and the original `request.scenario` is always preserved, but byte equality is not independently enforced. Read `language.processing_scenario` to see what retrieval and adjudication actually consumed; its hash is sealed. The boundary is not intended as a query rewriter, so callers must not rely on it to repair typos or infer an unstated concept.

    Read the `language` block rather than guessing: `response_language` says what the prose is in, and `output_rendering_state` tells `rendered` from `target_unknown` (no usable target tag was observed, so the prose comes back as it was reasoned) and from `not_required`. If you sent presentation guidance, check `guidance_rendering_state` for `unrendered_dropped` — your guidance could not be carried across and was dropped rather than applied un-rendered. The decision is unaffected either way, but the wording you asked for was not applied.
13. **Check `hash_basis` before verifying.** Current decisions seal under `case_decision_v2_verification`, or — when the decision was made under the language boundary — under `case_decision_v2_lang_verification`, which covers everything the first does **plus** `processing_scenario_hash` (the English text actually adjudicated) and the whole `language` block. Both names record that `verification_requirements` are sealed. Historical receipts can name `case_decision_v2_lang`, `case_decision_v2`, or `case_decision_v1`. Verify against the basis the receipt names; do not assume one, and do not treat the bases as interchangeable.
14. **Check `schema_version` if you hold old data.** New decisions are always `case_decision_v2`. A receipt stored before the two-track redesign — or replayed under an idempotency key from then — is served as `case_decision_v1`, in the shape it was written in, because re-projecting a stored receipt would mean inventing content that decision never had. Such receipts carry no `rule_selection`: rule-level retrieval did not exist when they were written, and their policies really were read whole. Receipts written before the language boundary carry no `language` block.

For free-form callers, preserve these additional boundaries:

- **Be explicit about the policy subject.** The language boundary is instructed not to rewrite already-English input, but that instruction is model-mediated rather than a byte-equality guard. In live tests, typos and colloquial wording survived and the boundary did not infer that “my bro owns a bidder” means conflict of interest or that “laptop gone” means loss or theft; a heavily misspelled question retrieved a generic policy in place of the specific one. Inspect `language.processing_scenario`, the returned policy identities, and citations. A non-answer over the wrong retained policy is not evidence that the whole corpus is silent.
- **Do not read a non-final status as a deterministic block.** Directly contradictory facts have been observed to produce a safely blocked run on one call and a conditionally scoped answer on another — both grounded, both citing the bearing policy, but with different machine statuses. Treat `answered` as actionable only within the scope stated in `decision` and `explanation`, and honour every `verification_requirement`. If contradictory facts must deterministically block, validate them in your own system or use the structured `POST /api/evaluations` path.
- **Split independent topics into independent calls.** One case can retrieve and cite several policy areas, but the fixed receipt still has one information outcome and one verdict outcome for the whole request. It cannot express "leave blocked, appraisal answered" as independent per-topic statuses. If leave and appraisal drive different actions, send two calls so each has its own status, idempotency key, and receipt.
- **Safety and cost are different gates.** An irrelevant question fails safely — no cited policy, no answer, no verdict — but retrieval and classification still run. One ambiguous off-topic control consumed about 75,000 service-reported tokens before both tracks concluded no rule bore. Do not expose this as a general-purpose assistant, and monitor `trace.token_usage` alongside `outcome`.

Each of these is recorded with its measured evidence in [known limitations → before relying on this build](known-limitations.md#before-relying-on-this-build).

## Correlation, idempotency and retries

- Send `X-Correlation-Id` (or `correlation_id` in the body — not both with different values) so both sides can name the same event. It is echoed in the response body and header.
- Send `Idempotency-Key` to make a retry safe. It is bound to your authenticated principal, the project, and a canonical hash of the request including your caller guidance. Replaying the same request returns the original receipt with the same `decision_hash` and no second model call; changing the request under the same key is a `409`.
- A decision is a multi-call model operation and runs for **tens of seconds**. A mixed question runs both gathers concurrently, so it costs roughly one gather's latency rather than two — but size your timeout for the slow end, not the average, and do not build a retry loop without an idempotency key.

## Timeouts and recovery

**Budget generously.** Across the evaluation matrices run against this release, end-to-end decision times sat around **p50 19–32 s and p95 35–45 s**, with individual calls above that. The variation between matrices reflects the scenarios in them, not the operation called: `/case/light` runs and stores the *same* decision as `/case` and is not a faster adjudicator — only its response is smaller. The low end is the one matrix re-measured after retrieval's index checks and query embedding were made concurrent; the upper figures predate that change and are now upper bounds. These are observations over a fixed scenario set, not a service level objective; no latency guarantee is offered.

A workable default is **120 s** for `/case` and `/case/light`, **60 s** for `/policies` (which makes no gather calls, though it still normalises the query through the inbound language boundary), and **30 s** for a receipt replay (which makes no model call at all).

**If a decision is too slow for your use, `reasoning_effort` is the lever — not the scenario length.** Decision time is dominated by how much the model reasons, not by how much policy text was retrieved, so shortening the question or narrowing the corpus reduces tokens and cost without reliably reducing wall-clock time. `reasoning_effort: "low"` genuinely trades adjudication depth for speed, and on the one matrix where it was measured it moved the **tail** rather than the middle — p95 down 22%, p50 unchanged, because the median request had little reasoning to cut. [API → what `low` measured](api.md#what-low-measured-on-one-corpus) has the figures. Treat it as a trade, validate it against your own scenarios, and remember the receipt records only what you *asked* for, as `request.reasoning_effort_requested` — a deployment may reject the parameter and retry without it.

**Recovery depends on what the operation persists**, and the three differ:

| Operation | On timeout | Why |
|---|---|---|
| `/case` | The decision may already have been made and stored. If you sent an `Idempotency-Key`, replay it: you get the original receipt, not a second decision. Without one, look the decision up by id if you captured it, or accept that you cannot tell whether it ran. | The receipt is reserved and committed *before* the model is called, so evidence that the call was made survives the client giving up. |
| `/case/light` | Identical to `/case` — and the recovered record is the **full** `case_decision_v2` receipt, because that is what was stored. A Light client should render that recovered full receipt rather than remaining in light-response state or reporting a failure. | Light is a projection of the stored decision, not a different decision. There is no light-shaped thing in storage to recover. |
| `/policies` | Just retry. Nothing was reserved, nothing was decided, nothing was written. | Retrieval is side-effect free. |

`decision_in_progress` reports a database state, not process liveness. A live request normally owns the `pending` row, so retry the same key while it may still be running. There is no lease, heartbeat, stale-row timeout, or startup reconciliation for decision receipts. If the process is known to have stopped and the row remains pending, escalate to the operator; starting a new key while liveness is uncertain can create a second decision.

Do not mix the two recovery paths: a timeout in one response mode must not surface the other mode's data or wording. Recovering a Full receipt and labelling it "light response unavailable" tells a user their decision failed when it succeeded.

**If you need exactly-once behaviour, you must send an `Idempotency-Key` on the first attempt.** Retrying a timed-out decision under a *fresh* key produces a second, independent decision with its own receipt, its own hash, and its own token cost — the platform has no way to recognise it as the same request, and deduplicating by scenario text alone would be wrong, because asking the same question twice is something people legitimately do.

## What a caller may steer

`additional_instructions` (≤ 2000 characters after normalisation) shapes **how the explanation is presented** — what to emphasise, how long to be, what format to use. It cannot change which policies were retrieved, **which tracks run**, what a rule means, either track's status, the verdict, the citation requirement, or the prohibition on drawing on anything outside the published records. It never reaches retrieval or the classifier, so it can steer neither which policies are considered nor what your question is read as asking for. Guidance asking for any of that is ignored for that part and the affected section's `note` says so.

The server's own instructions are not returned and are not editable. `trace.prompt_version` and `trace.instruction_profile` name them so a receipt can be traced to the framing that produced it, without that framing becoming a public surface someone could edit. `trace.stage_latency_ms` carries diagnostic wall-clock measurements for retrieval and gather stages, and `trace.token_usage` sums the counts reported by chat and embedding calls. Missing usage remains `null`, never an estimate. If `calls_without_usage` is nonzero, any numeric total is a lower bound rather than an exact total and must be shown as *at least N*. Both are execution metadata, not decision content, so they are deliberately excluded from `decision_hash`. Policy JSON carries the same usage report at top level because it has no decision trace, and its own `stage_latency_ms` beside it — additive, optional, and reporting only the stages that route actually runs. The field-level reference — every stage key, why the stage times must not be summed, and which durations a receipt can never carry — is in [API → timing and token telemetry](api.md#timing-and-token-telemetry).

If your product exposes this field to an end user, show the constraint alongside it. Do not offer an "edit the system prompt" affordance; there is nothing to unlock.

## What `decision_hash` is worth

It is an **integrity seal** over a fixed, documented subset of the receipt — enough to prove that *this* receipt's decision-defining content has not been altered since it was written. Store it with your own record and compare it against `GET /api/policy-decisions/{decision_id}` whenever you need to show the decision is unmodified.

**Compare the hash, not the bytes.** The replay is *content-equivalent*, not byte-identical: every field carries the value it was written with and `decision_hash` verifies against the replayed content, but JSON key order may differ from the original response. A control that diffs response strings will report false mismatches; compare `decision_hash`, or compare parsed values.

It is **not** a determinism or replay guarantee. A language model is in the path, so the same scenario put twice to the same published version may legitimately produce different prose and a different hash. Do not build a control that expects two independent calls to seal identically; use an `Idempotency-Key` if you need the same receipt back.

## Security and privacy obligations

Calling this API puts you in possession of two things that carry obligations: a credential, and an audit record containing whatever your users typed.

**The credential.**

- Keep it in your service's secret store, injected as an environment variable or a managed secret reference. Never in source, never in a URL, never in a log line, never in a browser bundle. Anything a build tool inlines under a client-visible name — a Vite `VITE_` variable, for example — ships to everyone who loads the page.
- The subscription key is one shared value with no expiry and no revocation list. Rotation means an operator changes `POLICY_SUBSCRIPTION_KEY` and restarts the API, and in-flight callers get `401` during that restart. Plan for a brief failure window rather than a clean cutover.
- Prefer a bearer token wherever you need per-caller attribution, expiry, or revocation without a restart. Two systems sharing one subscription key are indistinguishable in every receipt they produce.
- If a browser needs a decision, put your own server in front of this API and let it hold the credential.

**The audit record.** Every decision call writes an append-only receipt that stores, in clear:

- the caller's `scenario`, verbatim, in the language it was sent in;
- the normalised `additional_instructions`, verbatim;
- the authenticated principal, and any `calling_system_identity` label you declared.

It is stored in clear on purpose — a receipt that does not show the question it answered is not evidence of anything. But that means **free-form scenario text may contain personal data, and it persists for the life of the database.** There is no retention window, no expiry job, and no deletion endpoint for a receipt; retention, export and erasure are the operator's obligation, performed directly against the `policy_case_decisions` table.

Three practical consequences for an integration that puts this in front of end users:

1. **Tell your users what is recorded**, before they type. A prompt that reads like a chat box and is stored like an audit log is a surprise you should not spring.
2. **Do not put identifiers in the scenario that you would not put in an audit log.** Describe the situation, not the person, wherever the policy question does not turn on identity.
3. **`calling_system_identity` is unverified free text.** It is recorded *beside* the proved principal, never instead of it. Do not treat it as an authorisation signal in your own systems either.

Receipt reads are narrowed at the record: a receipt may be read by the caller who made the decision, or by a policy author or administrator. Anyone else gets `403`. A service calling under its own principal can always verify its own receipts.

## What this contract does not claim

- No accuracy, precision or benchmark claim is made about the answers. The receipt tells you what was retrieved, what decided and what was cited so a human can check it — that is the guarantee on offer.
- **A large policy is read as a slice of its rules, not whole.** Above 15 rules a policy is a schedule rather than a statement, and the rules that bear on your question are selected — at most 15 in total, context included. `rule_selection` says exactly which, and how many were not read. That selection is lexical: it keys on the policy's own words against yours, so a rule that bears on your question in substance while sharing none of its vocabulary can be missed. When nothing matches, `method` is `document_order` and a bounded sample is read instead — the policy is never dropped for a lexical miss, but that answer is weaker and the field says so.
- **The retained set is bounded by what one grounded pass can read, not only by relevance.** Whole policies are admitted in rank order while they fit; one that would overflow is set aside with `outside_payload_budget` and reported. Candidates requiring the same thing are additionally *ordered* so the budget is not spent twice on one thing, which can put a highly-ranked policy outside it (`policies_diversity_deferred`). If a specific policy must be read, name it as `provision_id` and use single scope.
- **Equivalence is conservative, and errs toward reading more.** Two policies are called duplicates only on an exact match of everything stored. Two that differ in any recorded respect — even one only a drafter would notice — are read as two policies, or at most ordered relative to one another. The platform will forgo a collapse before it will assert a sameness the records do not support.
- **A slice that will not fit is still an honest non-answer.** If the selected rules themselves exceed the record budget, `rule_selection.oversize` and `size.oversize` are `true` and the track declines. Nothing is cut down to fit.
- **Retrieval is tuned to the whole question, not to each track.** A mixed question runs one retrieval and one rule selection; both gathers read the same records. That is deliberate — separate retrievals would let the statement you are told and the verdict you are given rest on two different sets of policies inside one receipt — but it means a question whose two halves are about genuinely different subjects is narrowed for as one subject. Ask them separately if that matters.
- **A project whose index is not ready and quality-passed is refused, not answered.** Retrieval requires a `ready` manifest built under the current corpus projection and a recorded `passed` verdict under `policy-projection-quality-v1`. A project that was never indexed, is mid-rebuild, was indexed under a superseded projection, or has not passed current validation answers `503 index_projection_unavailable`. Treat it as an operator signal: rebuild or validate as the recorded state requires. On `/case` and `/case/light` this is discovered after receipt reservation, so the original idempotency key is spent and the repaired call needs a new one; `/policies` writes no receipt and is simply safe to repeat after repair.
- **Translation is a dependency, and it can fail closed.** The inbound and outbound crossings each call a model. `503 scenario_translation_unavailable` and `scenario_translation_empty` mean no decision was attempted; `503 response_translation_unavailable` means a decision was made but its prose could not be returned in your language, and is refused rather than handed back in English under your language tag. The dependency failure may be transient, but the failed receipt has spent its `Idempotency-Key`: back off, then start a new call with a new key.
- **Projection validation is required but not omniscient.** Policies are matched through an English rendering of the corpus. Each rendering is checked structurally when built, then the completed `policy-projection-quality-v1` gate must record `passed` before readiness will match the index. The live AIS and HW projections passed 138/138 and 115/115 documents with zero findings. The gate detects gross substitution, not every near-identical sibling-record swap, and retrieval can still miss a bearing policy. The disclosure fields tell you what was read; they do not certify that everything which should have been read was found.
- **The classifier's reading is a model's reading.** `asked` reports it with its reasoning so you can see it, and an unreadable classification runs both tracks rather than dropping one. It is not a guarantee that a question you consider mixed will always be read as mixed.
- The evaluation is model-mediated. The platform's deterministic decision path is a different endpoint (`POST /api/evaluations`) taking structured facts and returning a `result_hash`; see [API](api.md). Use it when you need reproducibility rather than natural language.
- Nothing here is a substitute for the published policy itself, which remains the authoritative contract.

## Related pages

- [API](api.md#audited-external-decisions-policy-decisions) — the full endpoint, envelope and error reference.
- [User guide → serve decisions to other systems](user-guide.md#14-serve-decisions-to-other-systems) — the in-product **Call from your app** panel and the external playground.
- [Architecture](architecture.md#one-decider-two-surfaces) — why there is one decider behind two surfaces.
- [Known limitations](known-limitations.md) — retention of stored scenarios, the RBAC posture, and what is not shipped.
