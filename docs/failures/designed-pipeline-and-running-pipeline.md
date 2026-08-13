# The designed pipeline and the running pipeline

**The extraction pipeline that was designed is not the one that runs, and the
difference is not visible from any single file.**

Ten dead subsystems were found independently over one session — an unreachable
converter, verification gates nobody calls, cell coordinates dropped at the
database write, a reading plan that is only ever displayed, a stage table
nothing writes. They are not ten defects. They are one fact seen from ten
angles: `run_extraction` defines nine stages, production reaches the first two,
and everything after that was re-implemented as fixed-size character windows.

Each piece stayed hidden because the scaffolding around it is real. There are
endpoints, there is a UI tab, there are passing tests. A reader opening any one
file finds working code.

Evidence below is cited by file and line so it can be checked rather than
believed. The measurements come from one bilingual PDF used as a regression
witness; it is the vehicle for the measurement, not its subject, and no figure
from it should be read as a general rate.

---

## 1. The two pipelines

`run_extraction` (`src/policy_platform/infrastructure/docling/pipeline.py`, line
133) defines nine stages:

| # | stage constant | value | line |
|---|---|---|---|
| 1 | `STAGE_SOURCE_ACCEPTED` | `source_accepted` | 154 |
| 2 | `STAGE_CONVERTED` | `docling_converted` | 160 |
| 3 | `STAGE_CANONICAL_FROZEN` | `canonical_artifact_frozen` | 169 |
| 4 | `STAGE_STRUCTURE_BUILT` | `deterministic_structure_built` | 192 |
| 5 | `STAGE_CONTEXT_UNITS` | `context_units_assembled` | 201 |
| 6 | `STAGE_GRAPH_DISCOVERY` | `graph_discovery_completed` | 210 |
| 7 | `STAGE_SPANS_RESOLVED` | `exact_spans_resolved` | 220 |
| 8 | `STAGE_CANDIDATES` | `canonical_candidates_proposed` | 226 |
| 9 | `STAGE_VERIFIED` | `verification_completed` | 270 |

`run_extraction` has no caller in `src/policy_platform`. It is invoked from
`tests/unit/test_docling_pipeline.py` and `scripts/docling_corpus_report.py`.

What production runs instead:

* **Upload** — `src/policy_platform/api/routers/documents.py` line 153 calls
  `extract_document`, the seam in
  `src/policy_platform/infrastructure/ingestion/document_extraction.py`. This
  covers stages 1 and 2.
* **Persist** — `clauses_from_document` in the same file flattens elements to
  `ClauseData`.
* **Extract** — `src/policy_platform/infrastructure/extraction/ai_extraction.py`
  batches those clauses by character count (`_batch_clauses`, line 120) and calls
  a passage agent and then a formulator per batch (lines 641 and 718).

Stages 3 through 9 have no counterpart in that route. They are not skipped by a
branch; there is no branch. The two implementations do not meet.

### The three `build_reading_plan` call sites

This is the part that explains why the layer looks alive.

| site | what it is |
|---|---|
| `src/policy_platform/api/routers/extraction.py` line 246 | `GET /{id}/reading-plan` — renders the plan as JSON for a reader |
| `src/policy_platform/api/routers/extraction.py` line 332 | `GET /{id}/coverage` — derives a coverage report from the plan |
| `src/policy_platform/infrastructure/docling/pipeline.py` line 202 | inside `run_extraction`, which production does not call |

So `build_reading_plan` **is** reached in production — by two read-only
endpoints that display it. It never reaches the model. The coverage endpoint's
docstring promises the report "stays truthful when clauses change", and it does:
truthfully describing a plan nothing extracts from.

`_add_table_context` (`src/policy_platform/contracts/reading_plan.py`, lines 305
onward) is the function that pulls `header_for`, `merged_with`, `table_cell_of`
and caption edges into a cell's context. Its docstring states the intent
exactly — *"A cell reading '15 minutes' states nothing on its own; its meaning
lives entirely in the column header and the row label that frame it."* It is
reachable only from the three sites above.

---

## 2. The entire context contract

This is what addresses a clause to the model. `_render_batch`,
`src/policy_platform/infrastructure/extraction/ai_extraction.py` lines 151-170:

```python
def _render_batch(clauses: list[Clause]) -> str:
    """Render clauses with an unambiguous addressing marker.

    The section label is deliberately on its own line rather than inside the
    marker. When it was rendered as `[clause_ref=p3-E000016 (Article 2)]`, the
    "identifier exactly as supplied" that the agent was told to echo back was
    genuinely ambiguous — the ref and the section were one undelimited string —
    and the agent returned the decorated form, which matched no clause. That
    was survivable while verbatim verification did all the work, but a span
    reference is only useful if it resolves, so the label must contain exactly
    one identifier and nothing else.
    """

    parts = []
    for c in clauses:
        header = f"[clause_ref={c.clause_ref}]"
        if c.section:
            header += f"\n(section: {c.section})"
        parts.append(f"{header}\n{c.text}")
    return "\n\n".join(parts)
```

`clause_ref`, `section`, `text`. No graph, no headers, no context units. Eleven
lines of body are the whole contract between the document and the model.

Batching is by running character length in stored order — `_MAX_CHARS_PER_BATCH
= 4000`, line 117. The file says so itself at line 699: *"a document is walked
in fixed-size windows, not one topic at a time"*.

---

## 3. The measured regression

A converter setting exists at the upload seam (section 5). Enabling it today,
with the reading plan out of the path, makes table extraction worse. Both
renderings below are the production `_render_batch` over the real output of each
converter for the same source row.

**Legacy** — one clause, the row intact:

```
[clause_ref=p21-E000441]
1. |  | Late for work, 15 minutes or less without permission or a valid
reason, if it did not cause delay to other employees. | Written Warning |
5% deduction | 10% deduction | 20%deduction | ...
```

**Structured converter** — the same row becomes eight separate clauses:

```
[clause_ref=p21-E8929efbeb2ad0b8a]
Late for work, 15 minutes or less without permission or a valid reason...

[clause_ref=p21-Eca51eba927b763d8]
Written Warning

[clause_ref=p21-E3487ee2383856166]
5% deduction

[clause_ref=p21-E08e22fae5286726a]
10% deduction
```

The headers exist in the structural graph for that table — nine header cells,
including one spanning four columns and three naming successive occurrences.
Measured, over the same rendering: **header text reaching the renderer:
`False`**.

A clause reading `5% deduction` alone carries neither what it is a penalty for
nor when it applies. The row's four outcomes become four disconnected clauses,
each well-formed and none interpretable. That is a worse failure than the
flattened row, which at least keeps a row's values adjacent in one string.

Two further severances sit behind this one, each independently sufficient:

* **Persistence drops cell position.** `ClauseData`
  (`src/policy_platform/infrastructure/ingestion/document_extraction.py`, line
  43) has no `table_id` and no `table_cell`. Measured over a synthetic table:
  6 `table_cell_of` and 3 `header_for` edges before the write, **0 and 0** after
  the round trip, while `element_type="table_cell"` survives — so a cell still
  looks like a cell downstream while carrying no position.
* **Text order.** Neither converter reads direction evidence from the source;
  each applies a fixed policy. Recorded in
  `docs/specs/docling-integration-operating-notes.md`.

---

## 4. Dependency order

Stated as an ordering constraint discovered by measurement, not as planned work.
Each step is inert until the one above it holds.

1. **`ClauseData` and the schema carry `table_id` and `table_cell`.** Until then
   steps 2 and 3 have nothing to operate on, because position is discarded at
   the write.
2. **`build_reading_plan` feeds the batcher in place of `_batch_clauses`.** This
   is what would let a cell arrive with the header that governs it.
3. **The converter default may then change**, text order permitting.
4. **Verification gates** — see section 6.
5. **Cross-page header association**, which is upstream in the converter: it
   emits each page's grid as a separate table, so a body row on a continuation
   page has no header row to resolve against.

Steps 1 and 2 are each larger than the whole of the work recorded in section 5.
Doing 3 before 1 and 2 produces the regression in section 3.

---

## 5. What is already in place

So it is not rebuilt:

* **A converter seam and its setting.**
  `src/policy_platform/infrastructure/ingestion/document_extraction.py` decides
  how an upload is parsed, selected by a setting in
  `src/policy_platform/infrastructure/settings.py`. The default is unchanged.
  An unavailable structured stack raises rather than falling back silently.
  `extract_clauses` in the same file routes through the seam rather than around
  it.
* **Two general table-structure fixes** in
  `src/policy_platform/contracts/structural_graph.py`: a header now heads every
  column it spans rather than only its starting column, and merged cells are
  connected without depending on placeholder cells that no converter emits.
  Guarded by `tests/unit/test_table_spans_reach_their_headers.py` over five
  table shapes. These are prerequisites; on their own they do not change
  extraction output, because nothing in the running path consumes the edges.
* **A text-fidelity diagnostic** at the seam, reporting display-glyph storage
  from a Unicode character property rather than a script range.
* **A paired control fixture** — `tests/fixtures/text-order/` — two PDFs
  differing only in the order their glyphs are painted, with a reproducible
  generator. Guarded by
  `tests/unit/test_extraction_preserves_stored_text_order.py`.
* **A reachability guard**, `tests/unit/test_capabilities_are_reachable.py`,
  which is what holds any of the above to being connected.

---

## 6. The three verification checks

Recorded here because their status was misstated once already, and the
correction is the useful part.

| check | status in the upload path |
|---|---|
| `verify_fragments` | **Runs**, in both parsers (`document_ingestion.py` line 330, `docling/converter.py` line 492). Records a `severity="error"` diagnostic. Nothing gates on it. |
| `plan.is_exhaustive` | **Computed and returned** (`api/routers/extraction.py` lines 246 and 251). Nothing gates on it. |
| `verify_structural_coverage` | **No production caller.** Only `docling/pipeline.py` line 194. |

Two are reported rather than enforced; one is absent. The distinction matters
because "not computed" and "computed and ignored" need different work.

One constraint on wiring the first: `_canonical_from_clauses`
(`src/policy_platform/api/routers/extraction.py`, line 60) rebuilds pages with
`raw_text=""`, so fragment offsets cannot resolve against anything there.

---

## What generalises

The lesson beside this one in
[`validators-that-could-not-fail.md`](validators-that-could-not-fail.md) was
that each check asserted more than its evidence supported. This is its
structural twin: **each of these subsystems is correct, tested, and connected to
something — just not to the path that runs.**

None was caught by a type check, a lint, or a passing suite, because nothing
here is broken in the sense those tools test for. Every one was caught by
following a call chain from a production entry point and noticing where it
stopped.

A test that a capability is reachable from production is therefore a different
kind of test from one that it works, and the second does not imply the first.
