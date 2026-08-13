"""Checking an extraction against the document it claims to describe.

Three passes over the same question -- does this record say what the source
said -- separated by what each is able to prove.

`policy_faithfulness` and `logic_faithfulness` are deterministic. They compare a
record against its source text and its own condition tree, so a span that is not
verbatim, or a tree that does not match the formulation it came from, is caught
by comparison rather than by reading. `ai_quality` handles what comparison
cannot reach: duplicates, contradictions and instability across a run, where
judging needs a reader.

Five of the recorded mutations name `ai_quality`, more than any other module.
They guard two things that are easy to get wrong in the same direction: that
duplicate detection groups on the sentence rather than on the classification,
and that a record decided by reading is described as a route rather than
reported as a defect. `ai_ready` is not a fault, and a quality pass is the most
tempting place to start treating it as one.

Findings are stored as runs, so a finding is always a statement about the rules
as they stood at that moment rather than a claim about them now.
"""
from __future__ import annotations
