"""`decomposition_malformed` must fire on any route without presupposing one.

The check itself is route-neutral: a damaged decomposition -- an empty subject,
a dangling referent, a mis-split sentence -- is a real defect however a record
is decided, and it fired overwhelmingly on the judged route in the stored runs.
The defect was in the *copy*. The detail read "the logic derived from it cannot
be trusted", which describes only the route where logic is derived from the
decomposition. On the judged route no logic is derived; a reader weighs the
record's words against a case, so that sentence framed a property of the other
route as a fault in the record.

These tests hold two things at once: the finding still fires (removing the copy
defect must not remove the check), and its detail no longer asserts that
derived logic is what the damage spoils.
"""
from __future__ import annotations

from policy_platform.infrastructure.extraction.evaluability import (
    EvaluabilityAssessment,
    Evaluability,
)
from policy_platform.infrastructure.quality.logic_faithfulness import (
    check_malformed_is_reported,
)

# The wording that pins the finding to the route where a decomposition is
# compiled into logic. Its presence is the regression this test locks out.
_DERIVED_LOGIC_TELLS = ("logic derived", "derived from it")


def _malformed_finding():
    assessment = EvaluabilityAssessment(
        evaluability=Evaluability.MALFORMED,
        reason="predicate repeats the modality",
    )
    findings = check_malformed_is_reported(
        assessment, "employees may may also be eligible for the increase"
    )
    assert len(findings) == 1, "the malformed decomposition went unreported"
    return findings[0]


def test_a_malformed_decomposition_is_still_reported():
    """The reword must not cost the detection."""

    finding = _malformed_finding()

    assert finding.code == "decomposition_malformed"
    # Still points the reviewer upstream, to re-extraction, on either route.
    assert "re-extract" in finding.detail.lower()


def test_the_detail_does_not_presuppose_a_derived_logic_route():
    """The detail must not blame damage on logic derived from the decomposition.

    Fails against the prior copy ("the logic derived from it cannot be
    trusted"); passes once the detail speaks route-neutrally about the record
    no longer carrying what its source says.
    """

    detail = _malformed_finding().detail.lower()

    for tell in _DERIVED_LOGIC_TELLS:
        assert tell not in detail, (
            f"detail still frames the damage as spoiling {tell!r}, which only "
            "the compiled route derives"
        )


def test_a_sound_decomposition_stays_silent():
    """Guards the check above: the finding has to mean something when it fires."""

    assessment = EvaluabilityAssessment(
        evaluability=Evaluability.DECIDABLE, reason="states a readable test"
    )

    assert check_malformed_is_reported(assessment, "any source text") == []
