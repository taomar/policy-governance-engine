# Testing strategy: Tests, Evaluate, Regression — and the case dialog as their front door

**Status:** analysis, delivered before any build (as requested).
**Scope owner:** the case-dialog / policy-test surfaces listed as mine. `EvaluatePage.tsx` is read‑only here (another agent holds it); everything I say about Evaluate is strategy, not a change.

This document answers four questions the user asked, in their words:

1. *"restudy the testing page … as testing strategy, and implement it to catch the latest changes."*
2. *"running evaluation should be revised again according to latest changes."*
3. *"i dont know what regression does .. and its function."*
4. And the decision taken on their behalf: **the case dialog becomes the front door to a regression guard.**

The headline is measured, not asserted. Every claim below carries a file and line.

---

## 0. TL;DR

- **Regression is not a separate machine. It is a *property* of a saved test** — the property of being re‑run automatically when a new version publishes. Tests and Regression are literally **one React component**, mode‑switched (`ProjectWorkspace.tsx:420‑421`). That is why "i dont know what regression does": we gave a property its own page.
- **The re‑run machinery works.** On publish, every active guard is re‑run through the deterministic engine and recorded (`candidate_rules.py:810‑826` → `run_active_tests_for_version`, `policy_test_execution.py:134‑177`). The tables are empty because **nobody has ever created a guard**, not because the wire is broken. But there is a real, separate defect: **no automated test exercises that on‑publish hook** — a promise that has never been proven is exactly the §4.1 failure shape.
- **Evaluate is a genuinely different thing** and should stay separate: it is the deterministic **decision API** and its **append‑only audit trail** of *what calling systems asked* (`evaluations.py`, `Evaluation` model `models.py:866‑886`). It must never be merged into a reviewer's scratchpad, because that would blur the one meaning the audit trail exists to protect.
- **Recommendation:** merge **Tests + Regression** into one surface (they are one component); **keep Evaluate** separate but re‑label it so it is not confused with the case dialog; and delete the **dead 49 KB `PolicyTestsPage.tsx`**, which is mounted nowhere.
- **The case‑dialog → guard bridge has a mechanism mismatch that must be resolved honestly, and its resolution is the same cut the user already drew.** A **determination** answer supplies the facts a guard needs and *can* become a deterministic guard. An **informational** answer asks for the quantity a rule states — it has no facts to pin and, run through the deterministic engine, would demand the very input it was asking for (the original defect). **Informational answers are therefore not guardable, and the UI must say so rather than fake it.** Supplied‑quantity → determination → guardable; asked‑for‑quantity → informational → not guardable. The property that decides the intent is the property that decides guardability.

---

## 1. What each of the three pages is for

### 1.1 Tests — `PolicyValidationLab` (`mode="tests"`)

Mounted at `ProjectWorkspace.tsx:420`: `tests: <PolicyValidationLab policySetKey={…} />`.

What it lets a reviewer do:
- Generate a **blind validation batch**: the AI proposes N scenarios scoped to selected rules, run through the **deterministic** evaluator, with expected outcomes it must not have seen (`POST /api/policy-tests/policy-sets/{key}/validation-batches`).
- Review each AI‑proposed test (accept → active; reject → kept for history, never run): `POST /api/policy-tests/{id}/review`.
- Run any test now: `POST /api/policy-tests/{id}/run`.
- Promote passing scenarios into the regression suite (`PolicyValidationLab.tsx:1012‑1031`).

Backing tables: `policy_tests`, `policy_test_runs`, `policy_test_batches` (models at `models.py:1055‑1192`).

**A test is: `input_facts_json` (a structured dict) + an `expected_overall_status`** (one of `SATISFIED / NOT_SATISFIED / INDETERMINATE / NOT_APPLICABLE`) (`models.py:1081‑1161`). It is evaluated by the **deterministic engine only** — never AI (`policy_test_execution.py:13‑14`: *"Never lets AI decide pass/fail"*).

### 1.2 Regression — the **same** `PolicyValidationLab` (`mode="regression"`)

Mounted at `ProjectWorkspace.tsx:421`: `regression: <PolicyValidationLab … mode="regression" />` — **the identical component**.

A "regression guard" is not a new entity. It is a `PolicyTest` with `is_active = true`:

```
PolicyValidationLab.tsx:127
setRegressionTests(allTests.filter((item) => item.test.is_active));
```

The regression view shows the guards, their state, and lets you run the whole suite against any version, or retire/reactivate a guard. Its own promise to the reviewer (`PolicyValidationLab.tsx:406`):

> *"…added to the regression suite. They will re‑run automatically against every future published version and surface failures under Quality; they do not block publishing."*

So **Regression's function, in one sentence a compliance officer understands:** *a regression guard is a scenario you have already verified, kept as a standing check that re‑runs itself every time the policy is republished, so a later edit can't silently break an answer you once trusted.*

### 1.3 Evaluate — `EvaluatePage` (a different mechanism entirely)

`POST /api/evaluations` → look up the active approved version → `evaluate_policy(package, facts)` → **record an append‑only audit row** (`evaluations.py`). The `Evaluation` model's own docstring (`models.py:866‑886`):

> *"A recorded runtime evaluation request/response pair with result hash. Append‑only audit record of runtime evaluator calls (never updated). Read back through the 'Decision Log' …"*

The router is emphatic that this path is deterministic and isolated: *"It must never call AI/Search/network itself."* The row records `calling_system_identity`, `correlation_id`, `request_facts_json`, `overall_status`, and a tamper‑evident `result_hash`.

**Evaluate is the production seam:** what a *calling system* gets from the deterministic engine, logged as evidence. It is not a reviewer's reading tool. This is the exact meaning the case dialog's guardrail protects (`PolicyCaseRunner.tsx:710‑711`): *"the evaluation audit trail, which records what calling systems asked."*

---

## 2. What overlaps

| Surface | Input | Decider | Persisted to | Audience |
|---|---|---|---|---|
| **Tests** | saved facts + expected status | deterministic `evaluate_policy` | `policy_tests` / `policy_test_runs` | reviewer authoring checks |
| **Regression** | *the same rows*, `is_active=true` | deterministic (on publish) | `policy_test_runs` (`run_trigger="on_publish"`) | reviewer watching drift |
| **Evaluate** | ad‑hoc facts | deterministic `evaluate_policy` | `evaluations` (audit trail) | calling systems / their operators |
| **Case dialog** | a natural‑language question | **AI** intent + reading | **nothing** (unsaved) | reviewer asking "what does it say?" |

Two overlaps, one real and one only apparent:

- **Tests and Regression are one idea wearing two hats.** They share a component, a data model, and an engine. Tests is where you *author*; Regression is where you *watch the same rows re‑run*. Nothing separates them except a `mode` prop.
- **Tests/Regression and Evaluate share the deterministic engine** (`run_policy_test` is a thin wrapper over `evaluate_policy`, `test_runner.py`), but they are **not** the same idea: a Test carries an **expected** outcome and is re‑run and compared; an Evaluate call is a **one‑shot logged decision** with no expectation. Same instrument, different purpose. They should not merge.

There is also a **fourth** mechanism that now overlaps *confusingly* with Evaluate: the case dialog. Both "run a scenario against a policy," so a reviewer can't tell from the verb which one to use. The difference is sharp and must be stated in copy, not left implicit:

- **Evaluate** = deterministic, logged, for calling systems, answers *"is this allowed?"*
- **Case dialog** = AI reading, unlogged, for reviewers, answers *"what does the policy say about this?"* (`PolicyCaseRunner.tsx:23‑39`).

---

## 3. Does the re‑run machinery work? (the headline)

**Yes — the wire exists and fires. It has simply never had anything to run.**

On publish, after the new version is committed (`candidate_rules.py:810‑826`):

```python
# Section 9.11 step 6: publishing a new version must re-run every active
# PolicyTest for this policy set against it. Additive and best-effort …
try:
    await run_active_tests_for_version(
        session,
        policy_set_id=policy_set.id,
        policy_version_id=version.id,
        run_trigger="on_publish",
        triggered_by=body.approved_by,
    )
    await session.commit()
except Exception as exc:  # publish already succeeded; never fail the request because of this
    logger.warning("on-publish PolicyTest re-run failed for policy set '%s': %s", key, exc)
```

`run_active_tests_for_version` (`policy_test_execution.py:134‑177`) fetches every `is_active=true` test, runs each through the deterministic evaluator in isolation, and records a new `PolicyTestRun` with `run_trigger="on_publish"`. It is **best‑effort by design**: a broken test can never fail a publish.

**Why the tables are empty:** not a bug — a no‑data situation. No guard has ever been created (via UI or API), so `list_by_policy_set(..., is_active=True)` returns `[]` and the loop runs zero times. The machinery is complete and ready; it is unused.

**The real defect here is coverage, not wiring.** There is **no automated test** that exercises the on‑publish hook end‑to‑end (create test → publish → assert an `on_publish` run row appears). The unit tests cover the pure comparison logic (`test_policy_test_runner.py`) and the expectation hash (`test_policy_test_commitment.py`), but nothing proves the publish→re‑run promise. That is precisely the §4.1 shape: *a capability that works and reaches nobody, guarded by nothing.* **Closing that gap is more valuable than any cosmetic tidy‑up**, and it is step 1 of the build.

---

## 4. The mechanism mismatch — and why the user's own cut resolves it

The decision on the table is: *the case dialog becomes the front door to a regression guard.* Taken naively that is impossible, and the reason is the crux of this whole analysis.

- A **guard** needs `input_facts_json` + `expected_overall_status` and re‑runs through the **deterministic engine** — *"does this case satisfy the rule?"*
- The **case dialog** produces an **AI reading** in natural language, with an intent and cited rule IDs, and **no structured facts, no deterministic status** — *"does this rule apply to this case?"* The header comment is explicit that these are different questions and must never be totalled (`PolicyCaseRunner.tsx:23‑36`).

So you cannot pour an AI reading into a deterministic guard without a translation, and the translation behaves differently for the two intents — in exactly the way the user already told us it should:

### Informational answers are **not** guardable

An informational question asks for the quantity a rule states ("how many hours should a part‑timer work?"). It supplies no facts. Two independent reasons it cannot become a deterministic guard:

1. **Non‑determinism.** Re‑running it means re‑invoking the AI and comparing prose to prose — the very instability we spent this session killing. A guard must be reproducible; an AI paragraph is not.
2. **Structural incoherence with this engine — the original defect, reincarnated.** The rule that answers "how many hours" is `machine_executable=true` and *demands* `part-time-regular-employees-hrs-per-week` as an input. Feed the informational scenario to the deterministic engine and it returns INDETERMINATE, asking for the number the reader was asking it to tell them. A guard built on that would be meaningless. **This is the defect that started the session, and it is proof that informational ≠ guardable.**

Therefore, for an informational answer, the "keep as a guard" affordance must be **honestly absent or disabled, with the reason shown** — a distinct state under constraint 5, not a greyed button with no explanation: *"An informational answer states what the policy says. A guard checks a determination — a case with facts. There is nothing here to re‑run."*

### Determination answers **are** guardable

A determination supplies the facts ("I am part time working 30 hours…"). The engine has what it needs, so the scenario maps to `input_facts_json` + `expected_overall_status` and can be pinned to the suite. Even here the promotion is **a deliberate, reviewer‑mediated translation**, because:
- the structured facts the AI extracts are **ours**, not the document's (constraint 8) — the reviewer must confirm them;
- the deterministic engine can disagree with the AI reading, and **that disagreement is the most valuable thing a guard can catch**, so the human blesses the expected status rather than the AI asserting it.

### The boundary is the one already drawn

This is the supplied‑vs‑asked cut the classifier now uses, lifted one level up:

> **Supplies the quantity the rule tests → determination → guardable. Asks for it → informational → not guardable.**

The property that decides the intent is the property that decides guardability. No new taxonomy; the same defensible, language‑neutral structural test, so it survives the 75 Arabic clauses with no phrase list.

---

## 5. Recommendation: two pages, not three (and delete a fourth, dead one)

### 5.1 Merge Tests + Regression into one surface

They are one component, one model, one engine. Two top‑level pages for one idea — where one is "author" and the other is "watch the same rows" — is what produced *"i dont know what regression does."* Collapse them into a single **Validation** surface with two clearly‑labelled sections:

1. **Author & run scenarios** (today's Tests).
2. **Active guards — re‑run automatically on publish** (today's Regression), with the plain‑language sentence from §1.2 as its standing description.

This explains regression *by placement*: it stops being a mysterious sibling page and becomes "the checks that keep running." It also turns two empty surfaces into one honest one.

### 5.2 Keep Evaluate separate — but re‑label it

Evaluate is a different mechanism (deterministic decision API) and a different audience (calling systems), and it owns the audit‑trail meaning the guardrail protects. Merging it would blur that meaning. But its overlap with the case dialog is a real source of confusion now that both "run a scenario," so its header should say plainly what it is and point elsewhere for the other need:

> *This is the decision your calling systems receive from the deterministic engine; every run is logged to the Decision Log. To ask what the policy* says *in plain language, use "Put a case to this policy" — that is a reading, and it is not logged.*

(That is a copy recommendation for the agent who owns `EvaluatePage.tsx`; I will not touch the file.)

### 5.3 Delete the dead `PolicyTestsPage.tsx`

`PolicyTestsPage` is exported (`PolicyTestsPage.tsx:207`) but **imported nowhere** — the tab mounts `PolicyValidationLab`, not this. It is a 49 KB predecessor left in the tree. Three empty surfaces plus a dead fourth file is the clutter behind the user's confusion. Removing it is safe and clarifying. (It is in my owned set; I will remove it in the build phase with its own commit.)

---

## 6. The build plan (what follows this analysis)

Sequenced; each step honours the guardrails.

1. **Prove the re‑run promise.** Add the missing end‑to‑end test: create an active guard, publish a version, assert an `on_publish` `PolicyTestRun` row exists. If it fails, that is the finding; if it passes, the promise is real and now defended (§4.1).
2. **Case dialog → guard, determination only.** On a determination answer, offer *"Keep this as a guard."* It opens a confirm step that shows the AI‑extracted `input_facts` (marked as ours, constraint 8) and the proposed `expected_overall_status`, both editable, and on confirm creates a `PolicyTest` via the existing `POST /api/policy-tests/policy-sets/{key}` (which lands `is_active=true`, joining the on‑publish suite).
3. **Informational: say why not.** On an informational answer, no guard button — instead the honest sentence from §4, so the four states stay four (constraint 5).
4. **Honour the audit‑trail guardrail.** Keeping a guard writes to `policy_tests` — the reviewer's own validation assets — and **never** to `evaluations`, the calling‑systems audit trail. So the guardrail sentence stays *true*: nothing the reviewer asks is written to the evaluation audit trail. The dialog copy changes from "nothing is written, full stop" to "asking writes nothing; keeping a guard is a separate, deliberate act that writes to this policy's tests, not to the decision log." That distinction is the whole point and it must be visible.
5. **Four‑state guard readout on the merged page.** "No guard exists", "guard passed", "guard failed", "guard exists but has never run" are four states (the regression view already computes the last three at `PolicyValidationLab.tsx:257‑260`); the merged Tests view showing zero must distinguish "none exist" from "exist, never run."

Guards attach to a policy (constraint 2): a `PolicyTest.policy_set_id` scopes it to the set, so it re‑runs against every future version of that policy — which is exactly what makes it a regression guard rather than a one‑off.

---

## 7. Evidence index

| Claim | Location |
|---|---|
| Tests & Regression are one component, mode‑switched | `apps/web/src/components/ProjectWorkspace.tsx:420‑421` |
| A guard is a `PolicyTest` with `is_active=true` | `apps/web/src/components/PolicyValidationLab.tsx:127` |
| Regression's promise (re‑run on publish, surface under Quality, non‑blocking) | `apps/web/src/components/PolicyValidationLab.tsx:406` |
| Four guard states already computed in regression view | `apps/web/src/components/PolicyValidationLab.tsx:257‑260` |
| On‑publish re‑run hook | `src/policy_platform/api/routers/candidate_rules.py:810‑826` |
| Re‑run executor (active tests only, isolated, deterministic) | `src/policy_platform/infrastructure/policy_tests/policy_test_execution.py:134‑177` |
| Test decided by deterministic engine, never AI | `src/policy_platform/infrastructure/policy_tests/policy_test_execution.py:13‑14`; `evaluator/test_runner.py` |
| `PolicyTest` shape: facts + expected status | `src/policy_platform/domain/models.py:1081‑1161` |
| Evaluate = deterministic decision API + append‑only audit trail | `src/policy_platform/api/routers/evaluations.py`; `Evaluation` model `src/policy_platform/domain/models.py:866‑886` |
| Case dialog is AI, unsaved; engine‑satisfies vs judge‑applies | `apps/web/src/components/PolicyCaseRunner.tsx:23‑39` |
| The audit‑trail guardrail sentence | `apps/web/src/components/PolicyCaseRunner.tsx:710‑711` |
| `PolicyTestsPage.tsx` is dead (defined, imported nowhere) | `apps/web/src/components/PolicyTestsPage.tsx:207` (no importers) |
| No automated test covers the on‑publish hook | `tests/unit/test_policy_test_runner.py`, `test_policy_test_commitment.py` (scope is pure logic only) |
