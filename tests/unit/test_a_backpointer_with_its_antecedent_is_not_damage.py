"""A back-pointer is only damage when the cut actually lost its antecedent.

THE FALSE POSITIVE THIS EXISTS TO PREVENT

On the AIS handbook the evaluation reported, at high severity and as
"confirmed by deterministic check":

    Rule 'action will be taken according to the administration procedures'
    (AI-914d968fe3): "the extraction cut this record away from wording it
    depends on: 'condition' says 'that day', which the record's own evidence
    does not name again in those words" — the canonical decomposition is
    damaged ... and needs re-extracting.

The source it quotes is two sentences:

    "If there are workshops, meetings, or other events on Saturdays, you may be
    asked to attend. In the case of absences on that day, there will be action
    taken according to the administration procedures."

"That day" is the Saturday named in the sentence before it, and that sentence is
inside the record's own evidence. Nothing was cut away and nothing needs
re-extracting. The document is written the way policy documents are written.

WHY THE CHECK FIRED

`_resolves_locally` asks whether the pointer's *head noun* occurs again in the
record — "day" against "Saturdays". It does not, so the check concluded the
antecedent was missing. That is a lexical test standing in for a semantic one,
and it is biased against correct prose: anaphora exists so a writer need not
repeat the noun, so a document saying "on that Saturday" would read worse and
pass, while the natural wording fails.

`UnresolvedReferent` already separated the two situations — its
`source_carries_a_neighbour` flag asks whether the evidence holds a sentence
before the pointer — but only the *message* changed. Both branches returned
`Evaluability.MALFORMED`, which `check_malformed_is_reported` raises as a
BLOCKING finding. The distinction was computed and then discarded.

WHAT IS PINNED HERE

Both directions, because the fix must not be a blanket suppression:

  * evidence that kept the neighbouring sentence is not malformed — a reader
    can resolve the pointer, so the record is not damaged;
  * evidence that is a single sentence still is — "that day" with no earlier
    sentence anywhere in the record has nothing to resolve against, which is
    the case the check was built for and must keep catching.
"""

from __future__ import annotations

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    assess,
    dangling_referents,
)

#: The passage from the live finding, verbatim.
SATURDAY_PASSAGE = (
    "If there are workshops, meetings, or other events on Saturdays, you may be "
    "asked to attend. In the case of absences on that day, there will be action "
    "taken according to the administration procedures."
)

#: The same operative sentence with nothing before it — the cut that did lose
#: the antecedent.
LONE_SENTENCE = (
    "In the case of absences on that day, there will be action taken according "
    "to the administration procedures."
)


def _absence_rule() -> CanonicalPolicyRule:
    """AI-914d968fe3, the record the finding named."""

    return CanonicalPolicyRule(
        rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
        subject="action",
        modality="will",
        predicate="be taken according to the administration procedures",
        condition="In the case of absences on that day",
        source_origin="inherited_context",
    )


def test_a_pointer_whose_evidence_kept_its_neighbour_is_not_malformed() -> None:
    verdict = assess(_absence_rule(), SATURDAY_PASSAGE)

    assert verdict.evaluability is not Evaluability.MALFORMED, (
        "'that day' resolves to the Saturday named one sentence earlier, inside "
        f"this record's own evidence; got {verdict.evaluability} — {verdict.reason}"
    )


def test_the_same_pointer_without_its_neighbour_is_still_malformed() -> None:
    # The check must keep catching the case it was built for. If this passes
    # only because the finding was suppressed everywhere, the fix is a blanket
    # and not a distinction.
    verdict = assess(_absence_rule(), LONE_SENTENCE)

    assert verdict.evaluability is Evaluability.MALFORMED
    assert "that day" in verdict.reason


def test_the_pointer_is_still_reported_either_way() -> None:
    """Not malformed is not the same as not noticed.

    The record still points outside its own wording, and a reviewer may still
    want to read it beside its passage. What changed is the claim made about
    it — a damaged extraction needing re-extraction — not whether it is seen.
    """
    kept = dangling_referents(_absence_rule(), SATURDAY_PASSAGE)

    assert kept, "the pointer should still be detected"
    assert all(item.source_carries_a_neighbour for item in kept)
    assert any("that day" in item.phrase for item in kept)


def test_the_two_situations_are_told_apart_by_the_evidence() -> None:
    """The discriminator is the cut, not the wording of the pointer."""
    with_neighbour = dangling_referents(_absence_rule(), SATURDAY_PASSAGE)
    without = dangling_referents(_absence_rule(), LONE_SENTENCE)

    assert [i.phrase for i in with_neighbour] == [i.phrase for i in without], (
        "the same pointer is found in both; only its resolvability differs"
    )
    assert all(i.source_carries_a_neighbour for i in with_neighbour)
    assert not any(i.source_carries_a_neighbour for i in without)
