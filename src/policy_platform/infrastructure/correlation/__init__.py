"""Finding what one rule has to do with another.

Two different questions, kept in one place because both answer "which rules
relate, and how".

`relationship_discovery` derives links deterministically from what a document
states -- shared anchors, numbering, explicit cross-references. It never infers
a relationship from wording or layout, because consumers read `related_rule_ids`
as established fact. Three detectors that could not fire were deleted rather
than left looking active; `docs/relationships.md` records which and why.

`correlation_agent` and `correlation_service` ask the harder question -- whether
two rules contradict, overlap or duplicate -- and that one needs a model. Its
answers are findings for a human to accept or reject, stored as runs so a
finding is always a statement about the rules as they stood at that moment.
Nothing here reaches a published version on its own.
"""
from __future__ import annotations
