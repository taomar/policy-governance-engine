# Known Limitations Register

This register lists what is honestly **not** implemented in this local build phase.

## Not implemented this phase

| Area | Status | Notes |
|------|--------|-------|
| Microsoft Agent Framework workflows (ingestion, formalization, change, publication graphs) | Not implemented | `policy_platform.worker` is a real, minimal Python process reserved for this. AI features (extraction, quality, rewrite, compare, ask) are implemented as direct FastAPI endpoints instead of MAF graph workflows — see ADR-0004 (original deferral) and ADR-0007 (what was actually built once real Azure credentials became available). |
| Azure Blob Storage | Not implemented | Local filesystem storage under `var/documents/` used as a stand-in; swap behind a storage interface later. |
| Microsoft Entra ID authentication | Not implemented | Local dev uses a simple header-based `X-Dev-User` / `X-Dev-Role` stub — **not for production use**. |
| Policy change management / diffing (Section 17) | Partially implemented | `ai_compare.py` / `GET .../compare` does version-to-version rule diffing (added/removed/changed/unchanged + AI narrative summary), exercised live. What's not implemented: a persistent change-request/approval workflow around a diff (Section 17's full change-management process) — comparison is read-only/on-demand today. |
| Contradiction/ambiguity detection (Sections 19–20) | Partially implemented | The quality-evaluation pipeline (`ai_quality.py`) flags ambiguity, conflicting effects, and (via AI review) genuine legal/scope conflicts as findings — for both published versions and pre-publish candidates. What's not implemented: a dedicated standalone contradiction-detection pass independent of the quality report, or automatic conflict resolution. |
| Outbox pattern / Service Bus eventing | Not implemented | `audit_events` table exists; outbox table modeled but no publisher yet. |
| CSV export | Not implemented | Canonical JSON export exists via the schema; CSV flattening deferred. |
| Multi-tenant / organization scoping enforcement | Not modeled yet | Deferred; single-tenant local assumption documented. |
| AI-quality progress streaming | Not implemented | `/candidates/quality` on a large batch (e.g. 346 candidates) is a single long-running (~1–3 min) request with no incremental progress reporting; the frontend shows a disabled "Evaluating…" state for the duration. |
| Remaining HR Guide candidates (346 of 419) | Awaiting human/legal review | Only the 73 unambiguous, machine-executable candidates from the HR Guide template extraction were bulk-approved and published (v1). The AI's own quality review flagged that the source document is a *template* with placeholder/alternative clauses — the remaining 346 candidates are intentionally left in `candidate` status pending real human/legal review, not auto-approved. |
| Policy test lifecycle management (delete / bulk-run / scheduled runs) | Partially implemented | `PolicyTest` supports create, AI-propose, accept/reject, run-on-demand, auto-run-on-publish, and retire-via-`is_active` (ADR-0010). Not implemented: a hard-delete or edit-existing-test endpoint (retire and re-create instead), a "run all tests now" bulk action, running the suite against a *candidate* version before publishing, and any scheduled/CI-triggered execution — every run today is either manual or publish-triggered. |
| Curated rule-relationship fields not populated in existing samples | Not implemented (stale sample data) | `CanonicalRule.group_label` / `related_rule_ids` / `supersedes_rule_ids` / `is_explicit_override` are real schema fields, fully wired end-to-end through the API and frontend (Policies tab Overview "Relationships", Logic "Precedence", Scope "Classification" — clickable, jump-to-rule navigation as of the Policies-tab redesign). Confirmed with the main session: `group_label` is the intended, authoritative clustering key (`ai_extraction.py` already derives `related_rule_ids` from matching `group_label`s; `ReviewQueue` already surfaces "similar rules by `group_label`" matches) — it's empty on every rule in all 3 current sample datasets only because they were extracted *before* this schema/logic existed (see ADR-0009), not because of a live pipeline bug. The frontend's Policies-tab inspector prefers `group_label` when populated and only falls back to a display-only same-fact heuristic ("decision variations") when it isn't, so no further frontend change is needed once new extractions populate it. **As of Milestone 21, the same preference order now also drives a left-side list "band" (colored bracket + sibling-count tag) grouping every visible member of a family**, not just the inspector's pill strip — so `group_label` data quality has an even more directly user-visible payoff once new extractions populate it (a real, curated grouping will visually read as a tighter/cleaner set of bands than the current same-fact heuristic, which can only detect simple single-fact variations). `supersedes_rule_ids` is intentionally left manual (not AI-inferred) per `ai_extraction.py`. **As of Milestone 23 this field is also the grouping key for the Policies tab's "Group: Related family" mode and its at-a-glance family strip** (it replaced a `group_label`-keyed grouping option that, because the field is empty everywhere, always collapsed into a single "Ungrouped" bucket and was effectively dead). The grouping keys off the *computed* cluster — curated `group_label` when present, same-fact heuristic otherwise — so it works today and upgrades itself automatically, with no code change, the moment real `group_label` data lands. |

## Implemented and verified this phase

| Area | Status |
|------|--------|
| Local PostgreSQL via Docker Compose on port 5433 | Done |
| `.env` / `.env.example` staged with local + placeholder cloud settings | Done |
| Core domain entities (subset of Section 23) as SQLAlchemy models | Done |
| Canonical policy schema (JSON Schema + Pydantic contracts) matching Section 14 example | Done |
| Condition AST with allowlisted operators only (Section 14.1) | Done |
| Deterministic evaluator: `SATISFIED` / `NOT_SATISFIED` / `NOT_APPLICABLE` / `INDETERMINATE` / `ERROR` | Done |
| Missing-fact handling returns explicit `INDETERMINATE` with `missing_facts` list | Done |
| Precedence resolution (authority rank, jurisdiction specificity, priority, effective date) | Done |
| Stable SHA-256 result hash over canonical evaluation output | Done |
| SQLAlchemy async engine + Alembic migration, applied to local DB | Done |
| Runtime evaluation API endpoint (`POST /api/evaluations`) | Done |
| Unit tests for determinism, missing facts, precedence (pytest) | Done |
| Candidate-rule draft/review/approve/reject/publish workflow (backend + frontend) | Done |
| "Exactly one active version per policy set" invariant enforced on every version-creation path | Done |
| Sample policy set derived from real source documents (`hardware-provisioning-policy`, 10 rules, 2 versions with a genuine rule change) | Done |
| Admin UI rebuild: sidebar shell, visual rule/condition rendering, document upload + management, dynamic evaluation facts form | Done |
| Azure OpenAI integration: real endpoint/keys wired, thin `httpx` REST client (no SDK), two deployments (reasoning `gpt-5.6-sol` + fast `gpt-5.4-mini`) | Done — see ADR-0007 |
| Azure AI Search integration: read/write against pre-existing shared indexes (`policy-authoring`, `policy-evidence`) | Done — see ADR-0007 |
| AI document extraction: source document version → `CandidateRule` drafts (never auto-published) | Done — live-tested on 3 real documents (HR Guide PDF 419 candidates, Hardware Provisioning DOCX v3.2/v3.3) |
| AI quality evaluation — **published version** scope (deterministic checks + AI review) | Done |
| AI quality evaluation — **pre-publish candidates** scope (new this phase; evaluates unpublished `CandidateRule` rows directly) | Done — `evaluate_candidate_quality()`, `GET .../candidates/quality`, frontend scope toggle |
| Bulk candidate review (approve/reject many candidates in one call, backend + frontend checkbox multi-select) | Done — `POST .../candidate-rules/bulk-review` |
| AI rewrite suggestion + apply (targeted instruction → revised candidate payload) | Done — live-tested, candidate revision incremented correctly |
| AI version compare (rule-level diff + AI narrative summary) | Done — live-tested, 171 added / 1 changed detected correctly across real hardware-policy versions |
| Ask AI grounded chat (scoped to one policy set or all, cites source clauses) | Done — live-tested, correctly answered a real question with accurate source citations |
| Frontend: Quality page published/candidates toggle, Review Queue bulk-select toolbar | Done — visually verified in a live browser session |
| Policy tests (Section 21.6 / 11.6): `PolicyTest` + `PolicyTestRun` entities, AI proposal, deterministic execution, on-publish auto-re-run, failed-test findings | Done — see ADR-0010; live-verified end-to-end (22 AI-proposed tests across 7 kinds on `expense-policy`, plus an isolated demo policy set proving publish-triggered re-runs genuinely re-evaluate) |
| Obligations / Advice as post-decision actions (XACML Obligations-vs-Advice gap) | Done — see ADR-0011; rule-level `advice: Advice[]` (contract → `approved_rules.advice_json` → mapper → evaluator → API), aggregated into `EvaluationResponse.advice_notes` from the winning side's SATISFIED rules only (overridden-out rules keep their own advice visible on `RuleEvaluationResult.advice` but excluded from the aggregate); surfaced in the Evaluate page. Live-verified end-to-end against the real Postgres schema (migration applied, write→read round-trip confirmed via a rolled-back transaction, live evaluation calls against `expense-policy` return the new fields with no errors); 6 new + 105 total unit tests pass. |

## Gap analysis vs. world standards (research-backed roadmap)

A dedicated research pass (`docs/policy-standards-research.md`) verified this
platform's design against real, fetched standards documentation — XACML 3.0
(OASIS), Open Policy Agent, DMN 1.3 (OMG/Camunda), AWS IAM/Azure Policy,
ISO 37301, ISO 27001, NIST SP 800-162/205 — plus commercial GRC/policy-as-code
products. Full detail, sources, and verification status (fetched vs. training
knowledge) are in that file. Prioritized gaps found, not yet implemented:

| Priority | Gap | One-line rationale |
|---|---|---|
| 🔴 P1 | Employee attestation / acknowledgment tracking | ISO 37301 §7.3 requires personnel acknowledge compliance obligations; no deadline/escalation workflow exists here. |
| 🔴 P1 | Exception/waiver requests as a first-class tracked entity | Today's `exceptions` are rule-level fields, not a pending→approved/denied→expired workflow with requester/justification/approver (ISO 37301 §8.6, Azure Policy `exemption` objects). |
| 🔴 P1 | Periodic review / recertification due dates | ISO 37301 §9.3 / ISO 27001 require scheduled policy recertification; no `review_due_date`/`last_reviewed_at` fields or reminders exist yet. |
| 🟠 P2 | Per-evaluation decision/audit logging (OPA-style) | OPA Decision Logs (`decision_id`, `trace_id`, full input/result, bundle revision) are the verified industry baseline; our audit trail isn't yet that granular per evaluation call. |
| 🟠 P2 | Impact analysis across principal populations (version A vs B) | **Partially closed by ADR-0010.** Saved `PolicyTest` cases now auto-re-run against each newly published version, so a regression across representative fact-contexts is caught at publish time. Still missing the *pre-publish* half AWS IAM Policy Simulator / Azure Policy CI provide: running the suite against a candidate version *before* committing to publish, and a side-by-side A/B pass-rate report. |
| 🟠 P2 | Policy ownership / RACI metadata | No persistent owner/approver/escalation-path fields on a policy set beyond the review workflow's actors. |
| 🟠 P2 | Control mapping to compliance frameworks (SOC 2, ISO 27001 clauses, etc.) | Needed to generate automated audit evidence; not modeled. |
| 🟡 P3 | Delegation of authoring/approval authority (XACML Delegation Profile) | No bounded, time-limited delegation model from a Policy Owner to an acting delegate. |
| 🟡 P3 | ALFA-like human-readable rule authoring syntax | Canonical rules are authored/edited as structured JSON/UI forms, not a compact DSL. |
| 🟡 P3 | SBVR-aligned managed vocabulary/glossary | No enforced shared-term glossary across rules (risk of inconsistent fact naming). |
| 🟢 P4 | Training linkage on publish | No mechanism ties a new policy version to a training-assignment event. |

None of these are implemented this phase; they're recorded here as a
prioritized backlog for whichever session/milestone picks them up next.

## Risks not resolved by this phase (per Section 35 quality gate)

- The full end-to-end acceptance scenario (Section 28) uses MAF graph
  workflows for orchestration (Section 11); this phase implements the same
  *capabilities* (extraction, quality, rewrite, compare, ask) as direct
  FastAPI endpoints instead of a MAF workflow graph — functionally
  equivalent for a human-driven UI, but not the same orchestration
  mechanism the spec describes, and there is no pause/resume-as-a-workflow
  semantics.
- No security/threat-model review has been performed on the local dev auth stub;
  it must be replaced before any non-local deployment.
- No load testing, no CI/CD, no container scanning has been performed.
- Legal/compliance review of policy governance workflow is outside engineering scope.
- 346 of 419 AI-extracted HR Guide candidates remain unreviewed by design
  (the source document is a template with placeholder clauses — see
  ADR-0007 §6); this is an intentional governance choice, not a bug, but it
  means `hr-guide-policy` v1 is a small, curated subset rather than a
  full policy.
- AI-review findings and rewrite suggestions are advisory only; nothing in
  the pipeline auto-applies an AI suggestion without an explicit human
  action (approve, apply-rewrite, bulk-review) — consistent with Section 35,
  but worth restating since the AI surface area grew substantially this
  phase.
