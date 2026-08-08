# Backend data-integrity session — handoff

> **Historical handoff (superseded 2026-08-08).** Start with
> [`extraction-quality-handoff-2026-08-08.md`](extraction-quality-handoff-2026-08-08.md).
> In particular, this file's open item claiming `EffectType` has no neutral member
> is obsolete: `EffectType.INFORMATIONAL` now exists, definition/classification
> rules map to it, and the evaluator excludes it from the allow/deny axis.

A working note, not a specification. It records what one session changed, what it
found and deliberately did not change, and the environment facts that cost time to
discover. Written so the next session can resume without re-deriving them.

Scope of this session was backend data integrity: extraction parsing, quality
reporting, and correlation durability. **No frontend files were touched.**

---

## What changed

Four commits, nine files, all backend Python and unit tests.

| Commit | What it fixes |
|---|---|
| `e5ebb21` | A list-shaped `semantic_projection` field discarding its whole batch |
| `ac65efe` | A `trusted_config` whose keys are silently unusable |
| `f2c8feb` | Definitions that carry an authorization effect |
| `b7d9562` | Correlation findings lost when a long run fails |

### `e5ebb21` — projection shape variance

`DmnSemanticProjection.object` is typed `str | None`. The agent sometimes returns
a list (`['modest', 'loose', 'opaque']`). `_remap_projection` re-raises by design,
so one such field cost the entire batch. MHRSD lost 4 batches to this class of
failure before it was fixed.

`_coerce_source_to_string` already joined lists for `outcome`, `condition_source`
and `outcome_source` — `object` sat one line above them and was simply omitted.
Coverage was extended to `subject`/`predicate`/`object` together, because they are
one semantic unit and covering only `object` would have been another special case.

Coverage deliberately stops at that model. The canonical side is protected by
`_salvage_valid_policies`, so a malformed policy there costs only itself; the
projection side has no such salvage. The two failure boundaries differ by two
orders of magnitude in blast radius and should not be conflated.

### `ac65efe` — `trusted_config` shape guard

Two shapes are accepted silently and do nothing:

```python
# WRONG — keyed by FEEL path. Accepted; still reports FACT_MODEL_REQUIRED.
{"worker.ageYears": {"type": "number"}}

# RIGHT — keyed by source term.
{"age of the worker": {"feel_expression": "worker.ageYears", "type": "number"}}
```

`output_model` uses `feel_name`, not `feel_expression`. The eleven valid Section 83
keys are `fact_model`, `output_model`, `type_model`, `value_normalization`,
`term_dictionary`, `decision_precedence`, `hit_policy`, `definitions`,
`numeric_normalization`, `currency`, `unit_conversions`. **`temporal_model` is not
one of them** — supplying it made `TEMPORAL_MODEL_REQUIRED` worse, not better.

The guard warns rather than errors: Section 83 is the specification's list, not the
model's, and a future revision adding a key should not stop an extraction. Verified
against both real configs — it fires on the one that silently did nothing and stays
silent on the one that made 2 of 3 decisions executable.

### `f2c8feb` — definitions carrying effects

Two separately-reported AI findings, "definitions modeled with allow effects" and
"semantic polarity errors", are **one defect**.

```
EffectType has no neutral member (allow / deny / require_action only)
  -> _RULE_TYPE_MAP sends DEFINITION -> EffectType.ALLOW     (category error)
  -> a negatively-phrased definition asserts the inverse of its source
  -> currently latent: machine_executable=False -> evaluator returns NOT_APPLICABLE
  -> supplying a trusted_config makes rules executable -> an active wrong answer
```

Observed in real data. *"The periods designated for rest, prayers, and meals **shall
not be included** in the actual working hours"* became `allow: "be included in the
actual working hours"`. Also *"may not be deemed as service transfer cases"* became
`allow: "be deemed as service transfer cases"`.

**55 rules in `saudi-labor-law`, 149 across both statutory sets.** The
`rule_type`-to-`effect_type` mapping is otherwise perfectly consistent, which is what
localised the fault to the definition category rather than to the mapping.

Contained, not fixed — see the open item below.

### `b7d9562` — correlation durability, and the reader it was coupled to

Findings were held in the session and written in a single commit at the end. A run
over the statutory sets is ~1,700 model calls and better than two hours, so a
failure near the end discarded everything already done. The unit of work was one
group; the unit of durability was the whole run. Now committed in chunks of 60
(`PERSIST_CHUNK_GROUPS`), bounding loss to roughly two minutes.

The run row had the mirror-image problem: flushed but not committed until
completion, which made `status="running"` a value the schema declares and **no
reader could ever observe**. Confirmed against a live job — over an hour in, 718
groups analysed, and `correlation_runs` contained nothing but `completed` rows.

Making runs visible forced a second change in the same commit. `correlation_findings`
defaulted to the newest run *regardless of status*, which was correct only while
running rows were invisible — the endpoint's correctness rested on a transaction
boundary in a different module. Left alone, this commit would have replaced the last
complete answer with an empty in-progress one for the entire length of every run.
It now selects the newest **completed** run; an explicit `run_id` still returns
whatever it names, so a run in progress stays inspectable.

Verified against the real database: with a synthetic `running` run inserted, the old
rule selects it and returns 0 findings where the new reader still returns 241.

Equivalent path checked rather than assumed: extraction runs already commit `running`
early, so the pattern is not repeated. The 5 stale `running` extraction rows all
produced 0 rules — nothing leaked.

---

## Open items

### 1. A neutral `EffectType` — decide before shipping the trusted-config UI

`_RULE_TYPE_MAP` (`formulation_mapping.py:96,98`) sends both `DEFINITION` and
`CLASSIFICATION` to `ALLOW` for want of anywhere truthful to send them.

Blast radius: `contracts/policy.py` `EffectType`, the evaluator's outcome vocabulary,
`_RULE_TYPE_MAP`, the effect badges in the review and policies UI, and 149 existing
`payload_json` rows (JSONB, so no schema migration, but a backfill decision).

**Ordering matters.** This is latent only because the affected rules are
`machine_executable=false`. A trusted-config UI is precisely what makes them
executable, at which point the evaluator starts returning ALLOW for text that says
"shall not". Settle this first.

### 2. Trusted-config UI

The proven capability gap: per-policy-set storage, an editor, and threading into the
extract call. A backend `trusted_config` body param on the extract endpoint was
reportedly added by a concurrent session — verify before rebuilding it.

### 3. MHRSD extraction defects

Quality evaluation surfaced real content problems, not formatting noise:
`incomplete_amendment` (Article 38 says "to read as follows" with no replacement
text), two conflicting settlement deadlines (90-day vs 70-day),
`template_content_treated_as_law` (blank model-contract fields approved as standalone
obligations), and conflicting Saudization standards (75% floor vs activity-specific
rates, no precedence). These need reviewer decisions, not code.

### Why no bulk approval

Deliberate. Quality runs on both sets surfaced polarity reversals, blank contract
templates treated as law, a "Repealed" rule still active, amendments with no
replacement text, and conflicting deadlines. Bulk-approving ~1,833 unreviewed rules
with known defects would launder them into an approved state — the exact outcome the
platform exists to prevent.

---

## Environment facts

- Python is always `.\.venv\Scripts\python.exe`.
- Postgres on **5433**:
  `docker exec policy-postgres psql -U policy_admin -d policy_platform -c "..."`
- Web **5174**, backend **8010**. Liveness is `/api/policy-sets` — there is no
  `/api/health`.
- **The backend runs without `--reload`.** Backend changes are not live until the
  process restarts.
- `candidate_rules` has no `description` column — it lives inside `payload_json`.
- `correlation_findings` joins on **`run_id`**, not `correlation_run_id`.
- `ConditionOperator` members are `EQUALS`/`NOT_EQUALS`, not `EQ`.
- `CorrelationFinding.classification` literals are upper snake case
  (`DIRECT_CONTRADICTION`), and findings deduplicate on rule identity, not on
  `reason`.
- PowerShell `git commit -m` mangles multi-line messages containing quotes or
  braces. Write the message to a file and use `git commit -F`.
- antd 6: `.ant-tabs-tabpane` reads empty; use `document.body.innerText`.

## Concurrency

This folder is shared with at least one other active session. Stage files by
explicit path — never `git add -A`.

Three cross-session claims failed verification in a single exchange: a test count
of 252 against a measured 322, a TypeScript error that was twice unreproducible, and
a handoff that "verified" frontend work against this session, which touched no
frontend files at all. Treat cross-session handoff summaries as unverified until the
actual file list is checked.

---

## Verification standing at handoff

- **322 unit tests passing** in `tests/unit`.
- Correlation reader fix verified against the live database, including that an
  explicit `run_id` still returns a run in progress.
- GUI verified at real scale: dashboard, Correlation tab counters matching the
  database exactly, Dismiss persistence (reverted afterwards), and Review Queue
  pagination over 668 rules.
- `saudi-labor-law` correlation complete: 959 groups, 241 findings stored, 53 at
  critical or high. Sampled and confirmed to be genuine legal contradictions.
- "Delete old entries" satisfied: exactly one `extraction_run_id` per set. The
  duplicate descriptions within a run are genuine source repetition — the same
  sentence closes several consecutive articles — and correlation already classifies
  them as `DUPLICATE` for reviewer disposition.
- MHRSD correlation was still running at handoff (1,009 of 1,763 groups). It loaded
  its modules before `b7d9562`, so that run is still all-or-nothing; the durability
  fix applies from the next run onward.
