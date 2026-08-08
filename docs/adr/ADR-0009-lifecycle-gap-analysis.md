# ADR-0009: Policy-lifecycle gap analysis against world standards, and scope decisions

## Status
Accepted

## Context
Per explicit instruction ("i want ur new plan and this business to follow known
real world standards for handling policies and how it's coded into computer
systems... dont fabricate or invent, follow the world and standards for this"),
a dedicated research pass was run against named, citable standards bodies and
real production systems before adding further business-process features. This
ADR records what was verified, what gaps were found, and — critically — which
gaps are adopted now versus deliberately deferred, so the deferral is a
documented decision rather than a silent omission.

### Standards consulted (verified via direct fetch unless marked otherwise)
- **OASIS XACML 3.0** core spec, Related Entities Profile, Administration &
  Delegation Profile — authorization policy language: PDP/PEP/PAP/PIP
  architecture, Target matching, Obligations vs. Advice, combining algorithms.
- **OMG DMN 1.3** (via Camunda's conformant implementation) — decision tables,
  hit policies (UNIQUE/ANY/FIRST/RULE ORDER/COLLECT), aggregators (SUM/MIN/MAX/
  COUNT), FEEL expressions.
- **NIST SP 800-162 / SP 800-205** — ABAC guidance (existence/authorship
  verified via CSRC; content details from training knowledge, flagged as such).
- **ISO 37301:2021** (Compliance Management Systems) and **ISO/IEC 27001** —
  policy lifecycle, periodic review, documented evidence requirements.
- **Real production systems verified via fetched docs**: Open Policy Agent
  (Rego, bundles, Decision Logs), AWS IAM + Policy Simulator, AWS Organizations
  SCPs, Azure Policy + Policy-as-Code. Referenced from training knowledge only
  (fetch failed or blocked, explicitly marked unverified in the underlying
  research report kept in session artifacts): Styra DAS, HashiCorp Sentinel
  enforcement levels, Red Hat Drools/KIE details, IBM ODM, Oracle Intelligent
  Advisor, ServiceNow Policy & Compliance, COSO ERM, SBVR, RuleML/RIF, ALFA.

### What this confirms we already got right
- XACML Target matching, Permit/Deny combining algorithm, and 8-dimension
  precedence (ADR-0008) are a direct, named match to the XACML 3.0 core
  architecture — not an invented mechanism.
- The `AggregateLimit` construct (ADR-0008) is the same shape as DMN's
  COLLECT+SUM hit policy, used by Camunda for exactly this "cap the combined
  output of several matching rules" case.
- `require_action` as an effect type is XACML's **Obligation** concept
  (a mandatory PEP action returned alongside a decision) — correctly named
  in spirit even though not yet labeled that way in the contract.
- The draft → review → approve → publish → version cycle already matches the
  standard shape ISO 37301/27001 and every GRC platform researched describe.

## Gap analysis and scope decisions

The full researcher-produced report (standards table, software table, phase-
by-phase lifecycle narrative, and complete prioritized gap list with citations)
is preserved in the session's research artifacts. This ADR records the
**decision** made against each priority-1/2 gap — adopt now, or defer with a
named reason — not a duplicate of the full report.

| Gap (standard/product grounding) | Decision | Reason |
|---|---|---|
| **Aggregate-limit persistence** (DMN Collect+SUM; not from this research pass but discovered while acting on it) | **Adopt now** | Already fully specified in ADR-0008 but never wired to the database — a rule persistence defect, not a new feature question. Tracked as `aggregate-limit-persistence`/`aggregate-limit-ui`. |
| **Exception/waiver requests as a first-class tracked entity** (ISO 37301 §8.6; Azure Policy `exemption` as a named, versioned JSON object) | **Adopt, scoped down** | A rule-level `RuleException` (condition + effect override) is a *modeling* construct, not a *request workflow*. A lightweight `PolicyException` request (who, which rule/policy, justification, decision, expiry) fits inside the existing 3-actor model (composer/reviewer requests or reviews it, policy manager decides) with no new actor. Full multi-level approval chains are out of scope. |
| **Periodic review / recertification due dates** (ISO 37301 §9.3, ISO 27001) | **Adopt** | Cheap, high-value: add `review_due_date`/`last_reviewed_at` to `PolicySet`, surface an overdue indicator. No new actor required. |
| **Obligations vs. Advice** (XACML 3.0 core) | **Adopt, minimal** | `require_action` already models Obligation. Add a non-blocking **Advice** channel (supplementary guidance returned with a decision, e.g. "consider notifying Finance") as an optional field on `Effect` rather than a new evaluator pathway — avoids re-litigating the combining algorithm. |
| **Decision/audit logging depth** (OPA Decision Logs: `decision_id`, `trace_id`, full input/output, bundle revision) | **Adopt, incremental** | The `evaluations` table already records request/response/hash; extend with a queryable audit view rather than a new logging subsystem. |
| **Impact analysis: version A vs. B across representative principals** (AWS IAM Policy Simulator; Azure Policy CI/CD validation) | **Adopt** | Folds naturally into `policy-test-management` (already planned) — a saved `PolicyTest` run against two versions is exactly this comparison. |
| **Policy ownership / RACI metadata** (ISO 37301, GRC practice) | **Partially adopt** | `PolicySet.owner` already exists. Add reviewer/approver-of-record on the published version (already captured as `approved_by`) — full RACI (informed/consulted lists) deferred as unneeded ceremony for a 3-actor tool. |
| **Control mapping to compliance frameworks** (SOC 2 / ISO 27001 control IDs) | **Defer** | Requires a controls taxonomy and mapping UI with no current consumer (no auditor actor, no compliance-report exporter requested). Revisit if/when an audit-facing export is requested. |
| **Delegation of authoring/approval authority** (XACML Administration & Delegation Profile) | **Defer** | Requires a delegation model (grantor, grantee, scope, attenuation, expiry) that only matters with more than a handful of users; the 3-actor model has no delegation need today. |
| **Employee attestation / acknowledgment tracking** (ISO 37301 §7.3; ServiceNow-style GRC) | **Defer — explicit actor-scope conflict** | Attestation requires a 4th actor (the policy's *audience*, i.e. "employees"), which directly conflicts with the explicit instruction to keep at most 3 actors (system admin, policy composer/reviewer, policy manager). Recorded here so the omission is a decision, not an oversight, and can be revisited if the actor model is deliberately expanded later. |
| **SBVR-aligned business vocabulary/glossary** | **Defer** | Valuable for very large rule sets with many authors; disproportionate for the current scale. A lighter version already exists informally via `category`/`tags`. |
| **ALFA-style human-readable authoring syntax** | **Defer** | The existing row-based condition editor + advanced JSON mode already serves the "avoid raw XML/JSON" goal for this platform's rule complexity; a full DSL is not justified by current evidence. |
| **Training linkage** | **Defer** | No training-content actor or system exists in this tool; out of scope until requested. |

## Consequences
- **Positive**: every business-cycle feature added from this point forward
  (aggregate limits, exception requests, review-due dates, Advice, impact
  analysis via PolicyTest) is traceable to a named standard or verified
  product practice, satisfying the "don't fabricate" instruction durably, not
  just for this conversation.
- **Negative**: several genuinely standard practices (attestation, control
  mapping, delegation, SBVR vocabulary, ALFA syntax, training linkage) are
  knowingly not implemented. Each has a recorded reason above; none are
  silent gaps.
- **Follow-up todos created**: `policy-exception-requests`,
  `policy-review-recertification`, `evaluator-advice-channel`,
  `aggregate-limit-persistence`, `aggregate-limit-ui` (the last two discovered
  independently while investigating this gap analysis — see below).
- **Compatibility**: all adopted changes are additive (new columns with safe
  defaults, new tables, new optional contract fields) — no existing rule,
  evaluation, or API response shape changes incompatibly.

## Related discovery made while acting on this ADR
While cross-checking the "aggregate-limit" gap against the actual codebase
(not merely the contract layer covered by ADR-0008), `AggregateLimit` was
found to have **zero database persistence**: `mappers.py`'s
`approved_policy_version_to_package()` never populates it, and
`policy_version_import.py` never receives or stores one. Separately,
`CanonicalRule.is_explicit_override`/`supersedes_rule_ids` and
`RuleException.limit_value`/`limit_unit` — all added for ADR-0008 — have no
corresponding columns on `ApprovedRule`/`RuleException` (domain tables), so
they are silently dropped at publish time despite being captured correctly in
drafts and the UI. These are tracked as `persist-precedence-fields` and
`persist-exception-limits` and are being fixed ahead of the new
lifecycle features above, since a database that silently discards data is a
correctness defect, not a feature gap.
