# A trace into a deleted file, and a defect that outlived its report

Two briefs in one body of work pointed at a `file:line` that no longer existed.
Acting on either literally would have produced a confident diagnosis of a defect
that was somewhere else. They are recorded together because the shape repeated,
which makes it a trap in the method rather than a one-off slip.

Both come from the same period. Several forked renderers on the Policies page —
`PublishedPolicyCard.tsx`, `publishedPolicyCards.ts`, `PublishedRecordActions.tsx`,
`RuleDetailInline.tsx` — were deleted once a shared component replaced them, and
briefs written against the old layout still cited their line numbers.

---

## 1. A defect can survive the deletion of the file it was reported in

A container-label defect — a heading-only passage labelled with the handbook's
own title — was reported at `PublishedPolicyCard.tsx:145`, a call to
`policyTopicLabel(card.policy)` with no name supplied. That file had already been
deleted. The reported site did not exist.

**The symptom was still real.** `PoliciesTab` was reintroducing the same missing
input one level up, by a different mechanism from the one that caused it on the
review side. Deleting the fork removed the *file* the defect was reported in and
did not remove the *defect*.

The lesson is not "the report was stale." It is that **a symptom and the file a
report attributes it to are two different facts**, and confirming the file is
gone tells you nothing about whether the symptom is. The fix supplied the
missing input where the surviving code needed it, derived exactly as the review
side already did.

---

## 2. Check that a file exists before acting on a trace through it

A regression — a rule's detail opening as a flat stack instead of the tabbed
inspector — was handed over with the trace `PublishedPolicyCard.tsx:168,380 ->
RuleCard`. That file did not exist; it had been deleted alongside
`publishedPolicyCards.ts` in the same change. Reading its old line numbers would
have produced a precise account of a defect that was not there.

The real site was `ComparePage.tsx`, which expanded a diffed rule into a flat
`RuleCard` and had simply never been converted when every other surface was. It
was found by looking for the on-screen fingerprint — `Record details`, which
only `RuleCard` prints — not by following the trace.

This was the **second** brief in a row to cite a `file:line` inside a file
already removed. Reading a deleted file's old line numbers produces a confident
diagnosis of a defect that is somewhere else entirely.

---

## The rule this produced

> **A `file:line` in a report is a claim, not a location. Confirm the file
> exists before you trace through it, and confirm the symptom independently of
> the file a report blames — a defect can outlive the file it was reported in.**

It is sharpest where files are being deleted. A cleanup that removes a fork does
not retire the briefs written against it, and the next reader inherits traces
that resolve to nothing. The same caution applies to retiring a working document
that logged live defects: carry the defects out before deleting the file, or
they vanish with their only record.
