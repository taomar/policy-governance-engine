"""A phrase the document states elsewhere was not invented by the record.

THE FALSE POSITIVE THIS EXISTS TO PREVENT

Run against AD-103 — a different document from the one the rest of this
session's fixes were found on — the quotation checks produced eleven findings
on thirty-seven records, every one BLOCKING:

    'depending on the financial position of the University'
    'subject to the approval of the President'

reported against sentences like "3.2.2. Increase due to promotion, which shall
be provided upon the promotion of an employee to a new position."

Section 3.2 opens with a governing clause stating those conditions, and each
numbered sub-clause becomes a rule that carries them. That is what a governing
stem is for. Compared against its own sentence the condition appears from
nowhere, so a correct decomposition was ranked at the severity reserved for a
record stating something the source does not.

THE FAULT, AND WHY IT IS THE SAME ONE AGAIN

`check_attributes_are_quoted` opens: "Every attribute the evaluator is told to
find must be in the source ... An attribute that is not in *the document* sends
the evaluating LLM looking for something the policy never mentioned."

The contract is document-level. The implementation compared against one
sentence. That is the eighth instance of the fault this codebase keeps finding:
a check judging a narrower context than the decider — or here, than its own
docstring — and then reporting the document as deficient for what it could not
see.

WHY THIS IS EVIDENCE AND NOT PROVENANCE

The obvious alternative is to exonerate anything declaring
`source_origin: inherited_context`. `LogicFindingSeverity` records that design
as already tried and measured: it "correlated 100% with provenance being
declared and 0% with what had actually gone wrong". A declared provenance is
the record's own claim about itself. This reads the document and checks.

A second alternative was built and reverted before this one: comparing content
words rather than all words, so that sharing only "of" and "the" would not
count as reuse. It moved the same seven findings, and it failed
`test_invented_approver_is_blocking` — correctly. "the Chief Financial Officer"
also shares no content word with its sentence, so content-word overlap cannot
tell an invented party from an inherited one. Document evidence can, and the
control below is that same case, now passing.

MEASURED ON BOTH CORPORA

    AD-103   11 blocking -> 11 review
    AIS      6 blocking, 8 reextraction -> unchanged

Nothing moving on the corpus this session was worked against is the evidence
that this corrects the check rather than loosening it.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    EvaluabilityAssessment,
    ReferencedAttribute,
)
from policy_platform.infrastructure.extraction.policy_parties import (
    PartyProvenance,
    PartyRole,
    PolicyParty,
)
from policy_platform.infrastructure.quality.logic_faithfulness import (
    LogicFindingSeverity,
    MismatchShape,
    check_attributes_are_quoted,
    check_parties_are_quoted,
)

#: The numbered sub-clause. States none of the stem's conditions itself.
SUB_CLAUSE = (
    "3.2.2. Increase due to promotion, which shall be provided upon the "
    "promotion of an employee to a new position."
)

#: The governing clause, extracted as its own record like any other. This is
#: what makes the stem's conditions quotable from the document.
DOCUMENT = (
    "3.2. Salary increase at FBSU is granted depending on the financial position "
    "of the University and subject to the approval of the President. || "
    + SUB_CLAUSE
    + " || 3.2.3. Increase due to inflation with a percentage not exceeding 5% of "
    "the employee's basic salary, and subject to the judgment and approval of the "
    "Board of Trustees."
)


def _attributes(*phrases: str) -> EvaluabilityAssessment:
    return EvaluabilityAssessment(
        evaluability=Evaluability.DECIDABLE,
        reason="stated",
        attributes_referenced=[
            ReferencedAttribute(phrase=phrase, role="condition") for phrase in phrases
        ],
    )


def _party(name: str) -> EvaluabilityAssessment:
    return EvaluabilityAssessment(
        evaluability=Evaluability.DECIDABLE,
        reason="stated",
        parties=[
            PolicyParty(
                name=name,
                role=PartyRole.AUTHORITY,
                provenance=PartyProvenance.DELEGATION_PHRASE,
                source_field="requires the approval of",
            )
        ],
    )


#: Verbatim from AD-103.
_INHERITED = [
    "depending on the financial position of the University",
    "subject to the approval of the President",
]


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("claim", _INHERITED)
def test_an_inherited_condition_blocks_without_the_document(claim: str) -> None:
    """The state this fixes, kept as a case so the change stays visible."""

    findings = check_attributes_are_quoted(_attributes(claim), SUB_CLAUSE)
    assert findings and findings[0].severity is LogicFindingSeverity.BLOCKING


@pytest.mark.parametrize("claim", _INHERITED)
def test_an_inherited_condition_is_a_review_once_the_document_is_read(claim: str) -> None:
    findings = check_attributes_are_quoted(_attributes(claim), SUB_CLAUSE, False, DOCUMENT)
    assert findings, "the finding is downgraded, never silenced"
    assert findings[0].severity is LogicFindingSeverity.REVIEW
    assert "the document does state it in another sentence" in findings[0].detail


def test_an_invented_condition_still_blocks_with_the_document() -> None:
    """The anti-vacuity case. Reading the document must not clear everything."""

    findings = check_attributes_are_quoted(
        _attributes("if the Dean of Students agrees"), SUB_CLAUSE, False, DOCUMENT
    )
    assert findings and findings[0].severity is LogicFindingSeverity.BLOCKING


# --------------------------------------------------------------------------
# Parties — the case that rejected the previous attempt
# --------------------------------------------------------------------------


def test_an_invented_approver_still_blocks() -> None:
    """The control that reverted the content-word design, now passing.

    "the Chief Financial Officer" shares no content word with its sentence AND
    appears nowhere in the document. Only the second fact distinguishes it from
    an inherited party, and only the second is evidence.
    """

    findings = check_parties_are_quoted(
        _party("the Chief Financial Officer"), SUB_CLAUSE, False, DOCUMENT
    )
    assert findings and findings[0].severity is LogicFindingSeverity.BLOCKING
    assert "the document does not name" in findings[0].detail


def test_an_approver_named_by_the_governing_clause_is_a_review() -> None:
    findings = check_parties_are_quoted(_party("the President"), SUB_CLAUSE, False, DOCUMENT)
    assert findings and findings[0].severity is LogicFindingSeverity.REVIEW
    assert "the document names them in another" in findings[0].detail


# --------------------------------------------------------------------------
# What document evidence may and may not change
# --------------------------------------------------------------------------


def test_a_flattened_table_row_is_not_downgraded() -> None:
    """REEXTRACTION is about how the document was READ, not what it says.

    Finding the text elsewhere says nothing about a welded cell boundary, so
    the severity is untouched — it would otherwise be presented as a wording
    decision, which no reviewer can act on.
    """

    claim = "1 Time; 2 Time; 3 Time"
    findings = check_attributes_are_quoted(
        _attributes(claim), SUB_CLAUSE, False, DOCUMENT + " || " + claim
    )
    assert findings
    assert findings[0].shape is MismatchShape.CONCATENATED
    assert findings[0].severity is LogicFindingSeverity.REEXTRACTION


def test_severity_only_ever_moves_downward() -> None:
    """Document evidence may lower a blocking verdict. It may not raise one.

    A review finding that turned blocking because its words appear elsewhere
    would be nonsense — being stated in the document is exculpatory or nothing.
    """

    without = check_attributes_are_quoted(_attributes(_INHERITED[0]), SUB_CLAUSE)
    with_doc = check_attributes_are_quoted(_attributes(_INHERITED[0]), SUB_CLAUSE, False, DOCUMENT)
    order = {
        LogicFindingSeverity.REVIEW: 0,
        LogicFindingSeverity.REEXTRACTION: 1,
        LogicFindingSeverity.BLOCKING: 2,
    }
    assert order[with_doc[0].severity] <= order[without[0].severity]


def test_an_empty_document_reproduces_the_old_behaviour() -> None:
    """Every existing caller passes nothing, and must be unaffected."""

    a = check_attributes_are_quoted(_attributes(_INHERITED[0]), SUB_CLAUSE)
    b = check_attributes_are_quoted(_attributes(_INHERITED[0]), SUB_CLAUSE, False, "")
    assert [(f.severity, f.detail) for f in a] == [(f.severity, f.detail) for f in b]
