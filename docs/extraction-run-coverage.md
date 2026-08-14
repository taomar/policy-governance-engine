# Extraction run coverage

**A run that finished and a run that read everything are not the same run, and
the system now says which one it was.**

An extraction run closes in one of three states.

| Status | Meaning |
|---|---|
| `completed` | The run finished and read everything it was handed |
| `completed_with_gaps` | The run finished, but passed over material |
| `failed` | The run did not finish |

`completed` and `completed_with_gaps` are defined in
`infrastructure/persistence/repositories/candidates.py` as `RUN_COMPLETED` and
`RUN_COMPLETED_WITH_GAPS`, and set by `ExtractionRunRepository.mark_completed`.

This page is about the middle row: why it exists, why adding it was a correction
rather than a refinement, and why the reasoning is worth more than the values.

---

## The status was already load-bearing

Before there was anything to distinguish, `completed` was already doing work
well beyond describing how a run ended. It was the trustworthiness predicate.

When a run finishes, it compares itself against the previous generation of rules
for the same document, so a reviewer is shown what changed rather than the whole
corpus again. `_load_baseline_candidates`
(`infrastructure/extraction/ai_extraction.py`) picks that baseline, and it does
not pick the most recent run. It picks the most recent run that finished, with a
`WHERE` clause on `ExtractionRun.status == "completed"` and a comment saying
exactly why:

> Only a run that finished is a trustworthy reference. A run that failed or was
> interrupted holds however many rules it managed to commit before it stopped,
> and comparing against that partial set would report every rule it never
> reached as brand new — the exact noise this is meant to remove.

That comment is correct, and it is a rule about **partial readings**, not about
crashes. A crash was simply the only way a partial reading was known to arise.

## A skipped run was partial in exactly that sense

A batch whose agent fails does not fail the run. It is appended to a `skipped`
ledger and the loop continues, which is the right behaviour — one bad batch in
sixty should not discard the other fifty-nine.

But the run then closed as `completed`. So a run that had demonstrably not read
part of the document was, by the predicate above, a trustworthy baseline. The
comment forbidding a partial baseline was being obeyed to the letter and evaded
in substance.

## The delta lied in both directions

This is the part worth keeping, because the failure is symmetric and only one
half of it is intuitive.

**When a partial run is the baseline.** Rules the baseline never reached appear
in the next run and are reported as **new**. They are not new. They were in the
document the whole time; the previous run did not get to them.

**When a partial run is the current run.** Rules the current run never reached
are absent from its output, so the delta reports them as **no longer found**.
They are still in the document, on the page, unchanged.

The second is worse than noise. "No longer found" is a claim about *the
document* — it says a policy that used to be stated is not stated any more.
That is a substantive assertion about the source material, and it was being made
on the strength of how much of the source material we managed to read.

The general form: **a shortfall in the extraction was being reported as a
property of the thing extracted.** The two are never interchangeable, and when
they are confused it is always in the direction that flatters the extractor.

---

## How coverage is decided

Coverage is derived, once, at the end:

```python
await run_repo.mark_completed(run, coverage_complete=not skipped)
```

It is read off the same `skipped` ledger every skip point already appends to,
rather than from a flag each site has to remember to set. That is deliberate: a
skip point added later is counted whether or not its author thought about the
run's status. The failure mode of the alternative — a new skip that quietly does
not reduce coverage — is precisely the one this change exists to close, so it
would have been a poor design to reintroduce.

Four places append to `skipped` today: a batch whose passage extraction failed,
a passage discarded for not being a verbatim substring of its source, a batch
whose formulation failed, and individual formulations that could not be mapped.
The list is not the point; the ledger is.

### What belongs in the ledger, and what does not

Because coverage is read off `skipped`, the ledger's meaning has to stay exact:
**an entry means material was not read.** Anything else appended to it silently
changes what the run's status asserts.

The case to watch is a rule recorded more than once — a model restating itself,
or two passes over the same material. That is not a gap. The material was read;
it was recorded twice. Appending it to `skipped` would mark a run
`completed_with_gaps` for having read the document correctly, which inverts the
meaning of the status.

This is a constraint on skip points rather than a description of a mechanism.
Deriving coverage from the ledger is what makes a new skip count automatically,
and it is the same property that makes the ledger's meaning load-bearing:
whatever is appended to it inherits that meaning, whether or not the author
appending it was thinking about run status.

### Why no migration was needed

`ExtractionRun.status` is a free-text column, not an enumeration, so a fourth
value costs nothing at the schema level.

More usefully, the baseline query filters on the string `"completed"`. A run
recorded as `completed_with_gaps` therefore stops being eligible as a baseline
without that query being touched at all. The correction lands where the value is
written, and every consumer that already asked "did this run finish cleanly?"
gets the better answer for free.

---

## What this does not fix

**A partial run is still shown to the reviewer as a delta.** The status stops it
being used as a *baseline*; it does not stop the current run reporting its own
partial output as a comparison. That is why the run summary appends a plain
sentence when anything was skipped — the count of items passed over, and the
statement that the run did not read the whole document — rather than relying on
the reviewer to notice a status code.

**The in-flight progress record cannot carry the distinction.** Its status is
typed as `"running" | "completed" | "failed"` in `apps/web/src/api.ts`, which
belongs to another workstream. The shortfall travels in that record's free-text
stage instead. The durable status on the run is the one to trust.

**Nothing re-reads what was skipped.** A gap is recorded, reported, and left.
Closing it means running extraction again.

---

## The attribution rule

Stated once, because everything above is an instance of it:

> Material passed over is material this system did not read. It is not material
> the document failed to state.

Every message about a run should be able to survive that substitution. When a
sentence about coverage can be rewritten as a sentence about the source and
still sound reasonable, the sentence is wrong.

See [The running path](running-path.md) for where `mark_completed` sits in the
sequence, and [Known limitations](known-limitations.md) for what else a green
run does not promise.
