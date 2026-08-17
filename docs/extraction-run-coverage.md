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

**A gap that remains after one automatic recovery is still closed only by
re-running extraction.** A batch lost to a *transient* failure to reach the
extractor — a DNS or transport blip the per-call retries could not outlast — now
earns exactly one re-read at the end of the run, before coverage is judged, so a
whole document need not be re-extracted to recover a handful of batches
(`_retry_unread_batches` in `infrastructure/extraction/ai_extraction.py`; the
retryable set is snapshotted first, so it is one pass and not a loop). A
recovered batch is relabelled `batch_recovered` and keeps its first-attempt
reason with a note appended (`mark_recovered`), so the retry stays visible in the
ledger rather than being erased, and the run summary reports the document was
covered in full on a retry instead of staying silent. Two things are still never
re-read: a batch that fails that single attempt keeps its skip and the run still
reports it should be repeated; and a judgement — a sentence read and not
extracted — is left as it is, because the model answered and re-asking it would
be rolling the dice until the answer changed (`is_retryable_skip`). Closing
either of those means running extraction again.

---

## A failed run can leave the reviewer with less than they started with

This is not about coverage status, and coverage status does not fix it. It is
recorded here because it is the other way a run can end badly, and because the
two are easy to confuse.

Two decisions in `extract_candidate_rules`
(`infrastructure/extraction/ai_extraction.py`) are each individually correct and
each individually reasoned in a comment:

1. **Results are persisted and committed per batch, not once at the end.** The
   comment gives the reason: these runs take tens of model calls over tens of
   minutes, so an all-or-nothing transaction would discard every completed batch
   on a late failure and leave reviewers unable to tell progress from failure.

2. **The previous run's unreviewed candidates are superseded on the first batch
   that produces output**, in the same transaction as that batch's inserts. The
   comment gives the reason: the queue should never hold two runs at once, and
   should never lose the old set without gaining a new one.

Both hold. Neither is wrong. Read together they say: *the old set is discarded
once the first batch succeeds, and each later batch is kept as it lands.*

So a run that supersedes at batch 1 and fails at batch 3 of 20 leaves the
reviewer holding two batches where they previously held a complete set. The
guarantee in the second comment — never lose the old set without gaining a new
one — is true at the instant it executes and stops being true immediately after,
because "the new set" was one batch of twenty and nothing re-establishes the
old one.

### What changed and what did not

Retries closed one route into this. `infrastructure/ai/openai_client.py`
retries on `_RETRYABLE_STATUSES` and distinguishes `AzureOpenAITransientError`
from `AzureOpenAIError` precisely so a long loop can tell "this batch is bad"
from "the network hiccuped" — the first should skip the batch, the second
should not cost the caller the batches it already did. A stall that previously
ended the run now usually does not.

Deliberately not retried: anything else in the 4xx range. The client's comment
states why, and it is the right call — a bad body, an expired key or a missing
deployment is a defect in what was sent, and retrying it burns budget while
hiding the error that would have explained the failure. Retrying a malformed
request fails four times as slowly and reports the same thing.

**The interaction itself still exists.** Only the timeout path into it was
closed. A run that fails for a non-retryable reason after superseding still
leaves the reviewer with fewer records than before it started.

### Why this is left standing

Both fixes available are worse than the behaviour:

- Deferring the supersede until the run completes reintroduces the two-runs-at-
  once state the comment rules out, and holds it for tens of minutes.
- Restoring the old set on failure means un-superseding records the reviewer
  may already have acted on in the interval.

The composition is the defect, and neither decision is the one to change. What
was missing was anyone knowing about it, which is what this section is for.


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
