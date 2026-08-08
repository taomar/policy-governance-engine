# Human review workbench and workflow

## Contents

1. Objectives
2. Roles and authorization
3. Queue design
4. Review packet
5. Comparison workspace
6. Reviewer actions
7. Assistance features
8. Impact and testing workspace
9. Concurrency and workflow
10. Audit and notifications
11. Accessibility and privacy
12. Backend APIs

## Objectives

Make policy judgment faster and more reliable while keeping the human responsible for material interpretation, authority, precedence, approval, and publication.

Optimize for reviewer understanding, not the fewest clicks. Every recommendation must be inspectable against exact source evidence.

## Roles and authorization

Separate capabilities instead of relying on one generic admin role:

| Role | Typical capability |
| --- | --- |
| Intake operator | Upload and classify bundles; cannot approve policy meaning |
| Extraction reviewer | Correct layout, spans, classifications, and normalized candidates |
| Domain policy owner | Judge intended policy meaning and relationships |
| Legal/compliance reviewer | Judge configured high-risk authority, conflict, and regulatory issues |
| Rules reviewer | Validate deterministic representation and test coverage |
| Publisher | Freeze and publish an already approved release |
| Auditor | Read lineage and decisions without mutation |

Make roles tenant- and policy-domain-scoped. Enforce separation of duties when configured: submitter, material editor, approver, and publisher may need to be different principals.

Do not let an agent or model impersonate an approver. Capture human identity from trusted authentication context.

## Queue design

Provide queues and saved views for:

- unassigned and assigned work;
- publication blockers;
- critical and high-severity conflicts;
- low-confidence normative extraction;
- missing authority, scope, date, or precedence;
- definition drift;
- changed entitlements, thresholds, approvals, deadlines, and exceptions;
- review requested back from another role;
- tasks approaching SLA or escalation;
- re-review after material edits;
- indexing or publication verification failures.

Support filtering by tenant, policy family, domain, source, relationship, severity, materiality, status, owner, reviewer, date, language, and affected population.

Show queue counts and aging without exposing content the viewer is not authorized to read.

## Review packet

Generate an immutable review revision. It should include:

```json
{
  "reviewTaskId": "task-id",
  "reviewRevisionId": "revision-id",
  "taskType": "extraction|relationship|conflict|precedence|rule|publication",
  "severity": "low|medium|high|critical",
  "materiality": "low|medium|high|critical",
  "reasonCodes": [],
  "publicationGatesBlocked": [],
  "candidateReleaseId": "draft-release-id",
  "comparisonReleaseIds": [],
  "sourceBundleIds": [],
  "candidateIds": [],
  "conflictCaseIds": [],
  "sourceSpanIds": [],
  "comparisonArtifactIds": [],
  "impactRunIds": [],
  "validationFindings": [],
  "uncertainties": [],
  "createdFromVersions": {},
  "requiredReviewerRoles": [],
  "requiredApprovalCount": 1,
  "dueAt": null
}
```

Freeze the inputs reviewed. If a candidate, comparison, extraction, or impact artifact changes, create a new review revision and mark prior approvals stale when the change is material.

## Comparison workspace

Use a synchronized layout with these areas:

### Source viewer

- Render the exact page and attachment.
- Highlight cited spans and table cells.
- Permit navigation to definitions, footnotes, annexes, and cross-references.
- Show OCR uncertainty and original image when extracted text may be wrong.
- Let the reviewer relink or expand evidence without editing the original source.

### Candidate semantics

- Show original wording.
- Show clause classification.
- Render normalized conditions and outcomes in human-readable form.
- Show raw structured data in an advanced view.
- Display definitions, units, calendars, effective dates, scope, evidence, approvals, and exceptions.
- Distinguish explicit source facts from deterministic derivations and model inferences.

### Existing catalog comparison

- Display aligned existing clauses and exact sources.
- Show metadata, text, semantic-rule, process, and definition diffs separately.
- Highlight negation, modality, boundary, amount, unit, date, scope, evidence, approval, and exception changes.
- Show approved policy relationships and precedence relevant to the pair.

### Conflict explanation

- State why the clauses may collide.
- Show the overlapping applicability domain.
- Show at least one witness scenario when available.
- Identify missing information or authority required to resolve it.
- Make the model-generated nature of any hypothesis visible without overemphasizing model confidence.

### Impact panel

- Show changed representative outcomes.
- Identify affected rule and workflow paths.
- Show boundary and regression test results.
- State scenario coverage and limitations.
- Never imply that simulated impact establishes legal or policy authority.

## Reviewer actions

Provide typed actions rather than one free-text approval:

```text
ACCEPT_EXTRACTION
EDIT_CANDIDATE
REJECT_CANDIDATE
MARK_NON_NORMATIVE
SPLIT_CLAUSE
MERGE_CLAUSES
RELINK_EVIDENCE
MAP_DEFINITION
REQUEST_REEXTRACTION
REQUEST_CLARIFICATION
DECLARE_EQUIVALENT
DECLARE_AMENDMENT
DECLARE_SUPERSESSION
DECLARE_NARROWING
DECLARE_WIDENING
DECLARE_EXCEPTION
ESTABLISH_PRECEDENCE
CONFIRM_CONFLICT
RESOLVE_CONFLICT
APPROVE_RULE
REJECT_RULE
APPROVE_RELEASE
REJECT_RELEASE
ASSIGN
DELEGATE
ESCALATE
WITHDRAW
```

Require typed relationship endpoints, scope, effective interval, reason code, notes, and supporting evidence for material relationship or precedence decisions.

Do not allow a reviewer to resolve a conflict by deleting evidence. Rejected model candidates and replaced review revisions remain auditable.

After a material edit:

1. create a new candidate or review revision;
2. rerun schemas, comparison, compilation, and affected tests;
3. recalculate publication gates;
4. require fresh approval according to policy.

## Assistance features

Use AI to reduce cognitive load while keeping provenance visible:

- summarize the candidate document and changed areas;
- align likely corresponding clauses;
- explain a normalized rule in plain language;
- identify possible missing qualifiers, references, or exceptions;
- propose conflict types and witness scenarios;
- generate boundary and regression test candidates;
- translate for reviewer convenience while retaining original-language authority;
- suggest reason codes and next reviewers;
- answer questions over the review packet with exact citations.

Do not let the assistant:

- hide source text behind a summary;
- select authority or precedence;
- modify candidates without an explicit reviewer action;
- invoke publication or business-action tools;
- use unauthorized policy content;
- present self-confidence as proof.

Clearly distinguish deterministic findings, source facts, model suggestions, and prior human decisions in the interface.

## Impact and testing workspace

Let reviewers inspect and edit proposed tests using safe typed facts. Include:

- happy path;
- just below, at, and just above every threshold;
- immediately before, at, and after relevant dates;
- each exception and exclusion;
- missing and contradictory facts;
- overlaps with other releases;
- different units, currencies, calendars, time zones, and rounding;
- authorization and evidence availability;
- representative high-risk cases approved for simulation.

Display old and candidate outcomes side by side. The reviewer can accept a test into the release's regression suite, edit it, or reject it with a reason.

Protect personal and sensitive data. Prefer synthetic or deidentified scenarios; require explicit authorization and purpose limitation for production-derived cases.

## Concurrency and workflow

Use optimistic concurrency with a task/revision version or ETag. A decision against a stale revision must fail and show the newer revision.

Support:

- assignment leases and reclaim after timeout;
- pause/resume over process restarts;
- requests for information with explicit recipients and due dates;
- delegation without transferring unauthorized scope;
- SLA reminders and escalation;
- cancellation and withdrawal;
- quorum or sequential approvals;
- rejection and resubmission;
- re-review after material changes;
- deterministic gate recalculation.

Use MAF request/response HITL when MAF owns orchestration. Store the authoritative review task and decisions in PostgreSQL; store only workflow continuation references in MAF state.

Do not keep a server request or worker process open while waiting for a human.

## Audit and notifications

Record append-only events for:

- task creation and reason;
- assignment, claim, release, delegation, and escalation;
- each viewed revision when required by audit policy;
- comments and clarification requests;
- proposed and accepted field changes;
- review decisions, reason codes, and notes;
- approvals invalidated by later edits;
- rule compilation and test results used in the decision;
- publication and activation gates opened or blocked.

Notifications should contain minimal sensitive information and link the user into an authenticated workbench. Do not include complete policy content or personal scenarios in email or chat notifications by default.

## Accessibility and privacy

Provide keyboard navigation, screen-reader labels, non-color-only status indicators, readable diff modes, zoomable source pages, right-to-left support when in scope, and accessible tables.

Apply document-level authorization before rendering source, existing comparison clauses, generated summaries, or impact cases. Redact according to purpose and role; do not ask the model to enforce redaction.

Log identifiers and actions by default, not full document content, prompts, or model outputs. Keep immutable decision audit separate from operational UI telemetry.

## Backend APIs

Prefer narrow endpoints or commands equivalent to:

```text
GET  /review-tasks?filters
POST /review-tasks/{id}/claim
POST /review-tasks/{id}/release
GET  /review-tasks/{id}/revisions/{revisionId}
POST /review-tasks/{id}/decisions
POST /review-tasks/{id}/comments
POST /review-tasks/{id}/request-information
POST /review-tasks/{id}/delegate
POST /review-tasks/{id}/escalate
GET  /review-tasks/{id}/source-spans/{spanId}
GET  /review-tasks/{id}/comparisons
GET  /review-tasks/{id}/impact-runs
POST /review-tasks/{id}/impact-runs
```

Every mutation must validate:

- authenticated actor and tenant;
- role and policy-domain scope;
- task state and required reviewer role;
- expected revision/version;
- separation-of-duty rules;
- typed action and required fields;
- idempotency key;
- downstream revalidation requirements.

Return typed conflict responses for stale versions, changed review inputs, invalid transitions, missing evidence, or insufficient authority. Do not silently merge competing review decisions.
