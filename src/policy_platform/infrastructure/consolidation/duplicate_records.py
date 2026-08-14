"""A record the model emitted twice is one record.

Detection without remediation puts the work in the wrong place. This system can
already tell a reviewer that two records say the same thing and then asks them
to do something about it, which is the opposite of the division of labour that
makes review affordable. This module is the first thing that acts.

It acts only where there is no judgement to make. Two records cut from the same
source span, saying the same thing in the same words, are one record the model
emitted twice — a sampling artefact, not two facts. Nothing has to be decided to
know that, so nothing has to be reviewed.

## What it deliberately will not do

**It never merges.** Merging is not the inverse of splitting: concatenate two
records and you get prose that is neither record's words and possibly not the
document's. This pass only ever *discards a copy*, so the surviving text is
still exactly what the model produced for that span. Anything requiring two
records to become one differently-worded record belongs to a later tier, where
the operation is to re-formulate from the source rather than to stitch outputs.

**It never matches on absence.** Two records with no recorded span are not "in
the same span"; they are two records we cannot place. Two records with no
canonical rule core do not "say the same thing"; they say nothing we can read.
Grouping on missing data deletes records on the strength of what we failed to
record about them, and the live corpus is full of the missing data that would
do it — one whole run of 242 rows has no fingerprint at all, because the pass
that writes them runs after every batch and that run stalled before it.

**Same content is not enough — same *span* is the test.** A document may state
one obligation twice in two different places, and that is two facts about the
document. Collapsing them would silently rewrite what the document does.

## Identity

The identity is `rule_delta.semantic_core`, the same definition the cross-run
delta uses, plus the prose. One definition, because if consolidation and delta
disagreed about what makes two records the same, one of them would eventually
discard something the other would have kept.

Prose is added here and excluded there, deliberately and for the same reason in
both cases. The delta must see through a rewording, because the model rewords
freely between runs and a reviewer should not be asked to re-approve prose. This
pass must not, because within one run there is nothing to see through: two
records whose wording differs are not the repetition this tier exists to remove,
and if they should still become one record, that is a judgement and belongs to a
tier that makes judgements.

## Idempotence and reversibility

Both properties are structural rather than promised. The pass is a pure function
from records to a list of groups, so running it twice over the same input yields
the same groups; run it again once the redundant copies are gone and each group
has one member, which is not a group. And it *names* what it would discard
instead of discarding it, so the caller decides how to record the removal — this
system has already demonstrated what irreversible removal costs, when
supersession fired during a run that then failed and left a reviewer with fewer
records than they started with.
"""

from __future__ import annotations

from dataclasses import dataclass

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.infrastructure.projection.rule_delta import (
    NON_SEMANTIC_PROSE,
    semantic_core,
)


def source_span(payload: dict) -> str | None:
    """Where in the document this record was cut from, or None if unrecorded.

    None is never a group key. A record we cannot place is not in the same place
    as another record we cannot place.
    """
    lineage = payload.get("lineage")
    if isinstance(lineage, dict):
        elements = lineage.get("source_elements")
        if isinstance(elements, str) and elements.strip():
            return elements.strip()
    evidence = payload.get("evidence") or []
    if evidence and isinstance(evidence[0], dict):
        digest = evidence[0].get("source_hash")
        if isinstance(digest, str) and digest.strip():
            return f"hash:{digest.strip()}"
    return None


def _canonical_rule(payload: dict) -> dict | None:
    formulation = payload.get("formulation")
    if not isinstance(formulation, dict):
        return None
    canonical = formulation.get("canonical")
    if not isinstance(canonical, dict):
        return None
    rule = canonical.get("rule")
    return rule if isinstance(rule, dict) and rule else None


def record_key(payload: dict) -> str:
    """Everything this record says, in the words it says it in.

    `semantic_core` decides what a rule *means*; this adds the prose on top
    rather than redefining the core, so the two consumers of record identity
    cannot drift apart.
    """
    return canonical_hash(
        {
            "core": semantic_core(payload),
            "prose": {key: payload.get(key) for key in sorted(NON_SEMANTIC_PROSE)},
        }
    )


@dataclass(frozen=True)
class RepeatedRecord:
    """One record the model emitted more than once for a single span."""

    #: The source span every copy was cut from. Never None.
    span: str
    #: Caller's key for the copy that should remain. Chosen by sorting the
    #: caller's own keys, which is arbitrary on purpose: the copies are identical
    #: in everything this pass compares, so there is nothing to prefer between
    #: them, and an arbitrary-but-stable choice is what makes the pass repeatable.
    keep: str
    #: Caller's keys for the copies that are redundant. Never empty.
    redundant: tuple[str, ...]

    @property
    def copies(self) -> int:
        return len(self.redundant) + 1


def repeated_records(records: list[tuple[str, dict]]) -> list[RepeatedRecord]:
    """Find records emitted more than once for one source span.

    `records` are `(key, payload)` pairs; keys are opaque and echoed back, so
    this module needs to know nothing about how records are stored. Identity is
    computed from the payload and never read from a stored fingerprint column,
    because those columns are written by a later pass and are empty for every
    run that did not reach it.

    Returned in a stable order so two callers comparing results compare like
    with like.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for key, payload in records:
        span = source_span(payload)
        if span is None:
            continue
        if _canonical_rule(payload) is None:
            continue
        groups.setdefault((span, record_key(payload)), []).append(key)

    found = []
    for (span, _), keys in groups.items():
        if len(keys) < 2:
            continue
        ordered = sorted(keys)
        found.append(
            RepeatedRecord(span=span, keep=ordered[0], redundant=tuple(ordered[1:]))
        )
    return sorted(found, key=lambda record: (record.span, record.keep))
