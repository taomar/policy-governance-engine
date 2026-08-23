"""A sentence that states no subject has not omitted one.

THE FALSE POSITIVE THIS EXISTS TO PREVENT

Evaluating the AIS handbook reported, three times:

    Rule 'you Please view Appendix A for the Penalty Schedule' (AI-8c3f3b0078):
    'you' — the extraction target derived from canonical 'subject' shares no
    wording with this sentence, so it was supplied from outside it — a reviewer
    should confirm the document says it somewhere.

The document does say it. It says it by writing an imperative, and an
imperative's subject is the addressee, which English leaves unwritten. The
handbook addresses the reader in the second person throughout ("You are
required to comply with the following"), so "you" is the document's own word
for the party — it simply cannot appear in the subject position of a sentence
that has no subject position.

THE GENERAL FAULT, WHICH THIS IS THE FIFTH INSTANCE OF

`check_attributes_are_quoted` requires every attribute to be quotable from the
source sentence. That is right, and it catches invented parties. Asked of a
grammatical position the sentence does not contain, it can never be satisfied,
so a correct decomposition is reported as a fabrication.

It is the same shape as `test_a_backpointer_with_its_antecedent_is_not_damage`:
there a check required a head noun to repeat literally, which penalised
anaphora — the device that exists precisely to avoid repeating it. Here a check
requires a subject to be quoted, which penalises the imperative — the mood that
exists precisely to leave it out. Both are lexical tests standing in for a
grammatical property, and both are biased against correct prose.

WHAT IS DELIBERATELY NOT COVERED

The bare imperative, "Ensure social distancing is maintained at all times".
Genuinely subject-less, and not matched here. Separating it from an ordinary
declarative — "Employees shall comply" — needs to know that "Ensure" is a verb
and "Employees" is a noun, which is a part-of-speech judgement. The two ways to
fake it are a verb list, which is a content classifier by another name, and a
capitalisation heuristic, which was tried and is simply wrong because an
imperative opening a sentence is capitalised like anything else. Neither live
instance is a bare imperative, so this covers what can be identified
structurally and states what it does not cover.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.extraction.evaluability import (
    EvaluabilityAssessment,
    Evaluability,
    ReferencedAttribute,
)
from policy_platform.infrastructure.quality.logic_faithfulness import (
    _sentence_states_no_subject,
    check_attributes_are_quoted,
)


# --------------------------------------------------------------------------
# The grammatical test
# --------------------------------------------------------------------------


#: Verbatim from the AIS handbook where marked. Each states a duty and names
#: nobody to bear it.
_STATES_NO_SUBJECT = [
    "Please view Appendix A for the Penalty Schedule.",
    "Please check with the HR department about the latest Covid regulations "
    "as these are subject to change as per the Ministry of Health",
    "It is mandatory to sign a commitment to attend all activities and events.",
    "Kindly submit the form before Friday.",
    "- Please ensure social distancing is maintained.",
    "3. Please report any incident to your supervisor.",
]


@pytest.mark.parametrize("sentence", _STATES_NO_SUBJECT)
def test_a_subjectless_sentence_is_recognised(sentence: str) -> None:
    assert _sentence_states_no_subject(sentence) is True


#: Sentences that DO name their subject. The exoneration must not reach these,
#: or the check stops catching invented parties, which is what it is for.
#:
#: The last two are the interesting ones and both were mispredicted while this
#: was being written: an impersonal that names its bearer in a `for`- or
#: `of`-phrase is not subject-less, and the tight regex excludes them without
#: needing a special case.
_STATES_ITS_SUBJECT = [
    "You are required to comply with the following:",
    "Employees shall not refuse to follow the directions of the Head.",
    "The HR Department shall maintain personal information for 3 years.",
    "Alcohol and drugs are strictly forbidden.",
    "Slippers are strictly not allowed.",
    "Ensure social distancing is maintained at all times.",
    "It is the responsibility of the supervisor to inform their staff.",
    "It is essential for staff to attend.",
]


@pytest.mark.parametrize("sentence", _STATES_ITS_SUBJECT)
def test_a_sentence_with_a_subject_is_not_exonerated(sentence: str) -> None:
    assert _sentence_states_no_subject(sentence) is False, (
        f"{sentence!r} names its subject; treating it as subject-less would let "
        "an invented party through unreported"
    )


def test_an_empty_sentence_is_not_subjectless() -> None:
    """Absence of a sentence is not a grammatical construction."""

    assert _sentence_states_no_subject("") is False
    assert _sentence_states_no_subject("   ") is False


# --------------------------------------------------------------------------
# The check itself
# --------------------------------------------------------------------------


APPENDIX = "Please view Appendix A for the Penalty Schedule."


def _assessment(*attributes: tuple[str, str]) -> EvaluabilityAssessment:
    return EvaluabilityAssessment(
        evaluability=Evaluability.DECIDABLE,
        reason="test",
        attributes_referenced=[
            ReferencedAttribute(phrase=phrase, role=role) for phrase, role in attributes
        ],
    )


def test_the_addressee_of_an_imperative_is_not_reported() -> None:
    """The live case, end to end through the check."""

    findings = check_attributes_are_quoted(_assessment(("you", "subject")), APPENDIX)
    assert findings == []


def test_a_party_the_sentence_never_names_is_still_reported() -> None:
    """The anti-vacuity case, and the reason this is scoped to the addressee.

    An imperative leaves out its *subject*. It does not license every other
    phrase in the record. "the Board of Trustees" appears nowhere in this
    sentence and is not what "Please view Appendix A" implies.
    """

    findings = check_attributes_are_quoted(
        _assessment(("the Board of Trustees", "subject")), APPENDIX
    )
    assert findings, "an invented party must still be reported"
    assert findings[0].code == "attribute_not_in_source"


def test_the_exoneration_is_scoped_to_the_subject_role() -> None:
    """Only the subject position is empty. Objects and conditions are written.

    An attribute in any other role that reads "you" is not the implied subject —
    it is a phrase the sentence should contain and does not.
    """

    findings = check_attributes_are_quoted(_assessment(("you", "object")), APPENDIX)
    assert findings, "only the subject position is left empty by an imperative"


def test_a_declarative_still_has_its_subject_checked() -> None:
    """The same phrase, a sentence that states a subject: still reported.

    This is the pair that proves the sentence is what decides, not the phrase.
    """

    declarative = "Employees shall not refuse to follow the directions of the Head."
    assert check_attributes_are_quoted(_assessment(("you", "subject")), declarative)
