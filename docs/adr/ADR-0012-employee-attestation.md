# ADR-0012: Employee attestation / acknowledgment tracking

## Status
Accepted

## Context

`docs/policy-standards-research.md`'s gap analysis against ISO 37301 identified
the last remaining 🔴 P1 gap (the other two — exception requests, periodic
review/recertification — were closed in Milestones 36 and 37):

> **Employee attestation / acknowledgment tracking** — ISO 37301 §7.3 requires
> personnel acknowledge compliance obligations; no deadline/escalation
> workflow exists here.

There was no entity anywhere in the schema representing "this specific
person has read and agreed to this specific version of this policy." The
`AuditEvent`/`PolicyException`/`PolicySet.last_reviewed_at` machinery all
track *governance actors* (composers, reviewers, managers) doing things *to*
a policy set — none of it tracks the separate, much larger population of
*ordinary employees* who are simply obligated to read and confirm a policy
applies to them.

## Decision

### 1. Attestation binds to a specific `ApprovedPolicyVersion`, not the `PolicySet`

`PolicyAttestation.policy_version_id` is a hard foreign key to one immutable
published version row, not a floating pointer to "whatever is active now."
This mirrors how `PolicyException`/`PolicyTest` already anchor to a specific
version rather than the mutable policy set. Consequence (explicitly accepted,
not an oversight): publishing v4 does **not** retroactively invalidate or
re-open attestations against v3 — there is no automatic re-attestation
cascade on republish. A Policy Manager who wants fresh attestations for a new
version launches a new campaign explicitly. This keeps the semantics
unambiguous ("Dana attested to *exactly* this text") at the cost of requiring
a manual step most organizations would want anyway (a new campaign is itself
often the trigger for "please re-read what's changed").

### 2. Employee identity is free-text name + optional email, not a foreign key to a personnel system

Confirmed this session (again) that **no employee/personnel/auth model
exists anywhere in this codebase** — the platform has exactly 3 governance
personas (`system_admin`/`policy_composer`/`policy_manager`) modeled as a
client-side `ActorContext`, not a database-backed user table. Modeling a
real `Employee` entity with a directory sync would be substantial new
scope disconnected from what was asked. Instead, `AttestationAssignee`
(`name`, optional `identifier` treated as email) is captured directly on
each `PolicyAttestation` row at campaign-creation time, matching how
`PolicyException.requester` and `PolicyTest`'s free-text fields already
avoid inventing identity infrastructure this platform doesn't otherwise
have.

### 3. No-login self-service search, not a personal inbox

`MyAttestationsPage` (a new **top-level** nav page, not inside a project
workspace) lets anyone search by the name or email a manager typed in when
creating the campaign — there is no session, token, or login of any kind.
This is a deliberate, explicit trust trade-off appropriate to a local,
single-tenant build: it means anyone who knows (or guesses) a colleague's
name could view/acknowledge on their behalf. Acceptable here because (a)
this whole platform has no authentication layer to begin with (documented
limitation since Milestone 1), and (b) acknowledgment is additive and
auditable (timestamped, with optional notes) rather than a destructive or
security-sensitive action. Flagged explicitly in `known-limitations.md`
rather than silently accepted.

### 4. Status is computed, not stored

`pending` / `acknowledged` / `overdue` is derived, never written to a column:
`acknowledged_at IS NOT NULL` wins regardless of due date (an attestation
acknowledged after its due date is still `acknowledged`, not `overdue` —
overdue exists to flag *unacknowledged* obligations needing a chase, not to
penalize a late-but-completed one), otherwise `due_date < today` is
`overdue` and `due_date >= today` is `pending`. The exact same boundary is
implemented twice on purpose — once in Python (`_status_of`, used for the
list-response field) and once in SQL (`_apply_status_filter`, used for the
`?status=` query filter) — and a dedicated unit test compiles the SQL
WHERE-clause to a literal string and asserts it encodes the identical
`due_date < CURRENT_DATE`-shaped boundary as the Python function, so the two
can never silently diverge. "Due today" is deliberately `pending`, not
`overdue` — someone has the entire due day to act.

### 5. Campaign creation is manager-gated using the established `_require_manager` convention

`CreatePolicyAttestationCampaignRequest.actor_role` + `_require_manager(...)`
(403 for non-managers) exactly matches the convention already established by
`candidate_rules.py` and `PolicyException`'s grant/deny endpoints — no new
authorization pattern invented. Acknowledging one's own attestation via
`MyAttestationsPage`/`POST .../acknowledge` is deliberately **not**
role-gated at all (per point 3, there is no identity to gate against beyond
the free-text name/email already on the row).

### 6. Bulk creation, single due date, single version per campaign

`POST /policy-sets/{key}/campaigns` takes one `policy_version_id`, one
`due_date`, and a list of assignees — all rows in one campaign share both.
This matches the real-world shape of the feature (an HR-wide policy refresh
has one due date for everyone) and keeps the "New campaign" modal a single,
simple form rather than a bulk-editable grid. Splitting a cohort into two
due dates today means launching two campaigns.

## Consequences

**Positive**
- Closes the last verified, standards-backed P1 gap from
  `docs/policy-standards-research.md`'s ISO 37301 alignment pass.
- Fully additive: one new table, one new router, two new frontend pages, one
  new tab, one new top-level nav item — nothing existing was modified beyond
  registering the router and adding nav/tab entries.
- Reuses every established convention in this codebase (manager-gating,
  free-text identity, computed status, version-binding) rather than
  introducing new patterns, keeping the platform's architecture coherent.

**Negative / accepted**
- No automated reminder/escalation delivery (no email, no notification) —
  the `overdue` filter is the *only* mechanism a manager has to see who
  still needs chasing. Purely a local-build scope limitation, not a design
  flaw; would need a real notification channel (email/Teams/Slack) to close.
- No automatic re-attestation cascade when a new version is published — see
  point 1. A manager must remember to launch a fresh campaign.
- Self-service search has no authentication — see point 3. Acceptable given
  the platform's existing no-auth-anywhere baseline, but worth re-examining
  first if this were ever taken beyond a local single-tenant build.

**Compatibility / migration**
- Purely additive: one new table (`policy_attestations`) via Alembic
  migration `d1e2f3a4b5c6`. No existing table, contract field, endpoint, or
  response shape was changed or removed. Migration verified reversible
  (upgrade → downgrade → upgrade cycle completed cleanly against the local
  Postgres instance).

## Validation

- 14 new unit tests in `tests/unit/test_policy_attestations.py` (pure-logic,
  no DB — matching this repo's established testing convention with zero
  DB-integration test infrastructure): manager-gating (1 allowed + 4
  rejected roles), `_status_of` (4 cases incl. the due-today-not-yet-overdue
  boundary and acknowledged-wins-even-if-past-due), SQL/Python status-filter
  consistency via `stmt.compile(dialect=postgresql.dialect(),
  compile_kwargs={"literal_binds": True})`, and `bulk_create`'s row shape.
  Full suite: 312 passed, 0 failed (no regressions).
- Migration applied to the real local Postgres (port 5433) and confirmed
  reversible; table schema verified directly via `information_schema.columns`
  (all 11 expected columns present).
- Live API smoke test against the real running backend: created a real
  2-employee campaign on `hr-guide-policy` v3, confirmed 403 for a
  non-manager role, confirmed `GET /search` finds an assignee by partial
  name, confirmed status filters (`?status=pending`/`?status=acknowledged`)
  each return exactly the expected subset, confirmed the acknowledge
  endpoint updates status and persists notes.
- **Live browser verification** (chrome-devtools MCP, `http://localhost:5174`,
  after clearing a stale profile lock left over from an earlier attempt):
  navigated to the top-level "My Attestations" page, searched "sam", found
  the real pending attestation with the policy name correctly resolved,
  opened the acknowledge modal, submitted with notes, confirmed the row
  flipped to "Acknowledged" with a real timestamp and the notes text
  displayed. Switched to the project's "Attestations" tab as a
  `policy_composer` (gated — "New campaign" hidden, explanatory alert
  shown), switched acting role to `policy_manager` (button appeared),
  opened "Launch attestation campaign" (published-version + due-date
  pre-filled correctly), submitted a real campaign, and confirmed the new
  row appeared instantly as `Pending` with the segmented-control counts
  updating live (`All (3)`, `Pending (1)`, `Acknowledged (2)`). Confirmed the
  new row's "Assigned by: unknown" is expected, not a bug — the acting
  user's name field was intentionally left blank during this test, and
  `assigned_by: actor.name || "unknown"` is the exact same established
  fallback pattern already used by `PolicyExceptionsPage.tsx`'s
  `decided_by: actor.name || "unknown"`.
- `npx tsc -b --force` → 0 errors. `npx vite build` → clean.
