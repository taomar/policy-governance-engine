"""Folding back what the extractor emitted more than once.

Everything else in this system detects. `decision_families`, `self_containment`
and the quality checks all end by telling a reviewer something is wrong, and a
reviewer who is told a thousand true things and given no lever is worse served
than one who is told a hundred. This package is where a finding turns into an
action.

Consolidation is three operations wearing one name, and they carry very
different risk, so they are built and reasoned about separately rather than as
one pass:

- **identity** (`duplicate_records`) — the same record, from the same span,
  emitted twice. There is no judgement in it, so it can act.
- **one clause, a detected family** — a decision split across records that
  belong together. The safe operation is to re-formulate a single record from
  the source span, never to stitch two outputs into one; that is why this is a
  separate tier and not a flag on the first.
- **neighbouring records** — deliberately not built. Sized first and found to be
  mostly noise, and it is the tier where a real distinction between two
  obligations gets destroyed.

The rule that shapes all of it: **merging is not the inverse of splitting.**
Two records concatenated produce words that are neither record's and possibly
not the document's, and composition is the one thing this product must never
do. So consolidation either discards an exact repetition, or it goes back to
the source and formulates again. It never joins two outputs.
"""

from __future__ import annotations
