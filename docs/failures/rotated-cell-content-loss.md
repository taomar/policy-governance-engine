# Content lost in a rotated cell

A table cell painted along the vertical axis carried an operative provision. No
part of the system reported losing it, and two different converters were wrong
about it in two different ways.

This is a record of what happened, not a recommendation. The correction it
implies was measured and rejected.

---

## What the running system does

`infrastructure/ingestion/document_ingestion.py` drops glyphs whose `upright`
flag is false before grouping words into lines, and emits a diagnostic:

```
code="rotated_text_excluded"
severity="info"
detail=f"{rotated_count} rotated words excluded from the logical flow"
```

The comment above it states the reasoning plainly:

> Rotated text is almost always a watermark, sidebar label, or stamp. Left in
> the flow it interleaves with body text at arbitrary positions and corrupts
> reading order, so it is excluded and reported rather than silently mixed in.

Every clause of that is defensible. Rotated glyphs *usually* are furniture.
Interleaving them *does* corrupt reading order. Exclusion *is* reported rather
than silent. The decision was reasoned, the reasoning was written down, and the
diagnostic was emitted.

**It was still wrong for this page, and nothing said so.**

## Why the report did not help

The diagnostic exists, so this is not a silent drop in the strict sense. It is
worse than a silent drop in the practical sense, for three reasons.

1. **It is filed at `info`.** `info` is the severity a reader uses to decide
   what to skip. A count of excluded words is exactly the shape of a line that
   gets skipped.

2. **It reports a quantity, not a kind.** A watermark and a merged cell
   carrying a provision both arrive as *n rotated words excluded*. The
   diagnostic cannot distinguish the case it was designed for from the case
   that loses content, because the only signal it carries is how many.

3. **The base rate argues against the reader.** Because rotated text usually
   *is* furniture, a reader who investigates this diagnostic is wrong almost
   every time. A warning that is a false alarm nine times in ten trains the
   person reading it to dismiss the tenth.

The pattern generalises past this defect: **a diagnostic whose severity is set
from the common case cannot alert on the uncommon one.** Severity encodes a
prior. When the prior is right, the exception is unreachable.

## The other converter, and the other failure

A second converter available in the tree does not drop the run. It reads it —
and reads it in paint order, which for that orientation runs opposite to
reading order. The characters arrive reversed.

Reversed text is not obviously reversed to anything downstream. It has the
right characters, the right length, and the right shape. It passed through
extraction and reached a record's title verbatim, where it was stored as the
title of a real record.

Note which check did not catch it. Verbatim validation compares a model's output
against the batch the model was shown. Both sides of that comparison contained
the same reversed string, so the check passed — correctly, on its own terms. It
proves the model copied. It has never proved that what it copied matches the
source. See [Known limitations](../known-limitations.md) and
[AI assistance](../ai-assistance.md), where that boundary is stated.

## The row-attachment loss, which is separate

The provision in the merged cell is attached, structurally, only to the first
row it spans. Of the eight rows the cell covered, one carried it and seven did
not.

This is not a rotation problem and would survive a perfect fix to the rotation
problem. Reading the cell correctly and attaching it to one row still produces
seven records that are wrong in a way no downstream check can see: each is
individually well-formed, individually verbatim, and individually missing a
constraint that the page applies to it. There is no defect in the seven records.
The defect is between them and a cell they never referenced.

Detection for records that cannot be read without a neighbour exists —
`discover_split_decision_relationships`, step 17 on
[the running path](../running-path.md) — but it operates on extracted records,
and these seven do not look incomplete. They look complete and are false.

## Why nothing was changed

The converter that reads the rotated run rather than dropping it was compared
against the one that drops it — `infrastructure/docling/shadow_comparison.py`
exists to produce exactly that comparison, and states in its own docstring that
it is not part of the ingestion path. **The alternative scored worse overall.**

So the choice was between:

- keeping a converter that is better on average and loses this content, or
- adopting one that recovers this content and is worse everywhere else.

Neither is a fix. Trading a broad regression for a narrow recovery is a bad
trade, and taking it because the narrow case is the one currently in front of
you is how a system gets tuned to its most recent bug report.

The change was not made. **This document is the deliverable.** The loss is now
written down, attributable, and findable by the next person who sees a record
whose text is right and whose meaning is missing — which is the only outcome
available when both options are worse than the status quo.

## What would actually resolve it

Not recorded here as a plan, because none of it is built:

- A rotated run that sits inside a cell boundary is not the same object as a
  rotated run that floats over body text. Geometry can distinguish them. The
  current check reads one boolean per glyph and cannot.
- Reading a rotated run correctly is a coordinate problem with a known answer;
  it is *reversal* that is unsafe, for the reason
  `infrastructure/ingestion/reading_order.py` documents at length — reversing a
  run repairs its letters and destroys every number inside it, because a number
  is an opposite-direction sub-run. Any correction has to be per-run and driven
  by coordinates, never by reversing a string.
- Attaching a spanning cell's content to every row it spans is a structural
  change to how table geometry becomes records, not an ingestion tweak.

## The lesson

Three separate mechanisms behaved correctly and the content was still lost:

| Mechanism | Behaved correctly by | Missed it because |
|---|---|---|
| Rotation exclusion | reporting rather than dropping silently | severity was set from the common case |
| Verbatim validation | comparing output to input | both sides held the same corrupt text |
| Record-level checks | validating each record | each record was individually valid |

None of them failed. The loss happened in the gaps between them, and every gap
was created by a boundary that was reasonable in isolation. That is the same
shape as
[the designed pipeline and the running pipeline](designed-pipeline-and-running-pipeline.md):
**every individual piece was real, and the composition was not what anyone
believed it was.**
