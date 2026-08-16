# Handover

Written 2026-08-16 at the close of a long session. Read this before touching
anything. It is the guidance, the learning and the open work in one place,
because the last session lost instructions by re-deriving them from memory
instead of from a written source.

---

## 1. What the product is

PolicyVerbAItim ingests governance documents (PDF/DOCX) and emits grounded,
source-faithful JSON policy records for a human to review, approve and publish.

**The reader is a compliance officer, HR director or auditor — not an engineer.**
Every surface is judged by whether that person can act on it.

### The two routes — the single most important concept

| route | how a case is decided | verdict |
|---|---|---|
| **Deterministic** | the deterministic engine computes the comparison | exact |
| **AI Ready** | an **LLM judge reads the rule** against the case | verdict **with confidence** |

`AI Ready` exists *so that a rule whose test is language can still be decided*.
It is not a holding pen, not a backlog, not an unfinished Deterministic rule.

Live counts: **670 AI Ready, 7 Deterministic.** The judged path is the product.

**`AI Ready` is a ROUTE.** Two guards police how copy may describe it. Both
break the build when they fire. **Seven phrasings evaded them in one session** —
assume yours is the eighth and mutation-test it: inject a bad phrasing, watch
the guard go red, restore it.

The exact wording those guards reject, and the three consequences people keep
getting wrong, are written out in
[`failures/route-vocabulary-and-framing.md`](failures/route-vocabulary-and-framing.md).
**Read it before writing any user-facing copy about either route.** It lives
there because `docs/failures/` is the one directory the guards do not scan, and
prose that has to quote a forbidden phrasing in order to forbid it cannot be
written anywhere else.

One that is safe to repeat here: `decision_readiness` is `null` on all 2062
rules. Do not build a surface that mirrors it uncritically.

### Vocabulary — settled by the user, do not re-litigate

Use **"AI Ready"** and **"Deterministic"**. Two earlier names were retired and
may not appear in prose; they are listed in
[`failures/route-vocabulary-and-framing.md`](failures/route-vocabulary-and-framing.md)
§2, which is the only place outside the guard tests permitted to spell them.

---

## 2. Binding constraints

1. **Domain neutrality.** Nothing may be built or tuned to target a single
   domain, document, page, layout or language. Real documents are regression
   witnesses, **never targets**. A fix that makes one document pass is a failure.
   **Counts observed while diagnosing must never become literals in logic or
   tests.**
2. **The policy is the currency.** A policy is the unit of counting, selection,
   approval, publication and export. Rules are its contents. Counts read
   `policies = x, rules = y`. Export emits policies with rules nested — never
   single rules.
3. **The display contract** (user-approved verbatim: *"thats perfect....stick
   with this layout, for anything produce similar"*): every attribute is one row
   of three parts — **the attribute's own name, the document's words verbatim,
   and the identifier a case supplies a value for**. Nothing renamed, nothing
   merged, nothing hidden.
4. **Verbatim source is never translated, truncated or composed.** A quoted
   English clause stays English inside an Arabic answer, and the reverse.
5. **Absent / empty / refused / failed are four different states**, everywhere,
   in every language. Never collapse them.
6. **Nothing needed to judge a record sits behind a click.** Menus and tabs
   carry destinations, provenance and raw forms — never the evidence.
7. **Direction is a property of each text run**, never of a container, column,
   dialog or page. Use `DirectionalText`.
8. **A generated word is never a recorded word.** Labels, names and explanations
   are ours and must be unmistakably marked as ours (`✦ … NAMED BY THIS APP`).
   A generated rule name must never enter `payload_json`, an export or a
   published version.
9. **Editability is derived from the record** via `candidateEditability`, never
   passed as a prop. A sealed record must not become decidable by wiring.
10. **No filtering that hides.** Grouping and ordering, yes. Walls, no.
11. **Never buy tidiness with information.** No truncating a quotation to make a
    row align; no collapsing a distinction to reduce clutter.

### The endorsed logic idiom — approved, do not redesign

```
CONDITION — WHEN THIS RULE FIRES
  ⊟ APPLIES
      ├ subject     Any employee found guilty   [any-employee-found-guilty]
      └ condition   if not disclosed prior to the hiring/interview process
  OUTCOME
  ⊟ REQUIRES
      ├ modality    may
      ├ predicate   be released
```

Collapsible groups, attribute-name chips, `[case-supplies]` identifier chips,
indent guides. One implementation, composed at policy scale.

### Testing — two surfaces, two targets

| surface | who | target | version |
|---|---|---|---|
| **Review** | reviewer | the **candidate as it stands** | **none** — a candidate is not versioned |
| **Policies** | policy admin | the **published record** | **admin picks which version** |

A reviewer tests what is in front of them, before approving. Testing a draft
against a published version answers a question nobody asked.

| purpose | endpoint | needs a version? |
|---|---|---|
| judge a rule | `POST /api/ai/rules/evaluate-scenario` | **no** |
| compute a rule | `POST /api/ai/rules/compute-scenario` | **no** |
| deterministic evaluation | `POST /api/evaluations` | no |
| batch generation | `POST /api/policy-tests/.../validation-batches` | **yes** |

`DRAFT_TARGET` is the default that carries the review case. `PolicyInspector`
mounts `RuleScenarioTester` with **no `target`** precisely so that default
applies. Do not delete it — it looks unused and is not.

---

## 3. Architecture

**One record surface, parameterised on three orthogonal axes:**

| axis | carried by |
|---|---|
| **identity** — which policy | `provision_key` |
| **version** — which cut of it | document version / `approved_policy_versions` |
| **editability** — what may be done | derived from record status |

**`provision_key` is the policy's identity across versions.** `document_provisions.id`
is per document version, but one `provision_key` spans multiple published
versions. **A policy is not a row — it is a key, seen at a version.** This makes
History, Compare and Revise derivable rather than new subsystems.

**One renderer.** `PolicyInspector` is the single rule reading, reached inline
and as a destination, on Review and on Policies. The forked
`PublishedPolicyCard`, `publishedPolicyCards`, `PublishedRecordActions`,
`RuleDetailInline` and `InlineTabs` were all deleted for causing four separate
user-visible defects between them.

`RuleCard` **stays**, with three callers that render a rule *being written* —
`EditRuleModal` (Live preview, user-endorsed) and `RewriteModal` (before/after).
Those have no record to open. Different job. A test fails if it ever becomes the
answer to "open this rule of this policy".

---

## 4. Learning — the recurring failure patterns

### 4.1 The signature failure: a capability that works and reaches nobody

**Logged eleven times in one session.** Something is computed correctly, is
verified by its own tests, and no consumer ever calls it.

Examples: ingestion diagnostics built and never persisted; a dozen detectors
with one remediator; a reachability guard fooled by a string literal; a trend
gate disabled by an unmoved constant; a test guarding a content-loss defect that
had never executed because it skipped on a missing fixture; the structured
converter's table cells dying at the clause projection; the policy history
endpoint with no caller; `ExtractionStageRepository.record()` with no caller
anywhere; `PolicyContextElement` with no construction site.

**Defence:** before declaring work done, ask *who reads this?* and answer with a
call site. A test proving a capability works does not prove it is reached — walk
the AST or assert the caller.

### 4.2 A second copy always drifts

Two components rendering the same record produced four distinct user complaints
that were routed as four separate bugs. They were one. **Deleting the fork fixed
all four.**

**Defence:** if a surface needs a variant, parameterise the one component. If you
cannot edit the component you need, say so and request routing — do not fork.
When you must fork temporarily, say in writing that the copy exists to be
deleted, and name what deletes it.

### 4.3 Reporting a claim instead of verifying it

The producer relayed agent reports as fact; the user checked and found five
requests unimplemented. Separately, "exists" was mistaken for "wired" —
components existed and were rendered nowhere.

**Defence:** verify against code, then against the running app, before reporting.
Distinguish *file exists* / *imported* / *rendered* / *reachable by a user*.

### 4.4 Stale servers

The user reviewed a **30-hour-old build twice** while being told code had landed.
`--reload` is unsafe here: agents write scratch files into the repo and a reload
kills the detached process.

**Defence:** restart the API after backend commits and the web server after long
sessions; verify by asserting on a new field, not on uptime.

### 4.5 Measuring the wrong thing and concluding confidently

- The producer measured a policy page and checked for a rule-scoped tab.
- An agent reported "no Arabic in this corpus" because PowerShell's
  `ConvertTo-Json` escapes non-ASCII, so its regex could never match. There are
  75 Arabic clauses.
- An agent verified a bidi fix against *injected* pure Arabic; real Arabic here
  is bilingual and English-leading, so the fix was load-bearing on **1 block out
  of 596**. It reported this against itself.
- A run compared itself against a baseline **two model generations and five
  commits away**, because the baseline filter accepted only `completed` runs.
  That single defect accounted for 42% of the apparent instability.

**Defence:** state what you measured and how, so the method can be challenged.
Reproduce the known-wrong number first; it makes the right one credible.

### 4.6 Stacking work on one agent

Six tasks on one agent produced zero commits for hours while four other agents
shipped nine. Work existed but was uncommitted — worse than not started, because
it was reported as progress.

**Defence:** one coherent slice per agent, strict file ownership, and *commit
early even if incomplete*. Uncommitted work does not exist.

### 4.7 Constituent-boundary defects

Two separate defects came from a phrase landing in the role next door:
- a condition bound the grammatical subject rather than the measured quantity;
- a prohibition rendered as a permission because the negation sat in the
  modality and the predicate was a lossy copy of it.

**Defence:** fix at the boundary, not in the rendering, and **never by listing
words** — a vocabulary of negations does not survive Arabic. Anchor to the
source: a genuine constituent is a contiguous run of the sentence.

### 4.8 What good agent behaviour looked like

Worth imitating, all observed in this session:
- Refuting the producer's hypothesis with a counterexample rather than obliging
  it (the two-column header symmetry argument).
- Retracting a claim that justified the agent's own task.
- Reporting a failure its own guard could not catch (prompt-salience language
  drift).
- Declining to commit because the file held another agent's WIP.
- Disclosing its own `git reset` footgun — *"the behaviour I complained about
  being done to me"*.
- Refusing to "fix" a lint error that was a transient from a concurrent edit,
  and proving the constant was load-bearing.

---

## 5. Operating traps — concrete, cost real time

- **`git add` is not atomic in this shared worktree.** It swept up other agents'
  files **eight times** in one session. Stage ONE explicit path per invocation
  and run `git diff --cached --stat` before every commit.
- **The agent browser silently blocks any URL path starting `policies`.** Not an
  ad-blocker (`ads`, `analytics`, `tracking` all pass). Intercept and fulfil the
  route server-side with Playwright `page.route` + `page.request.fetch`, or you
  will see an empty page and misdiagnose it. Three agents lost time to this.
- **`git diff` read as text on Windows decodes as cp1252** and corrupts em-dashes
  into `â€”` in the index. Read as bytes.
- **`npx tsc -b` caches and reports false success.** Always `--force`.
- **Full web suite needs `--testTimeout=30000`** under load; several tests sit
  just under vitest's 5s default and fail spuriously when the machine is busy.
- **Python venv is `.venv-graph`, not `.venv`.** Set `$env:PYTHONIOENCODING='utf-8'`
  before any command that prints text. PowerShell has no heredoc.
- **Postgres:** container `policy-postgres`, port 5433, db `policy_platform_advtool`,
  user `policy_admin`.
- **Do not restart the API during an extraction.** One restart destroyed a
  40-minute run; another silently stamped a healthy headless run as `failed`.

---

## 6. State at handover

**404 commits** on `taomar-microsoft-advancedtooling`. Tree clean.

| | |
|---|---|
| Python | 3,143 passed, 1 skipped, 0 failed |
| Web | 1,204 passed, 77 files |
| `tsc -b --force` | exit 0 |

Data: AIS Employee Handbook (279 live rules, 38 policies, 2 published versions),
GMU Staff Handbook 2024 (398 rules, 32 policies, 0 published),
`table-structure-witness` (evidence set, disposable).

### Established this session

- The policy is a persisted entity (`document_provisions`); 155 cards → 70 real
  policies.
- One record surface; forked renderers deleted.
- One name per route, guards updated to reject the retired phrasings.
- Seven rows of disciplinary content recovered that had never existed as
  records; prohibitions no longer render as permissions.
- Extraction stability measured: **83.8% / 92.7% of rules keep their source
  anchor**; provisions identical across every run. The alarming figures came
  from a wrong-baseline comparison, since fixed.
- Docling flip **rejected on evidence** — it corrupts Arabic in both directions,
  runs 64× slower, and would have made the matrix problem worse. The real cause
  was one level deeper and is fixed.

---

## 7. Open work

### User queue (3) — do these first

| id | item |
|---|---|
| `json-invisible` | JSON tab renders its three sub-tabs and **no content** beneath them, for rules in the review page |
| `logic-rulename` | Logic tab shows raw element ids (`p9-E000071`); show the generated rule name with the rule text expandable |
| `ambiguity-yellow` | The yellow *"Reads more than one way, a person settles it"* block on published policies — check whether `ambiguity_status` carries real signal or merely restates the AI Ready route |

### Backlog (26) — none user-facing

Highest value first:

- `revise-action` — "send back to revise" on published policies; writes a new
  record, never rewrites a published promise.
- `policyset-key` — add `policy_set_key` to `PolicyCard` so generated rule names
  resolve on the published surface. The key must ride on the **record**, not the
  logic shape, or `logicViewServesEitherSurface` breaks.
- `reaper-mislabel` — API restart stamps healthy headless runs as `failed`.
- `run-restart` — run progress does not survive a restart.
- `quality-get` — a GET mutates and cannot be repeated; every page load commits
  a run row.
- `pagination` — `list_candidate_rules` has no `limit`; returns all 279.
- `stage-record`, `ctx-element`, `anchor-tid` — three more instances of §4.1.
- `interleaved-title`, `doses-defect`, `two-row-hdr`, `fact-cap` — extraction
  defects surfaced by the UI rather than hidden by it.
- `dupe-key-loc` — duplicate React key at `ProjectOverviewTab.tsx:136,144`;
  React may omit children.
- `askmodal-uuid` — draft ask sends a UUID where a slug is matched, so the
  approved-rules context silently never loads.
- `arabic-label` — an Arabic label on an English heading violates the bilingual
  rule; fix by withholding when the label's script set is disjoint from the
  heading's. Generic, no language list.
- `no-telemetry` — no token telemetry anywhere; wall clock is the only cost
  figure.
- `cleanup` — dead code and documentation sweep.

### Held for a user decision, not a defect

**Stage 1 re-segmentation.** Measured as the largest remaining variance source:
Stage 1 decides *which* sentences are normative consistently but *where one rule
ends* inconsistently. When Stage 1 was held fixed, Stage 2 reproduced 93% of a
batch on every field. Fixing the segmentation unit — one clause in, one candidate
passage out, letting Stage 2 split rather than Stage 1 — would remove most of it.
**It is a behaviour change with quality risk and needs the user's call.**

Also proposed and unenforced: floors F3–F5 (a run compares against the most
recent prior run that read the same document version; every rule anchors to a
clause span the previous run also cited; a rule whose anchor and decision fields
are unchanged keeps its identity). F1 and F2 are landed as tests.

---

## 8. Second session — what was verified, and where section 7 was wrong

Six commits on `taomar-microsoft-policy-queue-and-backlog`, branched from
`67f820e`. Tree clean. **Python 3147 passed / 1 skipped / 0 failed. Web 1222
passed / 80 files. `tsc -b --force` exit 0.**

### The handover commit broke the build

Section 6 above was measured *before* the commit that wrote it. That commit left
the suite at 3141 passed / **2 failed**: this document named the two retired
route names in `docs/`, and two of its sentences were rejected by the copy guard.
The guard matches phrasing and is blind to polarity, so it rejects a sentence
that denies the framing just as readily as one that asserts it.

Fixed in `351af75` by moving those passages to
[`failures/route-vocabulary-and-framing.md`](failures/route-vocabulary-and-framing.md),
the one directory both guards exclude. No guard was changed and no allowlist
grew. Both guards were then mutation-tested — red on an injected probe, green
when it was removed — so they are still load-bearing rather than newly blind.

**The lesson generalises: a guard that scans `docs/` will eventually reject the
document that explains the guard.** Write that explanation in `docs/failures/`.

### The user queue (all three closed)

| id | outcome |
|---|---|
| `json-invisible` | `103fe0a`. The review page mounts the inspector embedded, where the pane is `height:auto`; the record was styled `flex: 1 1 0` for the panel regime, and a zero-basis growable child of an auto-height column has no free space to grow into, so it resolved to 0px while the pinned switcher above it survived. Measured live: `.json-view` 0px → 4399px. Fixed by parameterising the embedded boundary that already exists, not by adding a competing rule. |
| `logic-rulename` | `59015a0`. `RuleName` already existed and the CSS already described the name — it was simply never wired, a §4.1 defect. Now each rule is headed by its generated name, marked as ours, with the element run demoted to the reference it is. The rule text was **already** expandable; no second disclosure was built. |
| `ambiguity-yellow` | No change, on evidence — see below. |

### `ambiguity_status` carries signal, and is not a restatement of the route

Measured across all 2062 rules, stored status against `machine_executable`:

| | `none` | `human_judgment_required` |
|---|---|---|
| `machine_executable = false` (2045) | 1764 | **281** |
| `machine_executable = true` (17) | 17 | 0 |

If the status merely repeated the route, all 2045 would carry the flag. 281 do —
13.7%. `_ambiguity_for` (`formulation_mapping.py:1906`) was repaired earlier so
that it reflects only the source's own wording, and the stored data shows that
repair took. The banner renders only for a prominent status, so it appears on 2
of the 14 published rules, not on every row.

Its real weakness is a different one: it reports that a sentence reads more than
one way without recording **which words** do. `ambiguityNote.ts` admits this in
its own copy. That is the improvement worth making. Removing the block would
destroy the only surface separating an unclear source from a clear one.

### Section 7's backlog is stale — verify before spending an agent

| id | section 7 says | measured |
|---|---|---|
| `quality-get` | a GET mutates on every page load | **already fixed.** `ai.py:773` documents the repair; the expensive work moved to `POST .../quality/runs` |
| `ctx-element` | `PolicyContextElement` has no construction site | **the symbol does not exist** anywhere in `src/` or `tests/` — it appears only in this document |
| `policyset-key` | add `policy_set_key` to `PolicyCard` | **already landed** (`policyCards.ts:176,380`) and confirmed resolving live on the published surface |
| `stage-record` | no caller | real, but **deliberately accepted and allowlisted** in `test_capabilities_are_reachable.py:377` with its reason. Needs a decision — write the stages, or delete the reader endpoint — not a fix |
| `pagination` | `list_candidate_rules` has no `limit` | **the item is wrong; do not implement it.** See below |
| `dupe-key-loc` | duplicate key at `ProjectOverviewTab.tsx:136,144` | real, line numbers had drifted to `:148` and `:161`. Fixed in `d8650c0` |
| `revise-action` | ranked **first** in section 7 | **already implemented end to end.** `RecordActionsMenu.tsx:184`, `PolicyInspector.tsx:778`, `EditRuleModal` `mode="revise"` writing `rule_revision + 1` as a new draft, gated on `is_active`, backend send-back at `candidate_rules.py:570`, three guard tests |
| `reaper-mislabel` | API restart stamps healthy headless runs as failed | **real.** Fixed in `fd0f46d` — read the caveat below |
| `askmodal-uuid` | draft ask sends a UUID where a slug is matched | **real, and worse than labelled.** Fixed in `3640b9a` and `39b815c` |
| `run-restart` | run progress does not survive a restart | real, but a **documented, deliberate** limitation — see below |
| `anchor-tid` | third instance of §4.1 | **the identifier resolves to no symbol**, exactly like `ctx-element` |

**Four of the eight items checked were already done or do not exist.** Two of
those four were ranked in the top five. Verify before dispatching.

### `pagination` was refused, and the refusal is guarded

Bounding that endpoint would be a wall under constraint 10, for four measured
reasons: every consumer counts in **policy** units, not rules (constraint 2), so
a rule offset cuts through the middle of a policy; the query orders by
`created_at` alone, which the domain model itself warns is not a total order, so
offset windows would silently drop or repeat rows; `api.ts:3033` documents that
the policies view indexes *into* the flat list's ids, which truncation would
dangle; and the web client never sends such a parameter, so it would reach
nobody. `8f40e1c` is a test-only guard that blocks the change, including a
signature check — because a behavioural test alone passes a `default=50` whenever
the fixture is smaller than 50.

### Two defects found that section 7 does not list

- **Quality runs had no deterministic order.** `QualityRunRepository` ordered by
  `run_at` alone, and `latest_quality_report` takes `runs[0]` as "the most recent
  recorded evaluation". Two runs stamped in the same tick tied, so a reviewer
  could be shown an older evaluation as the current one, and a different one on
  the next read. Fixed in `93cf639`; correctness no longer rests on clock
  resolution. The equivalent exposure on candidate rules was examined and is
  **not** the same defect — no consumer there selects by position.
- **`ProjectOverviewTab` overloaded one field as both React key and navigation
  target**, so renaming the key to fix reconciliation would have stranded the
  click. Identity and destination are now separate fields.

### Operating notes to add to section 5

- A fresh worktree has no `node_modules`, no `.env` and no `data/documents`.
  Without `.env` the whole suite fails at collection, because `api/app.py:123`
  builds the app at import time and that needs settings. Without
  `data/documents` twelve reading-order tests error on a missing fixture. Both
  are gitignored, so copy them from a working checkout.
- `pyproject.toml` sets `pythonpath = ["src"]`, so a venv from another checkout
  can be junctioned in and will still import *this* worktree's code.
- Ports come from `.env`: `API_PORT=8050`, `WEB_DEV_SERVER_PORT=5490`, and Vite
  sets `strictPort`. Do not assume 8000 or 5173 — two agents lost time to that,
  and the producer supplied the wrong numbers.
- Running the Python and web suites **at the same time** makes vitest workers
  time out. It cost 19 spurious errors in one run here. Run them one at a time.
- `Get-Content | Measure-Object -Line` skips blank lines and undercounts a
  Markdown file by about 20%. Use `(Get-Content path).Count` before concluding
  that a document was truncated.

### The startup reaper, and the one caveat on its fix

`_reconcile_interrupted_runs` ran from the FastAPI lifespan on every start and
marked **every** `running`/`pending` row failed, table-wide, with no ownership
predicate. Its docstring justified this with "an extraction is an in-process
background task" — true only of runs that process started.

This is not cosmetic. `_UNUSABLE_BASELINE_STATUSES` excludes `failed` from
baseline selection (`ai_extraction.py:411`, applied at `:458`), so a run flipped
to `failed` is silently dropped as a baseline and selection reaches back to an
older generation — the same mechanism §4.5 records as producing 42% of the
apparent instability.

`fd0f46d` adds `ExtractionRun.owner_kind` (migration `d9a3f6c1b204`, additive,
reversible, applied and backfilled) and scopes the sweep to `owner_kind == "api"`.
A per-process token was rejected because the reaper runs at *startup* to clean up
the *previous* incarnation, so matching on the current pid would reconcile
nothing; a heartbeat was rejected as a write on the extraction hot path plus a
tuned staleness constant.

**Caveat, stated because it decides how much to trust this:** no in-tree code
path currently creates a run owned by anything but the API. `submit_package`
creates `running` rows but has no production caller and is quarantined in the
reachability test. So the boundary is now explicit and the hole is closed, but
the fix could not be observed correcting a live mislabel — it guards the path
rather than repairing something happening today.

**Left undone, and it needs a cross-workstream decision:** an API run that was
interrupted is still recorded as `failed`, with the interrupted fact only in
`error_message`. Constraint 5 argues those are two states. Distinguishing them
means a new status value, and status is typed as a closed set in the web client,
so it is a model *and* web change.

### `run-restart` is real but deliberate — do not "fix" it casually

`extraction_progress.py` is in-memory **by design** and its docstring says so:
progress is "observation telemetry, not a source of truth… losing it has no
correctness consequence," and it expressly rejects persistence as "a write on
the hot path of every batch, to make a cosmetic readout durable." It is a
different root cause from the reaper — that was a wrong write with baseline
consequences; this is a read-only view that was never persisted on purpose.

### The ask now grounds on the right policy set, and says when it cannot

`AskAboutRuleModal.tsx:74` sent `candidate.policy_set_id` on the draft arm while
line 49 of the same file documented that the server resolves a key. Measured:
`SELECT count(*) WHERE key = id::text` is **0**, so the lookup could never match
and the approved-rules context was skipped on *every* draft ask.

Worse, `ai_chat.py` skipped that whole block with no log and no marker, which
collapses **failed** into **absent** — the collapse constraint 5 forbids. Both
halves are fixed: the caller now supplies the key (`ReviewQueue.tsx:2482`), and
the four states are now distinguishable in the log.

**Deferred, with a design:** making it reader-visible means a `policy_context`
field on the reply, following the existing `grounding` idiom rather than a new
mechanism, plus an Alert in `AskAiModal` with copy in the i18n table so the
caption guard stays green. It touches three files no single slice owned.

