"""A conjunction the decomposition supplies is glue, not invented wording.

THE FALSE POSITIVE THIS EXISTS TO PREVENT

Evaluating the AIS handbook reported, at BLOCKING severity:

    Rule 'Any employee may be released' (AI-a44dd6f6f8): 'found guilty and not
    disclosed prior to the hiring/interview process' — the extraction target
    derived from canonical 'condition' reuses this sentence's words in an order
    the sentence does not, so an evaluator would be told to look for wording
    the policy never used.

The sentence is:

    Any employee found guilty may be released if not disclosed prior to the
    hiring/interview process.

It states two conditions in two different grammatical shapes — a participle
("found guilty") and an if-clause ("if not disclosed prior to..."). A
decomposition that captures both has to join them, and English joins them with
"and", a word this sentence never writes because it did not need to.

`_subsequence_gap_words` returned None the moment it could not find "and" in
the source, so the claim fell through to UNSUPPORTED and was ranked blocking.
Every content word of the claim is in the sentence, in order.

THE GENERAL FAULT

This is the sixth instance of one fault: a lexical test standing in for a
semantic property, and biased against correct prose. Requiring a head noun to
repeat penalised anaphora. Requiring a subject to be quoted penalised the
imperative. Requiring a contiguous subsequence penalises conjunctive
decomposition — which is not optional, because a sentence stating two
conditions in two shapes cannot be decomposed into one field without a joining
word.

WHAT IS PINNED

The exclusions matter more than the inclusions. `_JOINING_WORDS` holds "and"
and "or" only. "nor" and "neither" are coordinators too and are deliberately
absent, because they reverse and `_REVERSING_RE` must keep seeing them — a
claim that steps over a negation is not a shorter way of saying the sentence,
it is the opposite of it. "but" and "yet" are contrastive and change what the
conjunction asserts; "for" and "so" are causal.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.quality.logic_faithfulness import (
    MismatchShape,
    _JOINING_WORDS,
    classify_mismatch,
)

NEPOTISM = (
    "Any employee found guilty may be released if not disclosed prior to the "
    "hiring/interview process."
)


def test_the_live_case_is_a_correct_decomposition() -> None:
    """Two conditions, two grammatical shapes, one field, one joining word."""

    claim = "found guilty and not disclosed prior to the hiring/interview process"
    assert classify_mismatch(claim, NEPOTISM) is MismatchShape.DECOMPOSED


def test_a_joining_word_the_sentence_does_write_is_matched_normally() -> None:
    """The pass-over applies only where the source has no "and" to offer.

    Where the sentence writes its own, that one is matched in place and
    anything it steps over is still counted, so the gap analysis is unchanged
    for the ordinary case.
    """

    assert (
        classify_mismatch("alcohol and drugs", "Alcohol and drugs are strictly forbidden.")
        is MismatchShape.DECOMPOSED
    )


# --------------------------------------------------------------------------
# What must not change
# --------------------------------------------------------------------------


def test_a_claim_that_steps_over_a_negation_is_still_inverted() -> None:
    """The guarantee this must not weaken.

    A subsequence that skips "not" states the opposite of its source, and that
    is blocking. Passing over a joining word must not make a reversing word
    passable — which is why "nor" and "neither" are excluded from the set.
    """

    inverted = classify_mismatch(
        "anyone employed by AIS",
        "Employees may not disclose X to anyone who is not employed by AIS",
    )
    assert inverted is MismatchShape.INVERTED


def test_an_invented_phrase_is_still_supplied() -> None:
    """Glue is not a licence. A claim sharing no content word is still reported."""

    assert (
        classify_mismatch("the Board of Trustees and the Dean", "Employees shall submit forms.")
        is MismatchShape.SUPPLIED
    )


def test_a_flattened_table_row_is_still_concatenated() -> None:
    """Separators are read before words and are unaffected."""

    assert classify_mismatch("1 Time; 2 Time", "a | b") is MismatchShape.CONCATENATED


@pytest.mark.parametrize("word", ["nor", "neither", "but", "yet", "for", "so", "not"])
def test_the_joining_set_holds_only_combining_conjunctions(word: str) -> None:
    """A structural guard on the set, not on today's contents.

    The set is safe because of what it may not contain. A reversing coordinator
    would let a negation be stepped over silently; a contrastive or causal one
    would let the claim assert a relation the sentence does not.
    """

    assert word not in _JOINING_WORDS


def test_the_joining_set_is_not_empty() -> None:
    """A set emptied by a future edit would silently restore the false positive."""

    assert _JOINING_WORDS
