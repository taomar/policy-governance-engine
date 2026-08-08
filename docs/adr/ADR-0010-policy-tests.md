# ADR-0010: Policy tests as saved, AI-proposed but deterministically-executed assertions

## Status
Accepted

## Context

Section 23's entity list required `PolicyTest` and `PolicyTestRun`; neither
existed. Section 21.6 requires generating and executing eight test categories
(positive, negative, boundary, missing-fact, scope, effective-date, exception
where relevant, precedence where relevant) and is explicit about the division of
labour:

> Azure OpenAI proposes tests.
> The deterministic evaluator executes them.

Section 11.6 defines a "Policy Test Proposal Agent" with the same proposal-only
remit. Section 9.11 lists "6. Run deterministic tests." as a required step of
policy publication, and Section 9.9 requires a "Failed policy tests" queue in
the findings centre.

Three design questions were left open by the spec and had to be decided here:

1. **What does a test assert against?** Section 21.6 names the *categories* of
   test but not the assertion vocabulary.
2. **Do AI-proposed tests need human review before they count?** The spec says
   AI proposes and the evaluator executes, but is silent on whether a proposed
   test is live immediately.
3. **How does a failed test surface as a "finding"** in a codebase that has no
   generic persisted `Finding` entity (the closest analog being the on-demand
   AI quality report in `ai_quality.py`)?

A fourth constraint was situational rather than architectural: this work was
carried out concurrently with an unrelated redesign of the Policies tab in the
same working folder, so several frontend files were off-limits. That shaped
*where* UI went (a new page plus additive sections), not the design itself.

## Decision

### 1. Separation of concerns: proposal, execution, and persistence are three modules

The spec's "AI proposes / evaluator executes" split is enforced structurally,
not by convention:

- `evaluator/test_runner.py` — `run_policy_test(test_case, package)` is a pure
  function with no DB, network, or AI dependency, mirroring `evaluator/engine.py`.
  It is the **only** place a test's expectations are compared to an outcome, and
  it reaches that outcome solely by calling the existing `evaluate_policy()`.
  Evaluation logic is never reimplemented or approximated.
- `infrastructure/ai_test_proposal.py` — proposes `PolicyTest` payloads via
  Azure OpenAI. It imports no evaluator symbol and cannot execute anything.
- `infrastructure/policy_test_execution.py` — the DB-aware seam: resolves the
  policy set/version, maps it with `approved_policy_version_to_package()`, calls
  `run_policy_test`, and persists a `PolicyTestRun`.

This makes "AI must never decide pass/fail" a property of the dependency graph
rather than a rule someone has to remember.

### 2. Assertion vocabulary: expected status, optionally narrowed to one rule

A test asserts `expected_overall_status` (always), and may additionally assert
`expected_rule_id` + `expected_rule_status` and/or `expected_missing_facts`.
These map directly onto fields that already exist on `EvaluationResponse`, so a
test can never assert something the evaluator does not actually report.

`expected_missing_facts` is checked as a **subset**, not equality: a missing-fact
test asserting that omitting `amount` makes a rule indeterminate should not break
when an unrelated new rule introduces another optional fact. All mismatches are
collected rather than short-circuiting on the first, so a failing test explains
everything that was wrong in one read.

`evaluation_timestamp` is nullable and overridable per test — required for
effective-date tests, which must be able to simulate a date without which
"is this rule in effect yet?" is untestable.

### 3. AI-proposed tests require a lightweight human accept; human-authored tests do not

AI-proposed tests are created `review_status="pending_review"`, `is_active=False`
and do not run on publish or appear in findings until a human accepts them.
Human-authored tests are created `review_status="active"`, `is_active=True`.

Rationale: an LLM proposing a test must also predict the expected outcome, and a
confidently-wrong expectation produces a permanently-failing test. Because failed
tests feed the findings queue and re-run on every publish, an unreviewed wrong
test would emit recurring false alarms — the classic failure mode that trains
reviewers to ignore a queue. A human writing a test is already asserting intent
directly, so a review step there would be a self-approval with no information
value.

The review is deliberately **lighter-weight than `CandidateRule`'s**: accept or
reject, with no `changes_requested` state and no manager-override escalation. A
wrong `ApprovedRule` misconfigures real policy decisions; a wrong `PolicyTest`
can only produce a misleading line in a test report. Matching the heavier
workflow would have imposed governance ceremony disproportionate to the stakes.

`is_active` allows retiring a test without deleting it, preserving its run
history — the same reasoning that makes `PolicyTestRun` append-only.

### 4. Mutability: tests are mutable, runs are not

`policy_test_runs` is append-only (never updated in place), consistent with
`approved_rules` / `approved_policy_versions` / `evaluations`. Each run records
the specific `policy_version_id` it executed against, so history remains
interpretable after the policy changes underneath it.

`policy_tests` rows, by contrast, are deliberately mutable. A test case is a
quality-assurance artifact, not an authoritative governance record, so Rule 5.3's
immutability requirement does not apply to it. The critical consequence — that a
past result stays meaningful — is secured by the run being immutable and
version-stamped, not by freezing the test definition.

### 5. `PolicyTest` binds to a policy set, not a policy version

The FK is to `policy_sets`, deliberately not to `approved_policy_versions`. A
test bound to one version could not satisfy Section 9.11 step 6, whose entire
purpose is re-running the *same* assertion against a *new* version. Version
identity lives on the run, which is where it is actually meaningful.

### 6. Failed tests surface via a dedicated endpoint and an additive Quality-page section

A new `GET /api/policy-tests/policy-sets/{key}/failing` returns every active test
whose most recent run did not pass. `QualityPage.tsx` renders this as a separate
"Failed policy tests" section alongside the existing AI quality findings.

The alternative — folding failed tests into `ai_quality.py`'s `findings` array —
was rejected because the two have fundamentally different epistemics. A quality
finding is an AI's *opinion* about a rule, produced on demand and subject to
model variance. A failed test is a *deterministic fact*: a stated expectation
that the real evaluator contradicted, reproducible byte-for-byte. Merging them
into one list would let a reader mistake one for the other, and would couple a
deterministic result to an AI call's availability and latency (the section loads
independently and needs no "Run evaluation" click).

Tests that have **never run** are deliberately excluded from the failing list.
"Not yet verified" is not the same as "verified wrong", and conflating them
would inflate the findings queue with non-findings.

### 7. Publication hook is additive and non-blocking

`publish_approved_candidates` re-runs every active test for the policy set after
the new version is committed, recording runs with `run_trigger="on_publish"`. The
call is wrapped so that a failure in test execution cannot fail the publish
request. Publication is the authoritative act; test execution is reporting *about*
that act. Letting a reporting failure roll back an approved publication would
invert their importance and could block a legitimate governance decision.

The trade-off is accepted explicitly: a publish can succeed while its test run
does not complete. Because tests are re-runnable on demand and every run is
version-stamped, this is recoverable — whereas a blocked publish is not.

## Consequences

**Positive**
- The spec's proposal/execution split is structurally enforced, not merely documented.
- Every publication is automatically regression-checked against saved expectations.
- Run history is immutable and version-stamped, so results stay interpretable.
- The findings view distinguishes deterministic failures from AI opinion.

**Negative / accepted**
- Human-authored tests are trusted without review; a careless test can produce a
  false alarm, though only in a report.
- A publish may succeed while its test run does not, by design (above).
- Retiring a test means deactivating it; there is no hard delete or in-place
  edit endpoint yet (recorded in `docs/known-limitations.md`).
- Tests only run against *published* versions — the pre-publish
  "simulate against a candidate version" half of the P2 impact-analysis gap in
  ADR-0009 remains open.

**Compatibility / migration**
- Purely additive: two new tables via migration `d4f8a1c2e6b9`, one new router,
  one new frontend page and tab. No existing table, contract, endpoint, or
  response shape changed, so nothing pre-existing needed migrating.
- `EvaluatePage.tsx` / `POST /api/evaluations` (Section 9.12 ad hoc simulation)
  are untouched and remain a distinct feature: simulation is unsaved and
  exploratory, a policy test is named, saved, and re-run over time. They share
  the evaluator function, not their persistence or lifecycle.

## Validation

- `alembic upgrade head` → `downgrade` → `upgrade` cycle applied cleanly.
- 99 unit tests pass, including 11 new ones in `tests/unit/test_policy_test_runner.py`
  covering each assertion path, multi-mismatch explanations, and missing-fact
  subset semantics against DB-free fixture packages.
- `npx tsc --noEmit` clean.
- Live end-to-end on `expense-policy`: AI proposed 22 tests spanning the seven
  applicable kinds and correctly omitted precedence (that set has no precedence
  rules — Section 21.6's "where relevant" honoured); accept → run → PASS; a
  deliberately-wrong test rendered FAIL with an accurate explanation and appeared
  in the Quality page's failed-tests section.
- Publication re-run proven on a disposable policy set: published v1, ran two
  tests (one passing, one failing by construction), then published v2 with a
  tightened threshold. Both tests received new `on_publish` runs against v2 and
  **both statuses inverted** — demonstrating the re-run genuinely re-executed the
  evaluator against the new rule content rather than reusing a cached verdict.
  The disposable policy set and all its dependent rows were then removed.
