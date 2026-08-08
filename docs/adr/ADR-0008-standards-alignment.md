# ADR-0008: Evaluator alignment with ABAC/XACML/DMN standards for scope, precedence, and combined limits

## Status
Accepted

## Context
Section 19.1 (contradiction detection) already lists "Subject, Action, Resource,
Process, Jurisdiction, Organizational unit, Persona" as conflict dimensions, and
Section 15.4 requires exactly 8 named precedence dimensions (authority rank,
jurisdiction, scope specificity, explicit override, explicit exception, effective
date, rule priority, supersession relationship) — the spec's own authors had
already modeled this platform on ABAC/XACML vocabulary. Three concrete gaps
existed between that intent and the implementation:

1. `PolicyScope` (Section 14's Target-equivalent) was captured on every rule but
   never checked against anything: AI extraction always emitted an empty
   `PolicyScope()`, manual authoring hardcoded `personas: ["*"]`, and
   `evaluator/engine.py`'s `_rule_is_in_effect` checked only effective dates.
   A rule scoped to "executives" or "finance" was descriptive text, not an
   enforced access boundary.
2. `precedence.py` implemented only 5 of the spec's 8 required dimensions
   (missing jurisdiction as its own dimension, explicit override, explicit
   exception, and supersession), and `evaluate_policy` had no combining
   algorithm at all: every SATISFIED rule's `effect.action` — regardless of
   whether the rule's effect was `allow`, `deny`, or `require_action` — was
   merged into one `required_actions` set, and the reported `outcome` was
   chosen alphabetically rather than by precedence.
3. No construct existed for a cap spanning multiple rules' combined numeric
   output (e.g., "60 days pregnancy leave + 15 days/year sick-family leave,
   but combined no more than 70 days/year" — structurally distinct from
   `RuleException`, which is scoped to a single rule).

Per explicit instruction, these gaps were closed by following named, citable
external standards where the spec leaves a mechanism unspecified, not by
inventing new ad hoc behavior: OASIS XACML 3.0 core specification (Target,
Effect, Obligation, combining algorithm, PDP/PEP vocabulary) and OMG DMN's
"Collect" hit policy with a SUM aggregator (the standard mechanism for
combining several rules' numeric outputs under one shared ceiling — the same
shape as the real-world US FMLA 12-workweek cap combined across qualifying
leave reasons).

## Decision

**Target matching (Section 15.2 step 4).** `evaluator/engine._match_target`
evaluates a rule's 4 `PolicyScope` dimensions (jurisdictions, organizational
units, personas, processes) against reserved, well-known fact keys
(`subject.jurisdiction`, `subject.organizationalUnit`, `subject.persona`,
`context.process`) read out of the existing `EvaluationRequest.facts` dict —
not a new top-level request field, since Section 9.13 fixes the request shape
exactly and has no principal/subject field. `contracts.policy.PrincipalContext`
is kept only as a `to_facts()` convenience helper for callers (frontend,
tests) to populate those reserved keys; it is never part of the wire contract.
An unrestricted dimension (empty list or `["*"]`) always matches. A restricted
dimension with the fact present but non-matching yields `NOT_APPLICABLE` with
`not_applicable_reason="scope_mismatch:<dimension>"` (a clean XACML
Target-mismatch). A restricted dimension with the fact absent yields
`INDETERMINATE` with the fact key in `missing_facts` — Section 5.5/5.7's
"missing facts are never silently treated as false" principle, applied to
Target matching exactly as it already applied to Condition evaluation.

**Combining algorithm (Section 15.2 step 7).** `evaluator/engine._apply_combining_algorithm`
treats SATISFIED rules on the XACML Permit axis (`allow`/`require_action`,
grouped since `require_action` is this codebase's Obligation-like effect
attached to a Permit) and the Deny axis (`deny`) as only conflicting with each
other, never with same-axis rules. Same-axis SATISFIED rules all coexist,
matching DMN's Collect hit policy (gather every matching output rather than
force one winner). When both axes have SATISFIED rules, the already
precedence-ordered rule list decides the winner via first-applicable (a named
XACML combining-algorithm family): the highest-precedence SATISFIED rule's
axis wins outright, and every opposing-axis rule is marked
`overridden_by=<winning rule_id>` and excluded from `required_actions`/
`denied_actions` (but remains visible in `rule_results` for auditability).
`outcome` is the winning rule's action, fixing the prior alphabetical-selection
bug as the same change.

**Precedence — 8 dimensions in spec-listed order (Section 15.4).**
`precedence.sort_key` now scores, in order: authority rank; jurisdiction
specificity (a rule with a specific, matched jurisdiction outranks one with an
unrestricted jurisdiction — lex specialis, read as its own dimension per the
spec's explicit split from "scope specificity"); scope specificity over the
remaining 3 dimensions only (avoiding double-counting jurisdiction); explicit
override (`CanonicalRule.is_explicit_override`, new field); explicit exception
(`rule_type == EXCEPTION` or 1+ `RuleException` entries — read structurally,
in parallel with "Explicit override" directly above it in the same list, both
literally named "Explicit..."; the alternative reading of "only an exception
*triggered* for this specific evaluation" was rejected because it would
require evaluating conditions before precedence ordering, an architecture
change the spec doesn't call for); effective date; rule priority; supersession
relationship (`CanonicalRule.supersedes_rule_ids`, new field — scored as a
binary "is this rule named in another applicable rule's `supersedes_rule_ids`"
flag across the candidate set, since supersession is inherently a pairwise
relationship, not a scalar per-rule property). Effective date and rule
priority swapped relative order versus the pre-existing implementation to
match the spec's literal listing. `rule_id` remains the final deterministic
tiebreaker.

**Aggregate limits (new `AggregateLimit` contract).** A cross-rule cap —
`aggregate_id`, `contributing_rules` (each a `rule_id` + the fact name whose
value counts toward the sum when that rule is SATISFIED and not
`overridden_by` another rule), `aggregator: Literal["SUM"]`, `max_value`,
optional `period` — evaluated as its own post-hoc step
(`evaluator/engine._evaluate_aggregate_limits`) after per-rule evaluation and
combining-algorithm resolution complete, surfaced as `EvaluationResponse.aggregate_breaches`.
Grounded in DMN's Collect+SUM hit policy; distinct from `RuleException`, which
only ever modifies a single rule's own effect.

All new response fields (`not_applicable_reason`, `overridden_by`,
`denied_actions`, `aggregate_breaches`) were added as optional/default-valued
additions — no existing field on `EvaluationRequest`, `EvaluationResponse`, or
`RuleEvaluationResult` was renamed, removed, or had its meaning changed, other
than `required_actions` narrowing to exclude DENY-effect actions (a bug fix:
those were never meant to be there per Section 15.1's status model, since a
DENY and an ALLOW are not the same kind of "required action").

## Rationale
Every mechanism adopted here is a named, citable standard construct (XACML
Target/Effect/Obligation/combining-algorithm; DMN Collect+SUM), chosen because
the spec's own Section 19.1/15.4 vocabulary already presupposes this alignment
without fully specifying the mechanics. Two points required an explicit
interpretive choice where the spec is silent (jurisdiction-vs-scope-specificity
split rationale; "explicit exception" read structurally rather than by
per-evaluation trigger) — both are documented at the point of implementation
rather than silently assumed, per the requirement to ground every decision in
either the spec or a real external standard and flag anything neither settles.

## Consequences
- **Positive:** scope restrictions ("executives can override," "HR only")
  are now real, enforced access boundaries instead of descriptive text;
  conflicting Permit/Deny rules resolve deterministically by precedence
  instead of alphabetically; multi-rule combined caps (the pregnancy +
  sick-family leave scenario) are expressible and evaluated without abusing
  `RuleException`; all 8 spec-mandated precedence dimensions are implemented.
- **Negative / known simplification:** the supersession dimension's binary
  scoring correctly orders direct supersession pairs but does not fully
  resolve multi-hop transitive chains (A supersedes B supersedes C) in every
  possible ordering — a documented limitation, not a silent gap. The
  aggregate-limit breach-resolution policy (which contributing rule's outcome
  gets curtailed once a breach is detected) is intentionally left to policy
  authors/downstream consumers for now: the evaluator surfaces the breach
  deterministically but does not itself decide a remediation, since the spec
  does not specify one and inventing a resolution policy was explicitly out of
  scope for this change.
- **Compatibility:** additive-only contract changes; existing callers reading
  only the pre-existing response fields see no behavior change unless they
  relied on the alphabetical `outcome`/mixed-axis `required_actions` bug,
  which is a correctness fix, not a breaking change to any documented
  contract.
- **Follow-up:** AI extraction and manual rule authoring still need to
  populate `PolicyScope`, `is_explicit_override`, `supersedes_rule_ids`, and
  `AggregateLimit` from real documents/users (tracked separately); this ADR
  covers only the evaluator's ability to act on that data once populated.
