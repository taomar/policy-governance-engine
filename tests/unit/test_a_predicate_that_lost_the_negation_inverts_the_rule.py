"""A predicate that lost the negation is not the same defect as one that repeats.

WHAT WAS WRONG

`assess()` reported four records with one sentence:

    canonical 'predicate' repeats the modality 'X', so the sentence was
    mis-split and the verb is unreliable

Measured on the AIS handbook, those four are two different things:

    "Smoking is not allowed on the school's premises."
        modality  'is not allowed'
        predicate 'allowed'

    "Alcohol and drugs are strictly forbidden."
        modality  'are strictly forbidden'
        predicate 'forbidden'

Both wrote one verb phrase into two fields, and both are malformed. Only the
first *inverts*: read on its own, its predicate says the document permits what
the document forbids. The second is redundant and says nothing false.

"The verb is unreliable" understates the first and overstates the second, and a
reviewer triaging a report cannot tell which two of four records store the
opposite of their source. This project's own negation suite opens by naming
that as the worst output the system can produce: "a confident statement of the
opposite of what the document said".

WHY THIS IS NOT A VOCABULARY

The discriminator is not a list of dangerous words. It is the set difference
between the two fields: the predicate is the modality with some words removed,
and the question is only whether a negation particle is among the words
removed. `_NEGATION_PARTICLES` is the closed English function-word class — not
a sample of it — and is consulted only on words the predicate dropped, never on
the sentence. It cannot grow into a content classifier because there is nothing
for it to classify.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    _NEGATION_PARTICLES,
    _predicate_dropped_the_negation,
    _predicate_repeats_modality,
    _words_the_predicate_dropped,
    assess,
)


def _rule(modality: str | None, predicate: str, subject: str = "Smoking"):
    return CanonicalPolicyRule(
        rule_type=CanonicalRuleType.PROHIBITION,
        subject=subject,
        modality=modality,
        predicate=predicate,
    )


# --------------------------------------------------------------------------
# The two shapes, verbatim from the corpus
# --------------------------------------------------------------------------


#: (modality, predicate, source) — the predicate states the opposite.
_INVERTS = [
    ("is not allowed", "allowed", "Smoking is not allowed on the school's premises."),
    (
        "does not permit",
        "permit",
        "The company does not permit the use of alcohol or drugs within the school's premises.",
    ),
]

#: The predicate merely repeats. Malformed, but nothing false is stored.
_REPEATS = [
    ("are strictly forbidden", "forbidden", "Alcohol and drugs are strictly forbidden."),
    (
        "are strictly forbidden",
        "forbidden",
        "Any other connections to the AIS internet/network from any other devices "
        "are strictly forbidden.",
    ),
]


@pytest.mark.parametrize("modality,predicate,source", _INVERTS)
def test_a_predicate_that_lost_the_negation_says_so(modality, predicate, source):
    rule = _rule(modality, predicate)
    assert _predicate_repeats_modality(rule) is True
    assert _predicate_dropped_the_negation(rule) is True

    reason = assess(rule, source).reason
    assert "the opposite of what the source states" in reason, reason
    assert predicate in reason, "the reason must quote what the predicate now reads"
    assert modality in reason, "the reason must quote what it was cut from"


@pytest.mark.parametrize("modality,predicate,source", _REPEATS)
def test_a_predicate_that_only_repeats_is_not_called_an_inversion(
    modality, predicate, source
):
    """The other half, and the reason this is a split rather than a rewording.

    Reporting these as inversions would be the same error in the other
    direction: it would send a reviewer looking for a reversal that is not
    there, and would make the two that ARE reversed indistinguishable again.
    """

    rule = _rule(modality, predicate)
    assert _predicate_repeats_modality(rule) is True
    assert _predicate_dropped_the_negation(rule) is False

    reason = assess(rule, source).reason
    assert "the opposite of what the source states" not in reason
    assert "repeats the modality" in reason


@pytest.mark.parametrize("modality,predicate,source", _INVERTS + _REPEATS)
def test_both_shapes_are_still_malformed(modality, predicate, source):
    """The split changes what is said, never whether it is reported.

    Both are one verb phrase written into two fields; both need re-extracting.
    A split that quietly exonerated half of them would be worse than the
    undifferentiated message it replaced.
    """

    assert assess(_rule(modality, predicate), source).evaluability is Evaluability.MALFORMED


# --------------------------------------------------------------------------
# What the discriminator must not do
# --------------------------------------------------------------------------


def test_a_well_formed_record_is_untouched() -> None:
    """The predicate does not repeat the modality, so neither test applies."""

    rule = _rule("shall", "submit the form", subject="Employees")
    assert _predicate_repeats_modality(rule) is False
    assert _predicate_dropped_the_negation(rule) is False


def test_no_modality_is_not_an_inversion() -> None:
    """A record with no modal word has dropped nothing from it."""

    rule = _rule(None, "is in place to prevent")
    assert _predicate_dropped_the_negation(rule) is False
    assert _words_the_predicate_dropped(rule) == []


def test_a_negation_the_predicate_kept_is_not_dropped() -> None:
    """Only words the predicate LOST count.

    "shall not disclose" / "not disclose" repeats the modality and keeps the
    negation, so the predicate reads correctly on its own. Calling that an
    inversion would report a faithful record.
    """

    rule = _rule("shall not disclose", "disclose confidential information")
    dropped = _words_the_predicate_dropped(rule)
    assert "not" in dropped, "this fixture is only meaningful if 'not' was lost"

    kept = _rule("shall not", "not disclose")
    assert _predicate_dropped_the_negation(kept) is False, (
        "the predicate kept the negation, so nothing was inverted"
    )


def test_the_particle_set_is_closed_and_holds_only_negations() -> None:
    """A structural guard on the set, not on today's contents.

    The set is safe because of what it may contain. An ordinary verb or a modal
    would make it a classifier of content rather than of grammar, and would
    start calling faithful decompositions inversions.
    """

    forbidden = {
        "shall", "must", "may", "will", "should", "can", "is", "are", "does",
        "do", "allowed", "forbidden", "permit", "strictly",
    }
    assert not (_NEGATION_PARTICLES & forbidden)
    for particle in _NEGATION_PARTICLES:
        assert particle == particle.casefold()
        assert " " not in particle, "particles are single words; phrases would not match tokens"
