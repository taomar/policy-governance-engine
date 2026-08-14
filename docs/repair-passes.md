# Repairing findings, not just reporting them

**Status: a design decision that has been taken and not implemented.** One pass
exists. Everything else on this page is proposed. The distinction is marked at
every point below, and it matters more than usual here — this repository has
already been damaged once by a design document that read as a description.

---

## What exists today

| | |
|---|---|
| The pass | `infrastructure/consolidation/duplicate_records.py::repeated_records` |
| Its caller | `scripts/consolidate_duplicates.py`, which writes only with `--apply` and reverses with `--undo` |
| Its tests | `tests/unit/test_a_record_emitted_twice_is_one_record.py`, `tests/unit/test_consolidation_can_be_run_twice_and_undone.py` |
| Its reachability | quarantined in `tests/unit/test_capabilities_are_reachable.py` — no production caller |

That is the whole of it. Nothing else described here is built.

## The observation

This system has roughly a dozen detectors and one remediator.

Every other finding is computed, stored, rendered to a reviewer, and acted on by
nothing. The system can tell you a condition holds and cannot do anything about
it, which places the entire remediation burden on the person least equipped to
carry it at scale — and does so silently, because a finding that is displayed
looks like a finding that is handled.

## Why many passes rather than one

Because each class needs a *different* remedy, and a single pass cannot hold
them. This is the proposed set; only the first exists:

| Finding | Proposed remedy |
|---|---|
| A record emitted twice | discard one — no judgement (**built**) |
| Polarity lost between canonical and projected effect | re-derive deterministically |
| A decision split across records; a qualifier promoted to a rule | re-formulate from the clause, with faithfulness as the acceptance test |
| A cut that lost its antecedent | widen the span and re-formulate |
| An attribute not present in the source | **propose only** |
| A record not decidable as written | **do nothing** |

The last two rows carry the argument.

**Propose only**, because that check is a term search, and a term search has
false positives. Dropping a record on one destroys content that was really
there. The asymmetry is total: a false positive that only proposes costs a
reviewer a moment, and a false positive that deletes costs a record nobody knows
is missing.

**Do nothing**, because a record that cannot be decided as written is a finding
about *the document*, not a defect in extraction. There is nothing to repair.
Anything that "fixed" it would be inventing a test the source declined to state.
This is the line most likely to be forgotten and the most expensive to relearn,
which is the only reason it is written this prominently.

## The contract any such pass would have to meet

Every clause below is already met by the built pass. They are stated as
requirements because each was paid for once and none is obvious.

- **Never compose.** A pass that produces text produces it from the source,
  never by joining records. **Merging is not the inverse of splitting** —
  concatenating two records yields prose that is neither record's words. The
  safe operation is to discard both and re-formulate over the union of their
  source spans.
- **Idempotent, asserted as the whole table unchanged.** Not as "the second run
  removed nothing": a pass that removed one row and resurrected another would
  also report nothing removed.
- **Reversible by marking rather than deleting, and undo must find its own rows
  by the note it wrote.** Anything that instead searched by shape would
  resurrect records some other mechanism had legitimately superseded. The built
  pass writes into `review_notes` and its comment records the further
  consequence: a record already carrying a reviewer's own note cannot be
  superseded without either destroying that note or becoming unrecoverable.
- **Individually attributable**, so any movement in the totals decomposes into
  named causes with zero residual. Otherwise a pass that changes counts is
  indistinguishable from a pass that has a bug.

## Ordering would be a real constraint, not a preference

Deduplicate before re-formulating, or the same clause is paid for twice.

Repair projection before proposing anything to a human, because a record whose
projected effect contradicts its own subject should not reach a reviewer as a
judgement call. Asking someone to adjudicate a record that is internally
inconsistent spends their attention on our defect and teaches them to distrust
the queue.

## The honest limit

The two largest finding classes cannot be repaired this way. Measured by
`scripts/consolidation_sizing.py` across four sets:

| Class | Counts | Reachable by repair |
|---|---|---|
| `attribute_not_in_source` | 46 / 45 / 29 / 21 | proposal only, never automatic |
| `not_decidable_as_written` | 16 / 31 / 22 / 33 | none — not a defect |

Realistic reach is on the order of **fifty to sixty records in 1,249**.

**Worth building. Not a cure.** Stated here rather than in a footnote because a
document that implies otherwise sets the next reader up to be disappointed and
then to overreach — and overreach in this particular direction means a pass that
deletes on a false positive.

## Build the runner first

`repeated_records` sits in the reachability quarantine because nothing in
production calls it. The agent that built it recorded that entry as debt it had
created, on a list whose own docstring says it *can only shrink*.

Five more passes added the same way would be five more entries on that list.

So the proposed order is: **one reachable entry point first**, owning ordering
and reporting, with passes registered into it. Adding passes before the runner
would recreate this session's defining failure — capability that exists, is
tested, and is not reached — deliberately, in a new place, immediately after
writing three pages about why that happens.

The quarantine entry cannot rot quietly: `test_every_quarantine_entry_is_earned`
fails the moment a quarantined symbol acquires a production caller, so
connecting the pass forces its own removal from the list.

Note what kind of entry this is. Every other item in that quarantine is either
deliberate tooling or an oversight. **This one is a temporary state entered on
purpose, for a stated reason** — extraction runs are the measurement baselines
this work is judged against, and a pass that removes records would alter a
baseline while it was being recorded. That reason expires. The distinction
between "not connected yet, on purpose, until X" and "not connected, nobody
noticed" is exactly the kind that decays into folklore, which is why it is
written here while it is still fresh.

---

## Related

- [The running path](running-path.md) — what production actually reaches, and
  the three ways a capability can look whole and not be
- [Designed pipeline and running pipeline](failures/designed-pipeline-and-running-pipeline.md)
  — the failure this page is written to avoid repeating
- [Known limitations](known-limitations.md) — what a reader should know before
  relying on this build
