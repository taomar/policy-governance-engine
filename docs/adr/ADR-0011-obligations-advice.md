# ADR-0011: Rule-level Advice as a non-blocking, aggregated evaluation channel

## Status
Accepted

## Context

`docs/policy-standards-research.md`'s gap analysis against XACML 3.0 (OASIS,
verified/fetched spec) identified a P1 gap:

> **Obligations and Advice as Post-Decision Actions** — XACML 3.0 defines
> **Obligation** (PEP *must* perform an action when a decision is returned —
> e.g. "send notification email," "write to audit log," "trigger approval
> workflow") and **Advice** (supplementary information the PEP *should* act
> on). The described platform specifies `require_action` as an effect, which
> maps to an Obligation, but there is no explicit Advice channel... callers
> cannot receive non-blocking guidance alongside PERMIT/DENY.

This platform's `Effect.action` / `EffectType.REQUIRE_ACTION` already models
the mandatory-Obligation half correctly. Advice had no equivalent: there was
no way for a rule to say "by the way, also consider notifying the
requester's manager" without it being interpreted as something the caller
*must* do to remain compliant (which is precisely what the Obligation/Advice
distinction in XACML exists to prevent conflating).

## Decision

### 1. `Advice` is a minimal, always-attached-on-SATISFIED note

```python
class Advice(BaseModel):
    advice_id: str
    text: str
```

Deliberately mirrors the simplicity of `Effect.action` rather than gaining
its own condition, priority, or targeting: a rule's advice is *its* advice,
attached whenever that rule is `SATISFIED`, with no independent trigger
logic. A rule may carry both a `require_action` (Obligation) and `advice`
(Advice) simultaneously — these are independent fields, not mutually
exclusive, matching how XACML treats them as two separate response
channels rather than alternatives.

### 2. Aggregation is polarity-agnostic, unlike `required_actions`/`denied_actions`

`_apply_combining_algorithm` already splits SATISFIED rules' actions onto two
axes — `required_actions` (allow-like) vs `denied_actions` (deny) — so a
caller can tell an approval from a rejection without inspecting each rule.
Advice does not get this treatment: `advice_notes` is aggregated from the
**whole winning side**, regardless of whether the winning rule was a
PERMIT or a DENY, because XACML Advice is informational and equally
meaningful attached to either outcome (e.g. "explain why this was denied"
is just as valid Advice as "remember to log this approval"). Deduplicated
and sorted for determinism, matching how `required_actions`/`denied_actions`
are collected.

### 3. Overridden-out rules keep their own advice visible, but excluded from the aggregate

Consistent with how `overridden_by` already works for actions: a SATISFIED
rule that lost precedence to a higher-authority rule on the opposite
allow/deny axis still reports its own `advice` on its individual
`RuleEvaluationResult` (transparency — Rule 5.5's spirit of never hiding
what actually happened), but its advice text is excluded from the aggregate
`EvaluationResponse.advice_notes`, which reflects only the decision that
actually stands.

### 4. Follows the established 5-step pattern for adding a new `CanonicalRule` field

This is the fourth field added this way (after `group_label`,
`related_rule_ids`/`is_explicit_override`/`supersedes_rule_ids` from
ADR-0009): contract field → `ApprovedRule.advice_json` JSONB column →
`mappers.py` read path → `policy_version_import.py` write path → Alembic
migration. All five were required in lockstep; a contract-only change would
have been silently dropped at publish time, exactly as ADR-0009 documented
for its own fields.

### 5. Frontend surfacing: Evaluate page only, not the Policies tab

`advice_notes` is rendered as an informational (blue) `Alert` on the
Evaluate page's result card, plus a per-rule "Advice" column (tooltip
showing full text) in the rule-results table — the same page
`aggregate_breaches` (ADR-0008) already surfaces. The Policies tab and its
Inspector were deliberately left untouched: two concurrent sessions were
actively redesigning that exact surface (master-detail Policies workspace)
at the time this feature was built, and the Evaluate page is both
low-conflict and the natural home for anything shaped like "extra
information about a specific decision" rather than "information about a
rule in the abstract."

## Consequences

**Positive**
- Closes a verified, standards-backed P1 gap without touching any
  in-flight concurrent work.
- Existing rules are entirely unaffected: `advice` defaults to `[]`
  everywhere (Pydantic `default_factory`, JSONB `server_default='[]'`), so
  the ~600 rules across the 3 real sample policy sets continue to evaluate
  identically.
- `advice_notes` is included in the evaluation's hash payload, so the
  determinism guarantee (Section 27.5 / `result_hash`) correctly reflects
  advice as part of the evaluation output, not a side channel that could
  silently diverge from the hash.

**Negative / accepted**
- No rule in any of the 3 real sample datasets has advice populated yet —
  identical situation to `group_label` et al. in ADR-0009. This is a
  content-authoring gap (nothing today writes non-empty `advice` at
  extraction or manual-authoring time), not a plumbing gap; the channel is
  fully wired end-to-end and ready the moment a rule author or the AI
  extraction pipeline populates it.
- The Policies tab / Inspector do not yet display a rule's *own* `advice`
  list when editing/reviewing it (only the Evaluate page's *evaluation
  result* surfaces it). Left for whichever session next touches that tab,
  to avoid the concurrent-edit conflict described in point 5 above.

**Compatibility / migration**
- Purely additive: one new nullable-with-default JSONB column via migration
  `e1f2a3b4c5d6` (down-revision `d4f8a1c2e6b9`). No existing table, contract
  field, endpoint, or response shape was changed or removed.
- `_apply_combining_algorithm`'s return tuple grew from 4 to 5 elements;
  confirmed via grep it has exactly one caller (`evaluate_policy`, in the
  same module), so this is not a breaking change to any public surface.

## Validation

- 6 new unit tests in `tests/unit/test_advice.py`: per-rule advice
  transparency on SATISFIED, absence on NOT_SATISFIED, aggregation across
  multiple non-conflicting rules, exclusion-from-aggregate-but-visible-on-
  rule for an overridden rule, hash-determinism sensitivity to advice
  content, and default-empty backward compatibility. All 105 unit tests
  (existing + new) pass.
- `alembic upgrade head` applied cleanly against the running local Postgres
  (port 5433).
- Live write→read round-trip verified directly against the real schema: a
  throwaway `ApprovedPolicyVersion`/`ApprovedRule` with real `Advice` text
  was inserted via `import_approved_policy_version`, re-fetched through the
  same repository + mapper the API/evaluator use, and the text confirmed to
  survive byte-for-byte — then rolled back (never committed), leaving the
  shared database unchanged.
- Live API verification against the running backend (port 8010): 
  `GET .../versions/{id}/rules` on the real `expense-policy` returns
  `"advice": []` on every real rule with no errors; `POST /api/evaluations`
  against real facts returns `"advice_notes": []` and per-rule `"advice": []`
  for INDETERMINATE and SATISFIED outcomes alike.
- `npx tsc -b --force` and `npm run build` clean after both the `api.ts`
  type additions and the `EvaluatePage.tsx` UI additions.
