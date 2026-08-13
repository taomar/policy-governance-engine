"""A negation in the source must survive into the record a reviewer reads.

A record that states the opposite of its source is worse than a missing one.
An incomplete record under-serves a reviewer; an inverted one misleads them,
and it survives review precisely because it reads as a clean, confident,
well-formed rule.

The failure this guards against is not a mistranslation. It is a *decomposition*
that writes one verb phrase into two fields and lets the halves disagree: the
modality keeps "not", the predicate keeps the bare verb, and the predicate is
then rendered to a reviewer as a quotation of a sentence that says the reverse.

    modality="does not permit"  predicate="permit"   -> "permit the use of ..."

The effect *type* is derived elsewhere (from the rule type, backstopped by
`states_a_negation`) and reads the modality, so it survives this intact. That
is exactly what makes the shape dangerous: the record decides correctly while
quoting falsely, so nothing downstream of the decision notices.

The shapes below are synthetic and structural. They express *where a sentence
can put a negation* — modal, auxiliary, copular, adverbial, and determiner —
not sentences from any document, domain, layout or language. A guard written
against real sentences bounds the sentences it was shown; this one bounds the
grammatical positions a negation can occupy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    _effect_action,
    _merged_verb_phrase,
    _title_for,
)

#: Any word that reverses the force of a clause, wherever the sentence puts it.
_NEGATION_RE = re.compile(r"\b(?:not|never|no|cannot|nor|forbidden|prohibited)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Shape:
    """One grammatical position a negation can occupy, split across two fields."""

    name: str
    modality: str
    predicate: str
    object_: str
    subject: str = "the holder"
    #: The word the source used to reverse the clause. Must reach the reviewer.
    negation: str = "not"
    #: True when the decomposition duplicated one phrase across both fields,
    #: which is the shape that can drop a negation. Tracked so the suite can
    #: prove it still exercises the repair rather than passing on easy cases.
    double_split: bool = True


#: Grammatical positions, not sentences. Each writes one verb phrase into both
#: `modality` and `predicate`, which is the shape that loses a negation.
_SHAPES: tuple[_Shape, ...] = (
    _Shape("modal", "must not disclose", "disclose", "the register"),
    _Shape("modal-future", "shall not delegate", "delegate", "the authority"),
    _Shape("auxiliary-do", "does not permit", "permit", "the substitution"),
    _Shape("copular", "are not permitted", "permitted", ""),
    _Shape("copular-adverbial", "are strictly not accepted", "accepted", ""),
    _Shape("adverbial-never", "is never approved", "approved", "", negation="never"),
    _Shape("modal-contracted", "cannot reassign", "reassign", "the case", negation="cannot"),
    _Shape("determiner-no", "is to be no", "is to be", "exemption granted", negation="no"),
    # Both halves kept the negation. Nothing is lost, but the phrase is printed
    # twice; the repair must collapse it without disturbing the words.
    _Shape("duplicated-whole", "are not accepted", "are not accepted", ""),
)

#: Decompositions that must be left exactly as they are. Each carries a word
#: that *looks* like a negation to a careless rule but does not reverse the
#: clause, or carries its negation somewhere the repair would damage.
_LEAVE_ALONE: tuple[_Shape, ...] = (
    # Disjoint fields: the ordinary, correct decomposition. "are not allowed to"
    # + "enter" describes the phrase once, across two fields.
    _Shape("disjoint", "are not allowed to", "enter", "the server room", double_split=False),
    # A comparative "no" sets a floor and obliges; it does not forbid.
    _Shape("comparative-no", "no later than", "submit", "thirty days", double_split=False),
    # A `without` qualifier is a condition on the act, not a negation of it.
    _Shape("without-qualifier", "may proceed", "proceed without approval", "", double_split=False),
    # The negation fell on the boundary and the object already carries it.
    # Merging would print it twice; the predicate was never false.
    _Shape("carried-by-object", "is to be no", "is to be", "no other access", double_split=False),
)


def _policy(shape: _Shape) -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text=f"{shape.subject} {shape.modality} {shape.object_}".strip(),
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.PROHIBITION,
            subject=shape.subject,
            modality=shape.modality,
            predicate=shape.predicate,
            object=shape.object_ or None,
        ),
    )


def _repeats_a_phrase(text: str) -> str | None:
    """The first run of words this text says twice in a row, if any."""

    words = text.casefold().split()
    for size in range(len(words) // 2, 0, -1):
        for start in range(len(words) - 2 * size + 1):
            if words[start : start + size] == words[start + size : start + 2 * size]:
                return " ".join(words[start : start + size])
    return None


@pytest.mark.parametrize("shape", _SHAPES, ids=lambda s: s.name)
def test_negation_reaches_the_reviewer(shape: _Shape) -> None:
    """Whatever reversed the clause must appear in what a reviewer reads.

    Both surfaces are checked. The title is what a reviewer scans in a list;
    the action is what the engine puts verbatim into `denied_actions`, so an
    inverted one reaches a decision point as well as a person.
    """

    policy = _policy(shape)
    title = _title_for(policy)
    action = _effect_action(policy)

    assert _NEGATION_RE.search(title), (
        f"{shape.name}: the source reversed this clause with {shape.negation!r} "
        f"(modality={shape.modality!r}), but the title reads {title!r} — "
        "which states the opposite of the sentence it quotes"
    )
    assert _NEGATION_RE.search(action), (
        f"{shape.name}: the source reversed this clause with {shape.negation!r} "
        f"(modality={shape.modality!r}), but the effect action reads {action!r} — "
        "the engine puts this text verbatim into denied_actions"
    )


@pytest.mark.parametrize("shape", _SHAPES, ids=lambda s: s.name)
def test_the_phrase_is_said_once(shape: _Shape) -> None:
    """Collapsing a double-split must not leave the phrase printed twice."""

    for surface, text in (("title", _title_for(_policy(shape))), ("action", _effect_action(_policy(shape)))):
        repeated = _repeats_a_phrase(text)
        assert repeated is None, (
            f"{shape.name}: the {surface} says {repeated!r} twice in a row "
            f"({text!r}); one verb phrase was written into two fields and "
            "both were printed"
        )


@pytest.mark.parametrize("shape", _LEAVE_ALONE, ids=lambda s: s.name)
def test_sound_decompositions_are_untouched(shape: _Shape) -> None:
    """A correct decomposition must survive the repair unchanged.

    Widening the repair is the obvious way to break this file: a rule that
    merges whenever two fields share a word would fuse ordinary decompositions
    and start inventing text. These are the cases that must stay put.
    """

    rule = _policy(shape).rule
    assert _merged_verb_phrase(rule) is None, (
        f"{shape.name}: modality={shape.modality!r} predicate={shape.predicate!r} "
        f"object={shape.object_!r} is a sound decomposition, but the repair "
        "merged it — which rewrites words the source did not write in that order"
    )


def test_the_guard_still_exercises_the_repair() -> None:
    """The fixtures must still reach the code path this file exists to test.

    Every assertion above is satisfied by a decomposition that never triggers
    the repair at all — a disjoint `modality`/`predicate` pair keeps its
    negation for free. So the suite can go green while testing nothing, simply
    by drifting towards easy fixtures. This asserts the detector still sees:
    that a real number of shapes still take the merge path, and that the
    surfaces being asserted on are not empty strings.
    """

    exercised = [s for s in _SHAPES if _merged_verb_phrase(_policy(s).rule) is not None]
    assert len(exercised) >= 8, (
        f"only {len(exercised)} of {len(_SHAPES)} shapes still reach the repair; "
        "the fixtures have drifted to cases that would pass without it"
    )

    positions = {s.negation.casefold() for s in _SHAPES}
    assert len(positions) >= 4, (
        f"the shapes only cover {sorted(positions)}; a negation can also be "
        "written as a modal, an auxiliary, an adverb or a determiner, and a "
        "guard that has seen one position bounds one position"
    )

    for shape in _SHAPES:
        policy = _policy(shape)
        assert _title_for(policy).strip(), f"{shape.name}: title is empty, so its assertion is vacuous"
        assert _effect_action(policy).strip(), f"{shape.name}: action is empty, so its assertion is vacuous"

    assert len(_LEAVE_ALONE) >= 4, "the untouched-decomposition controls have been thinned out"
