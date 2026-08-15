"""A field the source never wrote as a run is a copy of its neighbour, not a constituent.

The decomposition writes one sentence across `subject`, `modality`, `predicate`
and `object`. Each field is a *span* of the sentence. When the boundary between
two of them is drawn in the wrong place, a field stops being a span and becomes
a reconstruction — the same words as its neighbour with something left out.

Left out from the middle, that missing something can be the very word that
carried the sentence's polarity, and the record then states the inverse of the
document:

    source     "Slippers are strictly not allowed."
    modality   "strictly not allowed"
    predicate  "are allowed"          <- not a span of the sentence
    title      "Slippers strictly not allowed are allowed"
    action     "are allowed"

`_merged_verb_phrase` already existed to catch one form of this, where the copy
is strictly *smaller* than its neighbour and containment finds it. That test
cannot see the form above, because the copy keeps a word — the copula, which the
sentence put before the modality — that the neighbour never held. "are allowed"
is not inside "strictly not allowed", so containment reports two fields and lets
the inversion through.

WHAT IS TESTED, AND WHAT DELIBERATELY IS NOT. Nothing here asks which words are
negative. A list of negative phrases would be a vocabulary, it would be English,
and this corpus is substantially Arabic; it would also be the wrong object,
because the defect is not that a negation was mishandled but that a constituent
boundary was drawn late. The polarity is merely the most damaging thing that can
fall through the crack. So the property is stated over meaningless tokens: a
field whose words can be read off a neighbouring span only by *skipping* is a
copy of that span, whatever those words mean, in whatever language.

The corresponding real sentences appear only in `_WITNESSES`, and only as
regression witnesses. They are not targets: every one of them is an instance of
the generated shape above, and the shape is what the code is written against.
Removing them would not weaken the property; they are here so that a future
reader can see the thing the property is about.

CONTROLS COME FIRST HERE. The verdict of the main property is "this composition
changed", and a change is destructive: it replaces two fields with one span. A
guard containing only offenders cannot tell you when it has begun over-reaching,
and over-reach in this direction is worse than the defect — a genuine permission
that loses words reads as a narrower grant than the document made. So the
controls (`test_two_real_constituents_are_left_alone`,
`test_a_phrase_the_object_completes_is_left_alone`,
`test_a_window_wider_than_both_fields_is_not_one_phrase`) carry equal weight
with the offenders, and neither half is meaningful alone.

FLOOR PLACEMENT. The verdict is "every generated shape merges", so a generator
that produced nothing would pass vacuously with no offenders to show. The volume
floor is therefore asserted separately in
`test_the_generated_shapes_are_not_empty`, and the enumeration is derived from a
token alphabet rather than written out, so the floor cannot be satisfied by a
table someone shortened.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from policy_platform.contracts.formulation import (  # noqa: E402
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EffectType  # noqa: E402
from policy_platform.infrastructure.extraction.formulation_mapping import (  # noqa: E402
    _effect_action_for,
    _merged_verb_phrase,
    _title_for,
)

#: Tokens with no meaning of their own. Real words would invite a fix that reads
#: English, and the defect is structural rather than lexical: it is one field
#: holding a lossy copy of the span next to it.
_TOKENS = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta")

#: Well under the size of the enumeration below, so ordinary edits to the token
#: alphabet do not trip it, but far enough above zero that a generator which
#: stopped producing shapes could not pass vacuously.
_MINIMUM_SHAPES = 20


def _rule(subject: str, modality: str, predicate: str, obj: str = "") -> CanonicalPolicyRule:
    return CanonicalPolicyRule(
        rule_type=CanonicalRuleType.PROHIBITION,
        subject=subject or None,
        modality=modality or None,
        predicate=predicate or None,
        object=obj or None,
    )


def _policy(source: str, rule: CanonicalPolicyRule) -> CanonicalPolicy:
    return CanonicalPolicy(source_text=source, rule=rule)


def _lossy_copy_shapes() -> list[tuple[str, str, str, str]]:
    """Sentences where one field is a neighbouring span read with words skipped.

    Yields `(source, modality, predicate, expected_span)`. The modality is a
    contiguous run of the source; the predicate is that run extended leftwards
    by one or two words and then read with the middle dropped, which is exactly
    the shape a copula-plus-head reconstruction takes. The expected span is the
    run the source actually wrote.
    """

    shapes: list[tuple[str, str, str, str]] = []
    for length in (4, 5, 6, 7):
        words = list(_TOKENS[:length])
        for start in range(1, length - 1):
            for size in (2, 3):
                if start + size > length:
                    continue
                for reach in (1, 2):
                    low = start - reach
                    if low < 0:
                        continue
                    window = words[low : start + size]
                    if len(window) < 3:
                        continue
                    predicate = [window[0], window[-1]]
                    shapes.append(
                        (
                            " ".join(words),
                            " ".join(words[start : start + size]),
                            " ".join(predicate),
                            " ".join(window),
                        )
                    )
    return shapes


#: Real sentences that carried the defect into live data. Witnesses, not targets:
#: each is an instance of the generated shape, and the code is written against
#: the shape. Recorded as (source, modality, predicate) exactly as the stored
#: decomposition held them.
_WITNESSES = (
    (
        "Slippers are strictly not allowed.",
        "Slippers",
        "strictly not allowed",
        "are allowed",
        "Slippers are strictly not allowed",
    ),
    (
        "Alcohol and drugs are strictly forbidden.",
        "Alcohol and drugs",
        "strictly forbidden",
        "are forbidden",
        "Alcohol and drugs are strictly forbidden",
    ),
    (
        "Smoking is not allowed on the school's premises.",
        "Smoking",
        "is not allowed",
        "is allowed",
        "Smoking is not allowed",
    ),
)


def test_the_generated_shapes_are_not_empty() -> None:
    """A generator that produced nothing would make every property below vacuous."""

    assert len(_lossy_copy_shapes()) >= _MINIMUM_SHAPES


@pytest.mark.parametrize("source,modality,predicate,expected", _lossy_copy_shapes())
def test_a_skipped_reading_of_a_span_merges_back_into_that_span(
    source: str, modality: str, predicate: str, expected: str
) -> None:
    """The two fields are replaced by the one run the sentence actually wrote."""

    assert _merged_verb_phrase(_rule("", modality, predicate), source) == expected


@pytest.mark.parametrize("source,modality,predicate,expected", _lossy_copy_shapes())
def test_the_merged_phrase_is_always_the_source_s_own_characters(
    source: str, modality: str, predicate: str, expected: str
) -> None:
    """Nothing is composed. Whatever replaces the two fields is a substring of the source.

    This is the property that makes the repair safe to put in front of a
    reviewer beside verbatim evidence: the merge can only ever return words the
    document contains, in the order the document wrote them.
    """

    merged = _merged_verb_phrase(_rule("", modality, predicate), source)
    assert merged is not None
    assert merged in source


@pytest.mark.parametrize("source,modality,predicate,expected", _lossy_copy_shapes())
def test_containment_alone_could_not_have_seen_these(
    source: str, modality: str, predicate: str, expected: str
) -> None:
    """The predicate is not inside the modality, which is why the older test missed it.

    Asserted rather than described, so that a change which quietly narrowed the
    generator back to shapes the old rule already handled would fail here rather
    than pass everywhere.
    """

    haystack = modality.casefold().split()
    needle = predicate.casefold().split()
    contained = any(
        haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1)
    )
    assert not contained


def test_two_real_constituents_are_left_alone() -> None:
    """A predicate the source wrote as a run of its own is a second constituent."""

    source = "alpha beta gamma delta epsilon"
    assert _merged_verb_phrase(_rule("alpha", "beta", "gamma delta"), source) is None


def test_a_phrase_the_object_completes_is_left_alone() -> None:
    """Merging must not introduce the duplication it exists to remove.

    Where the object opens with the words the merged span would end on, the
    predicate is a truthful span and the object carries the rest, so joining
    them would print the shared words twice.
    """

    source = "alpha beta gamma delta epsilon"
    rule = _rule("alpha", "beta gamma delta", "beta gamma", obj="delta epsilon")
    assert _merged_verb_phrase(rule, source) is None


def test_a_window_wider_than_both_fields_is_not_one_phrase() -> None:
    """Two fields drawn from distant parts of the sentence are two constituents.

    One phrase written twice cannot need more room than its two writings. Where
    the only window spanning both is wider than that, the fields describe
    different parts of the sentence and merging them would compose a run the
    reader would take for a single clause.
    """

    source = "alpha beta gamma delta epsilon zeta eta"
    rule = _rule("", "delta epsilon", "alpha eta")
    assert _merged_verb_phrase(rule, source) is None


def test_a_field_that_is_not_in_the_source_at_all_is_left_alone() -> None:
    """A predicate the sentence never wrote cannot be a copy of a span of it."""

    source = "alpha beta gamma delta"
    assert _merged_verb_phrase(_rule("", "beta gamma", ""), source) is None
    assert _merged_verb_phrase(_rule("", "beta gamma", "beta delta"), "") is None
    assert _merged_verb_phrase(_rule("", "beta gamma", "zeta eta"), source) is None


def test_the_repair_needs_no_word_list_to_work_in_another_script() -> None:
    """The same shape in Arabic merges identically, because nothing here reads words.

    Direction and script are properties of the run, never of the rule. The test
    is word order against the source, so a sentence in any script behaves the
    same. Included because the corpus is substantially Arabic and a repair that
    silently worked only on Latin text would be the more dangerous failure: it
    would look fixed.
    """

    source = "\u0627\u0644\u0623\u062d\u0630\u064a\u0629 \u063a\u064a\u0631 \u0645\u0633\u0645\u0648\u062d \u0628\u0647\u0627"
    words = source.split()
    modality = " ".join(words[1:])
    predicate = " ".join((words[0], words[-1]))
    assert _merged_verb_phrase(_rule("", modality, predicate), source) == source


@pytest.mark.parametrize("source,subject,modality,predicate,expected", _WITNESSES)
def test_a_witness_title_reads_as_the_document_wrote_it(
    source: str, subject: str, modality: str, predicate: str, expected: str
) -> None:
    """Every witness composes back to a run of its own sentence.

    Asserted by exact text, because a witness is evidence rather than a
    property: the point of recording it is that this precise string is what a
    reviewer saw, and the previous string was its inverse.
    """

    policy = _policy(source, _rule(subject, modality, predicate))
    assert _title_for(policy) == expected
    assert expected in source


@pytest.mark.parametrize("source,subject,modality,predicate,expected", _WITNESSES)
def test_a_witness_action_no_longer_states_the_inverse(
    source: str, subject: str, modality: str, predicate: str, expected: str
) -> None:
    """The evaluator-facing action text is a run of the sentence, not a reading of it.

    `_effect_action` goes verbatim into `denied_actions`, so a decision point was
    being handed the fragment that survived the skip. Asserting substring-of-
    source rather than an expected string keeps this about provenance: the action
    may only ever be words the document wrote.
    """

    policy = _policy(source, _rule(subject, modality, predicate))
    action = _effect_action_for(policy, EffectType.DENY)
    assert action
    assert action in source
    assert action != predicate


def test_a_permission_whose_fields_overlap_keeps_all_of_its_words() -> None:
    """Over-correction would read a grant as narrower than the document made it.

    The risk of this repair is not that it fails to fire but that it fires on a
    permission and swallows the thing granted. Here the modality and predicate
    genuinely overlap and the object carries the grant, and every word survives.
    """

    source = "an employee will be entitled to 2.5 days of vacation per month"
    rule = CanonicalPolicyRule(
        rule_type=CanonicalRuleType.PERMISSION,
        subject="an employee",
        modality="will be entitled to",
        predicate="be entitled to",
        object="2.5 days of vacation per month",
    )
    policy = _policy(source, rule)
    assert _title_for(policy) == source
    assert _effect_action_for(policy, EffectType.ALLOW) == "will be entitled to 2.5 days of vacation per month"
