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
