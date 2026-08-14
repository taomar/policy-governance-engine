"""What a compiled comparison is allowed to compare.

A compiled condition asserts that the document stated a test. It also asserts
*what the test is about*: the fact named on the left of the comparison is the
operand a case engine will bind a real value to. Naming it wrongly does not
produce a rule that fails to fire -- it produces one that fires against the
wrong number while looking perfectly computable, which is the one outcome worse
than not routing at all.

The defect these tests exist to prevent bound the comparison to the sentence's
grammatical *subject*: the population a rule governs rather than the quantity it
measures. "Part-time employees ... not more than 24 hours per week" compiled to
`part-time-employees <= 24`, which asserts that the number of part-time
employees is at most twenty-four. The document said nothing of the kind.

So the invariant is: the operand is what the number counts. The subject says
whom the rule governs, and that belongs to the rule's scope, not inside its
arithmetic.

Both directions are guarded. A subject that is a population must never become
the operand; a subject that genuinely *is* the measured thing -- an interval, a
term, a limit -- must still reach the operand, because a fix that only suppressed
subjects would break the case it was never meant to touch.

Phrasings are generic. The shapes come from observed failures, the vocabulary
does not, so these tests say the compiler handles a construction rather than
that it handles one handbook.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import ConditionOperator
from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.extraction.policy_facts import _slugify
from policy_platform.infrastructure.extraction.quantity_projection import (
    project_stated_quantity,
)


def rule(**kwargs) -> CanonicalPolicyRule:
    base = {
        "rule_type": CanonicalRuleType.OBLIGATION,
        "subject": "the reported delay",
        "predicate": "is recorded",
    }
    base.update(kwargs)
    return CanonicalPolicyRule(**base)


#: (label, subject, predicate, threshold, unit, dimension the operand must name)
#: The first two are the observed failure shapes: a population capped at a rate,
#: and a population qualified by a tenure. The third and fourth are the control
#: -- the subject is itself the thing measured, and must survive the fix.
BINDINGS = [
    ("population capped at a rate", "Associate participants", "are",
     "not more than 20 hours per week", "hours", "hours"),
    ("population qualified by tenure", "Enrolled members",
     "become eligible after", "at least 9 (nine) months", "months", "months"),
    ("subject is the measured interval", "The review interval", "shall be",
     "not more than 6 months", "months", "months"),
    ("subject is the measured allowance", "The carried-forward allowance",
     "shall be", "at most 5 days", "days", "days"),
]


@pytest.mark.parametrize(
    ("label", "subject", "predicate", "threshold", "unit", "dimension"),
    BINDINGS,
    ids=[b[0] for b in BINDINGS],
)
def test_the_operand_names_what_the_number_counts(
    label, subject, predicate, threshold, unit, dimension
):
    """The compared fact denotes the measured quantity, in its stated unit."""

    projection = project_stated_quantity(
        rule(subject=subject, predicate=predicate, threshold=threshold, unit=unit)
    )
    assert projection is not None and projection.compiled, (
        f"{label}: expected a compiled comparison"
    )

    fact = projection.condition.fact
    assert dimension in fact, (
        f"{label}: operand {fact!r} does not name what the number counts "
        f"({dimension!r}); a case engine would bind the wrong value to it"
    )


@pytest.mark.parametrize(
    ("label", "subject", "predicate", "threshold", "unit", "dimension"),
    [b for b in BINDINGS if b[0].startswith("population")],
    ids=[b[0] for b in BINDINGS if b[0].startswith("population")],
)
def test_a_population_subject_is_never_the_compared_operand(
    label, subject, predicate, threshold, unit, dimension
):
    """The operand is not the population the rule governs.

    This is the failure exactly as observed: a comparison whose left-hand side
    was a group of people and whose right-hand side was a duration.
    """

    projection = project_stated_quantity(
        rule(subject=subject, predicate=predicate, threshold=threshold, unit=unit)
    )
    assert projection is not None and projection.compiled

    fact = projection.condition.fact
    assert fact != _slugify(subject), (
        f"{label}: operand is the bare subject {fact!r} -- the comparison reads "
        f"as a count of the population, not of {dimension!r}"
    )


def test_the_measured_thing_survives_when_the_subject_is_the_measurement():
    """A subject that is legitimately the measured thing still reaches the operand.

    The control. Suppressing subjects wholesale would pass every test above and
    silently discard the identity of a rule whose subject was never the problem,
    collapsing distinct limits that share a unit onto one indistinguishable fact.
    """

    projection = project_stated_quantity(
        rule(
            subject="The review interval",
            predicate="shall be",
            threshold="not more than 6 months",
            unit="months",
        )
    )
    assert projection is not None and projection.compiled

    fact = projection.condition.fact
    assert "review" in fact and "interval" in fact, (
        f"operand {fact!r} lost the measured thing's identity; two limits "
        "sharing a unit would become the same fact"
    )


def test_two_limits_sharing_a_unit_do_not_collapse_onto_one_fact():
    """Distinct measured things stay distinct operands.

    Naming the operand after the unit alone would compare both of these to
    `days`, and a case engine binding one value would answer both rules.
    """

    first = project_stated_quantity(
        rule(subject="The notice period", predicate="shall be",
             threshold="at least 30 days", unit="days")
    )
    second = project_stated_quantity(
        rule(subject="The carried-forward allowance", predicate="shall be",
             threshold="at most 5 days", unit="days")
    )
    assert first is not None and first.compiled
    assert second is not None and second.compiled
    assert first.condition.fact != second.condition.fact


def test_the_operator_and_value_are_unchanged_by_the_binding():
    """Renaming the operand must not disturb the comparison it carries."""

    projection = project_stated_quantity(
        rule(
            subject="Associate participants",
            predicate="are",
            threshold="not more than 20 hours per week",
            unit="hours",
        )
    )
    assert projection is not None and projection.compiled
    assert projection.condition.operator is ConditionOperator.LESS_THAN_OR_EQUAL
    assert projection.condition.value == 20.0


def test_the_declared_fact_matches_the_operand_it_compares():
    """The required fact a reviewer sees is the one the condition compares.

    A condition naming one fact while the record declares another would send a
    case engine looking for a value nobody was asked to supply.
    """

    projection = project_stated_quantity(
        rule(
            subject="Enrolled members",
            predicate="become eligible after",
            threshold="at least 9 (nine) months",
            unit="months",
        )
    )
    assert projection is not None and projection.compiled
    assert [f.name for f in projection.facts] == [projection.condition.fact]
