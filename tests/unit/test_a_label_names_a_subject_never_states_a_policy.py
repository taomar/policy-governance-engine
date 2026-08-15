"""A generated label names a subject; it never states what a document says.

WHAT THESE PROVE

The label is the one string on a policy card this system wrote. Everything
around it is the document's characters, quoted whole, and a reviewer decides
whether to approve a rule by reading those. So the label carries a risk nothing
else on the card carries: if it ever reads like a claim about the document, it
becomes an unsourced assertion sitting inside evidence.

The defence is shape, not vocabulary. A vocabulary check would need a list of
words, a list of words is a list from some domain, and this reads whatever a
customer uploads. So what is asserted here is that the validator refuses replies
by their form, and that the forms it refuses are the forms a statement takes.

Every input below is written for this file. None of it is a phrase from any
document in the corpus, and no count in it is a measurement of one — a test that
encoded what a document happens to contain would pass by describing that
document rather than by describing the rule.
"""

from __future__ import annotations

from policy_platform.infrastructure.assistants.provision_topic_label import (
    MAX_LABEL_WORDS,
    UNAVAILABLE_NO_SOURCE,
    UNAVAILABLE_REPLY_UNUSABLE,
    build_source,
    validate_label,
)

#: A source in one writing system, and a source in another. Neither is taken
#: from a document; both exist so that "the reply is in the source's script" can
#: be tested in both directions rather than only in the one the corpus has.
_LATIN = build_source(["Section one"], ["The stated arrangement applies to each case."])
_ARABIC = build_source(["\u0642\u0633\u0645"], ["\u064a\u0646\u0637\u0628\u0642 \u0647\u0630\u0627 \u0627\u0644\u062a\u0631\u062a\u064a\u0628 \u0639\u0644\u0649 \u0643\u0644 \u062d\u0627\u0644\u0629."])


def test_a_short_noun_phrase_is_accepted() -> None:
    label, code = validate_label("Stated arrangement", _LATIN)
    assert label == "Stated arrangement"
    assert code is None


def test_the_reply_is_stored_exactly_as_it_came_back() -> None:
    """No case folding, no trimming of words, no rewriting.

    A label the system edited is a label whose provenance record is wrong: it
    says a model produced these words and a function produced different ones.
    Only surrounding whitespace and one enclosing quote pair are removed.
    """

    label, _ = validate_label("  Stated  arrangement  ", _LATIN)
    assert label == "Stated arrangement"


def test_a_sentence_is_refused() -> None:
    """The failure this whole module exists to prevent.

    A phrase naming a subject cannot be read as a claim. A sentence beside
    verbatim evidence will be, and nobody sourced it.
    """

    label, code = validate_label(
        "Each case is handled under the stated arrangement.", _LATIN
    )
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_quantity_is_refused() -> None:
    """A subject has no number in it; a claim about a document usually does.

    This is why no digit is allowed at all rather than only some digits: a
    threshold, a duration, an amount and a date are the four things a reader
    would most wrongly take as sourced.
    """

    label, code = validate_label("Arrangement of 40 units", _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_terminal_mark_is_refused() -> None:
    label, code = validate_label("Stated arrangement.", _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_reply_longer_than_the_ceiling_is_refused() -> None:
    """The ceiling is on shape and is asserted through the constant.

    Writing the number here would make this test agree with the code by
    coincidence rather than by construction, and the two would drift apart
    silently the first time the ceiling moved.
    """

    label, code = validate_label(" ".join(["word"] * (MAX_LABEL_WORDS + 1)), _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE

    label, code = validate_label(" ".join(["word"] * MAX_LABEL_WORDS), _LATIN)
    assert label is not None
    assert code is None


def test_a_reply_in_a_script_the_source_does_not_use_is_refused() -> None:
    """Both directions, so this is a rule and not a preference for one script.

    The label is read by the person reading the passage, so it is written in
    the writing system the passage uses. Which system that is is read off the
    source at run time; nothing here names a language.
    """

    label, code = validate_label("\u0627\u0644\u062a\u0631\u062a\u064a\u0628", _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE

    label, code = validate_label("Stated arrangement", _ARABIC)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_reply_in_the_source_script_is_accepted_whatever_that_script_is() -> None:
    label, code = validate_label("\u0627\u0644\u062a\u0631\u062a\u064a\u0628", _ARABIC)
    assert label == "\u0627\u0644\u062a\u0631\u062a\u064a\u0628"
    assert code is None


def test_a_reply_in_a_third_script_is_refused_though_it_reads_the_same_way() -> None:
    """The check that direction class alone did not catch.

    Direction class separates only left-to-right from right-to-left, so a reply
    in an unrelated left-to-right script passed against a left-to-right source.
    That was observed against real data before this test existed.
    """

    label, code = validate_label("\u62db\u8058\u7a0b\u5e8f", _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_an_empty_reply_is_a_failure_and_never_an_empty_label() -> None:
    """Absence and emptiness stay apart all the way down.

    If an empty reply could be stored as a label, a card would render nothing
    where a name goes and a reviewer could not tell that from a name nobody has
    asked for yet. Refusing it here is what makes the interface's three states
    true rather than merely drawn.
    """

    for reply in ("", "   ", "\n"):
        label, code = validate_label(reply, _LATIN)
        assert label is None
        assert code == UNAVAILABLE_REPLY_UNUSABLE


def test_a_source_with_no_words_is_reported_as_such() -> None:
    """A different fact from a bad reply, and recorded as a different code.

    Nothing was asked of the model, so nothing failed. Conflating the two would
    send somebody looking at a model that was never called.
    """

    from policy_platform.infrastructure.assistants.provision_topic_label import (
        generate_label,
    )
    import asyncio

    attempt = asyncio.run(generate_label(build_source([], [])))
    assert attempt.label is None
    assert attempt.unavailable_code == UNAVAILABLE_NO_SOURCE
    assert attempt.model_deployment is None


def test_quotation_marks_never_survive_into_a_label() -> None:
    """A label wearing quotes presents itself as somebody's exact words.

    It is not anybody's. An enclosing pair is a formatting habit and is removed;
    anything else is refused rather than repaired, because repairing it would
    mean this system editing the words it is about to attribute to a model.
    """

    label, _ = validate_label('"Stated arrangement"', _LATIN)
    assert label == "Stated arrangement"

    label, code = validate_label('Stated "arrangement" here', _LATIN)
    assert label is None
    assert code == UNAVAILABLE_REPLY_UNUSABLE
