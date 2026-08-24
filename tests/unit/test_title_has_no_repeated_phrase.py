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

CONTROLS. A guard that contains only offenders cannot tell you when it has
started over-reaching, and this one did. Removing a repeat is a destructive
edit, and some repeats are the document's own words: a definition writes the
defined term and then opens the definition with it —

    source="Temporary Work: Work considered by its nature to end ..."
    subject="Temporary Work"   predicate=":"   object="Work considered ..."
        -> "Temporary Work Work considered by its nature to end ..."

— where "Work Work" is what the document says. Eliding it fuses a term into its
own definition and puts a title in front of a reviewer that the source does not
contain, which is a worse defect than the stutter it was cleaning up. So this
file carries controls as well as offenders: titles that legitimately repeat and
must survive, asserted by exact text. `test_named_offender_shapes_compose_cleanly`
and `test_source_attested_repetition_survives` are two halves of one property
and neither is meaningful alone.

The distinction is not available from the composed string. "Smoking is not
allowed is not allowed" and "Temporary Work Work considered ..." are the same
shape; only the source tells them apart. Any check here that reasons about the
title alone is therefore testing the wrong object.

FLOOR PLACEMENT. The verdict here is an offender list, so the volume floor goes
LAST. A generator that produced nothing would yield an empty offender list and
pass vacuously, which makes the floor the only thing left to catch it — but a
floor asserted first would shadow a real offender, and the fails-before proof
would then record a count failure as if it were the defect. (The opposite rule
applies when a verdict is a set difference against what a scan found: there a
blind scan accuses every item rather than none, so the floor must come first.)

The control table is parametrised, and an empty parametrise list is collected
without complaint, so it has a floor of its own in
`test_the_control_table_is_not_empty`.

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


def _title(subject: str, modality: str, predicate: str, obj: str, source: str) -> str:
    return _title_for(
        CanonicalPolicy(
            source_text=source,
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject=subject or None,
                modality=modality or None,
                predicate=predicate or None,
                object=obj or None,
            ),
        )
    )


def _overlapping_decompositions() -> list[tuple[str, str, str, str, str]]:
    """Every way four spans of one sentence can overlap at their joins.

    Built by walking a window over a token sequence: the modality is a run, the
    predicate is any sub-run of it (one phrase written into two fields), the
    object may open with the modality's own tail (the join collision), and the
    subject may close with the modality's opening words (the sentence's head
    repeated into the subject). No case names a document, a language or a
    grammatical construction.

    The sentence those spans are cut from is returned with them. It says each
    token once, which is the situation these shapes describe: the repetition is
    in the composition and nowhere else. Passing a placeholder here instead
    would let the composer's source check pass by never matching anything, and
    the enumeration would then prove nothing about the code that actually runs.
    """

    cases: list[tuple[str, str, str, str, str]] = []
    for modality_len in range(1, 5):
        modality = _TOKENS[:modality_len]
        tail_tokens = _TOKENS[modality_len : modality_len + 2]
        sentence = " ".join(("subj",) + tuple(modality) + tuple(tail_tokens))
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
                                sentence,
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
    for subject, modality, predicate, obj, source in _overlapping_decompositions():
        examined += 1
        title = _title(subject, modality, predicate, obj, source)
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
    for subject, modality, predicate, obj, source in _overlapping_decompositions():
        examined += 1
        title = _title(subject, modality, predicate, obj, source)
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
    ("subject", "modality", "predicate", "obj", "source"),
    [
        # One phrase written into both verb fields, with nothing after it.
        ("alpha", "beta gamma", "beta gamma", "", "alpha beta gamma"),
        # The predicate is the modality minus the word that carried the negation.
        ("alpha", "beta gamma delta", "delta", "", "alpha beta gamma delta"),
        # The object opens with the word the modality ended on.
        ("alpha", "beta gamma", "beta", "gamma delta epsilon", "alpha beta gamma delta epsilon"),
        # Both at once: predicate inside the modality, object colliding with it.
        ("alpha", "beta gamma delta", "beta gamma", "delta epsilon", "alpha beta gamma delta epsilon"),
        # The object repeats the predicate outright, and the source says it once.
        ("alpha", "beta", "gamma delta", "gamma delta", "alpha beta gamma delta"),
    ],
)
def test_named_offender_shapes_compose_cleanly(
    subject: str, modality: str, predicate: str, obj: str, source: str
) -> None:
    """The distinct ways two spans can overlap, each stated once.

    These are shapes, not sentences: every token is meaningless, so a fix that
    recognised particular English words would not satisfy them. Each source says
    its tokens once, so every repetition below was added by the composition.
    """

    title = _title(subject, modality, predicate, obj, source)
    assert _repeated_run(title) is None, f"{title!r} repeats {_repeated_run(title)!r}"


# Titles that repeat a run *because the source does*, with the text they must
# produce. These are the other side of the guard above: the same shapes, the
# same composed appearance, and the opposite correct answer — which is only
# reachable by consulting the source. Asserted as exact strings, because the
# property is not "does not stutter" but "says what the document says".
_SOURCE_ATTESTED_REPETITIONS: list[tuple[str, str, str, str, str, str]] = [
    # The shape that caught this guard over-reaching: a defined term, then a
    # definition opening with the same word. Its own words, deliberately, so
    # the case that was got wrong in the field is pinned in the file that got
    # it wrong.
    (
        "Temporary Work",
        "",
        ":",
        "Work considered by its nature to end within a limited period.",
        "Temporary Work: Work considered by its nature to end within a limited period.",
        "Temporary Work Work considered by its nature to end within a limited period.",
    ),
    # The same shape in meaningless tokens, so the rule cannot be satisfied by
    # recognising anything about the sentence above.
    (
        "alpha beta",
        "",
        ":",
        "beta gamma delta",
        "alpha beta: beta gamma delta.",
        "alpha beta beta gamma delta",
    ),
    # The repetition is separated in the source by punctuation the fields do
    # not carry. Comparing raw words would miss it and the run would be cut.
    (
        "alpha beta",
        "",
        ":",
        "beta gamma",
        "alpha beta \u2014 beta gamma",
        "alpha beta beta gamma",
    ),
    # A whole part the previous part already said, where the source also says
    # it twice. Same fields as the last offender case above; only the source
    # differs, and the answers are opposite.
    (
        "alpha",
        "beta",
        "gamma delta",
        "gamma delta",
        "alpha beta gamma delta gamma delta",
        "alpha beta gamma delta gamma delta",
    ),
]


@pytest.mark.parametrize(
    ("subject", "modality", "predicate", "obj", "source", "expected"),
    _SOURCE_ATTESTED_REPETITIONS,
)
def test_source_attested_repetition_survives(
    subject: str, modality: str, predicate: str, obj: str, source: str, expected: str
) -> None:
    """A repetition the document wrote is the document's words, and stays.

    Trimming it would fuse a term into its own definition and would put text in
    front of a reviewer that the source does not contain. Between a title that
    reads awkwardly and a title that misquotes, this project takes the first.
    """

    assert _title(subject, modality, predicate, obj, source) == expected


def test_the_control_table_is_not_empty() -> None:
    """An empty parametrise list is collected in silence and proves nothing.

    The controls are the only thing standing between this file and a composer
    that deletes repeats indiscriminately, so their disappearance has to be
    louder than their absence would otherwise be.
    """

    assert len(_SOURCE_ATTESTED_REPETITIONS) >= 4, (
        f"only {len(_SOURCE_ATTESTED_REPETITIONS)} control(s) left — this file is back to "
        "testing offenders only, and can no longer detect over-reach"
    )


# ---------------------------------------------------------------------------
# WHERE A TITLE TOO LONG TO SHOW IS CUT
# ---------------------------------------------------------------------------
#
# A title is capped for display. The cap was a character budget alone, so the
# ellipsis landed wherever the 197th character fell -- which on the live corpus
# was inside a word for 29 of the 39 titles long enough to be cut: "constitutes
# confide...", "banning for one time from Promot...".
#
# A marked truncation tells a reader the sentence continues. A truncation
# through a word reads as damage to the record, and sends them to the source to
# find out which it is.


def test_a_title_too_long_to_show_is_cut_between_words() -> None:
    source = (
        "Any information relating to Arab International Schools that is not publicly "
        "available constitutes confidential information and employees are required to "
        "protect it during and after the term of their employment with the company, "
        "including but not limited to salary data and personnel records."
    )
    title = _title("", "", "", "", source)

    assert title.endswith("..."), "a cut title must say it was cut"
    body = title[:-3]
    assert source.startswith(body), "a cut title must be a prefix of what it cut"
    # The cut is mid-word exactly when the source continues with a word
    # character where the title stopped. Checking the title's own last
    # character cannot tell: a correct cut ends on the last letter of a whole
    # word, which is alphanumeric too.
    assert source[len(body)].isspace(), (
        f"the cut fell inside a word: ...{title[-40:]!r}. The budget alone puts the "
        "ellipsis at a character position; it has to fall at a word boundary."
    )
    # The whole point of a boundary is that it keeps a readable title, not that
    # it merely avoids a letter. Collapsing to a fragment would pass the check
    # above while being a worse answer than the mid-word cut it replaced.
    assert len(title) > 150, f"the cut discarded too much: {len(title)} characters left"


def test_an_unbroken_run_is_cut_by_the_budget_rather_than_erased() -> None:
    """The boundary must not win when honouring it would leave nothing.

    A URL, a long identifier, or a script that does not space its words has no
    boundary to find. Preferring one unconditionally would collapse the title
    to whatever preceded the run -- possibly a word or two -- which is a worse
    answer than the mid-word cut. So the boundary is honoured only when it
    keeps most of the budget.
    """

    source = "Reference: " + ("x" * 400)
    title = _title("", "", "", "", source)

    assert title.endswith("...")
    assert len(title) > 150, (
        f"an unbroken run collapsed the title to {len(title)} characters; the word "
        "boundary was preferred where there was effectively none to prefer"
    )

