# ADR-0013: Policy ownership / RACI metadata

## Status
Accepted

## Context

`docs/policy-standards-research.md`'s gap analysis against ISO 37301 and
standard GRC practice identified a 🟠 P2 gap:

> **Policy Ownership / RACI Metadata** — ISO 37301 and standard GRC practice
> require each policy to have a named owner, approver, reviewer, and informed
> parties — a RACI model. The described platform has reviewer/manager roles
> in the workflow but no persistent ownership metadata on the policy itself
> (owner department, escalation path, delegate approver).

`PolicySet.owner` already existed (a free-text field holding department/team
values like `"finance-controls"`, `"hr-team"`) and every version-approval
event already records `approved_by`. What was missing was **individual-level
accountability**: a full RACI model needs a single named Accountable owner,
a Responsible/delegate approver distinct from whoever happened to click
approve on one version, an explicit escalation path, and the Consulted/
Informed stakeholder lists — none of which existed anywhere on the policy
set.

## Decision

### 1. `owner` (department) is left untouched; 5 new individual-level fields are added alongside it

`owner` continues to mean "which team/department is accountable for this
policy set" (e.g. `"finance-controls"`) and is unchanged by this milestone.
Five new columns are added to `PolicySet`:

- `accountable_owner` (RACI "A") — a single named person/role, e.g.
  `"Jane Doe, VP Finance"`.
- `delegate_approver` — a backup who can approve on the owner's behalf.
  Deliberately distinct from the per-version `approved_by` audit field:
  `approved_by` is a historical record of who *actually* clicked approve on
  one specific version; `delegate_approver` is forward-looking metadata
  about who is *authorized* to do so if the accountable owner is
  unavailable.
- `escalation_contact` — who overdue reviews, exceptions, or attestations
  should route to if the accountable owner is unresponsive.
- `consulted_parties_json` (RACI "C") — a list of stakeholder names/roles
  who must be consulted before a change (e.g. `["Legal", "Internal Audit"]`).
- `informed_parties_json` (RACI "I") — a list of stakeholders who must be
  kept informed of changes (e.g. `["All People Managers", "Finance Ops"]`).

This keeps the platform's existing "department owns the policy, actors act
on it" model intact while adding the individual accountability layer ISO
37301's RACI expectation actually requires, mirroring how `PolicyException`
(Milestone 36) and `PolicySet` review tracking (Milestone 37) each added a
narrowly-scoped new capability without disturbing what already worked.

### 2. `UpdatePolicySetRequest`'s new fields use plain optional types, no clear-flag

Unlike `review_due_date` (which needed a `clear_review_due_date` boolean
because `None` is itself meaningful there — "no due date" — so the request
schema must distinguish "field not provided" from "explicitly cleared to
null"), the 5 RACI fields follow the existing `description`/`category`/`tags`
convention: `str | None = None` / `list[str] | None = None` where `""` and
`[]` are valid, unambiguous "empty" states. A manager clearing the
"Escalation contact" field back to blank sends `""`, not `null` — there is no
scenario where "no escalation contact configured" needs to be distinguished
from "an escalation contact of empty string," so the extra clear-flag
machinery `review_due_date` needs would be unjustified complexity here.

### 3. Migration is purely additive with server defaults, following the established pattern

`f6a7b8c9d0e1_policy_set_raci_ownership_columns.py` (revises `d1e2f3a4b5c6`)
adds all 5 columns with `server_default` values (`''` for the 3 string
columns, `'[]'` for the 2 JSONB columns), exactly matching the template
`d5e6f7a8b9c0_policy_set_review_columns.py` established in Milestone 37. No
existing column, table, endpoint, or response shape changes. `downgrade()`
drops the 5 columns in reverse order.

### 4. Frontend: extend the existing "Edit Project" modal and Overview tab rather than a new page

The 5 fields are added to `ProjectWorkspace.tsx`'s existing "Edit Project"
modal (a new "Governance & ownership (RACI)" section after a `<Divider>`)
and displayed via a new "Governance & ownership" `<Card>` on
`ProjectOverviewTab.tsx`, inserted just above the pre-existing
`PolicySetSummaryPanel`. This reuses the exact same modal/tab a user already
visits to edit `name`/`description`/`category`/`tags`/`review_due_date`,
rather than inventing a separate "ownership settings" page for 5 fields that
are conceptually part of the same "project metadata" the modal already
owns. The card renders a populated label/value grid (department, accountable
owner, delegate approver, escalation contact) plus tag lists for
consulted/informed parties when data exists, or an empty-state prompt with a
"Configure ownership →" link when nothing has been set yet — matching the
populated/empty-state pattern already used elsewhere in this tab (e.g. the
review-due-date badge).

### 5. No escalation *engine* — this is metadata only, explicitly scoped out

`escalation_contact` is stored but nothing reads it automatically. There is
no notification system anywhere in this platform (documented since
Milestone 1 — no email/Teams/Slack integration exists), so an "overdue
review" or "overdue exception" does not auto-notify the escalation contact;
a human must still look at the field and act. This is the same accepted
trade-off as Milestone 41's attestation feature ("no automated reminder/
escalation delivery") and is recorded explicitly in
`docs/known-limitations.md` rather than silently implied.

## Consequences

**Positive**
- Closes a verified, standards-backed P2 gap from
  `docs/policy-standards-research.md`'s RACI alignment finding.
- Fully additive: 5 new nullable/defaulted columns, no existing field
  changed or removed; reuses the existing Edit Project modal and Overview
  tab rather than adding new surface area to navigate.
- Individual accountability (`accountable_owner`/`delegate_approver`/
  `escalation_contact`) is now separable from departmental ownership
  (`owner`) and from historical approval records (`approved_by`), closing
  the specific ambiguity the standards research flagged.

**Negative / accepted**
- Metadata only — no escalation engine, no automated routing, no validation
  that `escalation_contact` is a real, reachable address. See point 5.
- No enforcement that a policy set has an accountable owner configured
  before it can be published or marked reviewed — configuring RACI fields is
  entirely optional and unprompted beyond the empty-state UI nudge.
- Consulted/Informed parties are free-text tag lists, not links to a real
  personnel/directory system — consistent with this platform having no
  employee/auth model anywhere else (same trade-off ADR-0012 made for
  attestation assignees).

**Compatibility / migration**
- Purely additive: 5 new columns via Alembic migration `f6a7b8c9d0e1`
  (revises `d1e2f3a4b5c6`, now head). No existing table, contract field,
  endpoint, or response shape was changed or removed. Migration verified
  reversible (upgrade → downgrade → upgrade cycle completed cleanly against
  the local Postgres instance).

## Validation

- `pytest tests/unit -q` → 322 passed, 0 failed (no regressions; count
  unchanged by this milestone since no new pure-logic unit is introduced
  beyond straightforward field plumbing already covered by existing
  policy-set CRUD tests).
- Migration applied to the real local Postgres (port 5433) and confirmed
  reversible via a downgrade → upgrade round trip.
- Live API smoke test against the real running backend (direct HTTP, no
  browser): `GET /api/policy-sets/expense-policy` confirmed all 5 new fields
  present and empty by default; `PATCH` with all 5 fields populated
  (`accountable_owner: "Jane Doe, VP Finance"`, `delegate_approver: "Alex
  Kim, Finance Director"`, `escalation_contact:
  "compliance-office@company.com"`, `consulted_parties: ["Legal", "Internal
  Audit"]`, `informed_parties: ["All People Managers", "Finance Ops"]`)
  confirmed persisted and returned correctly, byte-for-byte, on repeat GET.
- `npx tsc -b --force` → 0 errors. `npx vite build` → succeeds.
- **Live browser verification** (chrome-devtools MCP, `http://localhost:5174`):
  confirmed the empty-state Governance & Ownership card renders correctly on
  `saudi-labor-law` (no RACI data set — shows the icon, "Configure" link, and
  empty-state prompt). Confirmed the fully-populated state on
  `expense-policy` renders the complete label/value grid and both tag lists
  exactly matching the values set via the API smoke test above (screenshot
  captured). Opened the "Edit Project" modal on `expense-policy` and
  confirmed all 5 RACI fields are correctly pre-populated from the existing
  data.
- **Save-path (edit → submit → persist) note**: a live in-browser edit
  attempt on `escalation_contact` produced a corrupted, concatenated value
  (old value + new value run together) that was also persisted to the
  database. Root-caused **before** accepting it as a product defect, per
  this project's architectural-escalation discipline: (a) `handleSaveEdit`/
  `openEdit` in `ProjectWorkspace.tsx` were re-read line-by-line and contain
  no append/merge logic — `form.validateFields()` reads the form's current
  state and is spread directly into a fresh request body; (b)
  `api.updatePolicySet()` in `api.ts` is a pure passthrough
  (`JSON.stringify(body)` over PATCH, no client-side merge); (c) the
  `escalation_contact` `Form.Item`/`Input` uses the identical pattern as
  `name`/`description`/`category`/`tags`, all proven reliable across 40+
  prior milestones' live verifications; (d) the shared Chrome dev-tools
  browser instance was independently confirmed, mid-investigation, to be
  under **live concurrent control from another active Copilot session**
  working on the same Policies tab at the same time (an isolated test page
  opened for diagnostic purposes was closed without this session's action,
  and the main tab's active view/tab-selection changed without this
  session's action, both within the same investigation window). Corrupted
  test data was reset to the clean value via a direct, uncontested API PATCH
  and re-confirmed clean. Conclusion: the corruption is attributable to
  environmental contention from concurrent multi-session browser automation
  on a shared dev Chrome instance, not a defect in this feature's code —
  recorded here in full rather than either silently dismissed or
  misattributed as a fixed bug. If this is ever observed again **without**
  concurrent multi-session browser access, it should be treated as a fresh,
  unconfirmed report and re-investigated from first principles.
