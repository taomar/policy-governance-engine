"""A composed title must never say the same words twice running.

The decomposition writes one sentence across `subject`, `modality`, `predicate`
and `object`, and those fields are *spans* of the sentence rather than a
partition of it. Neighbouring spans therefore overlap routinely, and a title
built by joining them end to end says the shared words once per field:

    subject="Smoking"   modality="is not allowed"   predicate="is not allowed"
        -> "Smoking is not allowed is not allowed"

This module does not test those strings. A test written against the sentences
someone happened to notice would pass the moment the corpus changed, while the
composition stayed broken for every sentence nobody read. What is tested is the
*shape*: overlapping spans, enumerated over a generated vocabulary, with the
verdict being "does any composed title repeat a run of words immediately".

FLOOR PLACEMENT. The verdict here is an offender list, so the volume floor goes
LAST. A generator that produced nothing would yield an empty offender list and
pass vacuously, which makes the floor the only thing left to catch it — but a
floor asserted first would shadow a real offender, and the fails-before proof
would then record a count failure as if it were the defect. (The opposite rule
applies when a verdict is a set difference against what a scan found: there a
blind scan accuses every item rather than none, so the floor must come first.)

The detector is itself checked, in both directions, by
`test_the_detector_still_sees_a_repeat_and_does_not_imagine_one`.
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
from policy_platform.infrastructure.extraction.formulation_mapping import (  # noqa: E402
    _title_for,
)

# Enough distinct compositions that a generator which quietly stopped producing
# them could not slip past. Chosen from the size of the enumeration below, well
# under it, so ordinary edits to the vocabulary do not trip it.
_MINIMUM_COMPOSITIONS = 200

# Tokens with no meaning of their own. Real words would invite a fix that reads
# English — a stop-word list, a modality vocabulary — and the defect is
# structural, not lexical: it is two adjacent fields quoting the same span.
_TOKENS = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta")


def _repeated_run(text: str) -> str | None:
    """The longest run of words the text says twice in immediate succession.

    Whole words, case-folded. Returns `None` when nothing is repeated back to
    back, which is the property under test.
    """

    words = text.split()
    folded = [word.casefold() for word in words]
    longest: str | None = None
    longest_len = 0
    for size in range(1, len(words) // 2 + 1):
        for start in range(0, len(words) - 2 * size + 1):
            if folded[start : start + size] == folded[start + size : start + 2 * size]:
                if size > longest_len:
                    longest_len = size
                    longest = " ".join(words[start : start + size])
    return longest


def _title(subject: str, modality: str, predicate: str, obj: str) -> str:
    return _title_for(
        CanonicalPolicy(
            source_text="(source sentence)",
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject=subject or None,
                modality=modality or None,
                predicate=predicate or None,
                object=obj or None,
            ),
        )
    )


def _overlapping_decompositions() -> list[tuple[str, str, str, str]]:
    """Every way four spans of one sentence can overlap at their joins.

    Built by walking a window over a token sequence: the modality is a run, the
    predicate is any sub-run of it (one phrase written into two fields), the
    object may open with the modality's own tail (the join collision), and the
    subject may close with the modality's opening words (the sentence's head
    repeated into the subject). No case names a document, a language or a
    grammatical construction.
    """

    cases: list[tuple[str, str, str, str]] = []
    for modality_len in range(1, 5):
        modality = _TOKENS[:modality_len]
        tail_tokens = _TOKENS[modality_len : modality_len + 2]
        for predicate_start in range(0, modality_len):
            for predicate_len in range(1, modality_len - predicate_start + 1):
                predicate = modality[predicate_start : predicate_start + predicate_len]
                for object_overlap in range(0, modality_len + 1):
                    obj = tuple(modality[modality_len - object_overlap :]) + tuple(tail_tokens)
                    for subject_overlap in range(0, modality_len + 1):
                        subject = ("subj",) + tuple(modality[:subject_overlap])
                        cases.append(
                            (
                                " ".join(subject),
                                " ".join(modality),
                                " ".join(predicate),
                                " ".join(obj),
                            )
                        )
    return cases


def test_the_detector_still_sees_a_repeat_and_does_not_imagine_one() -> None:
    """The verdict is 'no offenders', so the detector must be known to work.

    Without this, a `_repeated_run` that always returned `None` would make every
    other test in this file pass while checking nothing at all.
    """

    assert _repeated_run("alpha beta alpha beta gamma") == "alpha beta"
    assert _repeated_run("alpha alpha") == "alpha"
    assert _repeated_run("Alpha alpha") == "Alpha", "must fold case"
    assert _repeated_run("alpha beta gamma delta") is None
    assert _repeated_run("alpha beta gamma alpha beta") is None, "only immediate repeats"
    assert _repeated_run("") is None


def test_a_composed_title_never_says_the_same_words_twice_running() -> None:
    """No overlap between two adjacent spans may reach a reader as a stutter."""

    offenders: list[str] = []
    examined = 0
    for subject, modality, predicate, obj in _overlapping_decompositions():
        examined += 1
        title = _title(subject, modality, predicate, obj)
        repeated = _repeated_run(title)
        if repeated is not None:
            offenders.append(
                f"subject={subject!r} modality={modality!r} predicate={predicate!r} "
                f"object={obj!r} composed {title!r}, repeating {repeated!r}"
            )

    assert not offenders, "titles that say the same words twice running:\n  " + "\n  ".join(
        offenders[:12]
    )
    # Floor last: see the module docstring. A generator that produced nothing
    # would have reached here with an empty offender list.
    assert examined >= _MINIMUM_COMPOSITIONS, (
        f"composed only {examined} titles, expected at least {_MINIMUM_COMPOSITIONS} — "
        "the generator has gone blind and the assertion above proved nothing"
    )


def test_the_title_only_ever_drops_words_it_has_already_said() -> None:
    """Removing a repeat must not remove anything else.

    The guard above is satisfied by a composer that returns the empty string, or
    that keeps only the subject. This one holds it to the other side of the
    bargain: every word in the title is a word some field supplied, in the order
    the fields supplied them, and each field still contributes something unless
    a neighbour has already said all of it.
    """

    offenders: list[str] = []
    examined = 0
    for subject, modality, predicate, obj in _overlapping_decompositions():
        examined += 1
        title = _title(subject, modality, predicate, obj)
        available = f"{subject} {modality} {predicate} {obj}".split()
        remaining = list(available)
        for word in title.split():
            if word in remaining:
                remaining.remove(word)
            else:
                offenders.append(f"{title!r} contains {word!r}, which no field supplied")
                break
        # The subject is never a repeat of anything before it, so it always survives.
        if not title.startswith(subject.split()[0]):
            offenders.append(f"{title!r} dropped the opening of subject {subject!r}")

    assert not offenders, "titles that invented or lost words:\n  " + "\n  ".join(offenders[:12])
    assert examined >= _MINIMUM_COMPOSITIONS, (
        f"composed only {examined} titles, expected at least {_MINIMUM_COMPOSITIONS}"
    )


@pytest.mark.parametrize(
    ("subject", "modality", "predicate", "obj"),
    [
        # One phrase written into both verb fields, with nothing after it.
        ("alpha", "beta gamma", "beta gamma", ""),
        # The predicate is the modality minus the word that carried the negation.
        ("alpha", "beta gamma delta", "delta", ""),
        # The object opens with the word the modality ended on.
        ("alpha", "beta gamma", "beta", "gamma delta epsilon"),
        # Both at once: predicate inside the modality, object colliding with it.
        ("alpha", "beta gamma delta", "beta gamma", "delta epsilon"),
    ],
)
def test_named_overlap_shapes_compose_cleanly(
    subject: str, modality: str, predicate: str, obj: str
) -> None:
    """The distinct ways two spans can overlap, each stated once.

    These are shapes, not sentences: every token is meaningless, so a fix that
    recognised particular English words would not satisfy them.
    """

    title = _title(subject, modality, predicate, obj)
    assert _repeated_run(title) is None, f"{title!r} repeats {_repeated_run(title)!r}"
