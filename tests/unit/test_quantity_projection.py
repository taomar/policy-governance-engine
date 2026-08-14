"""The quantity compiler: what it compiles, and what it refuses to.

The refusals carry the weight here. Compiling a comparison asserts the document
stated a test, so every test below that expects `None` is guarding against the
one defect this feature could introduce -- a fabricated limit that looks
computable.

Phrasings are written generically rather than lifted from any document the
project happens to hold, so the suite says the reader handles a construction
rather than that it handles one handbook.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import ConditionOperator
from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.extraction.quantity_projection import (
    QuantityRefusal,
    project_stated_quantity,
    stated_comparison,
)


def rule(**kwargs) -> CanonicalPolicyRule:
    base = {
        "rule_type": CanonicalRuleType.OBLIGATION,
        "subject": "the reported delay",
        "predicate": "is recorded",
    }
    base.update(kwargs)
    return CanonicalPolicyRule(**base)


@pytest.mark.parametrize(
    ("threshold", "operator", "value"),
    [
        ("more than 15 units", ConditionOperator.GREATER_THAN, 15.0),
        ("greater than 3 units", ConditionOperator.GREATER_THAN, 3.0),
        ("exceeding 7 units", ConditionOperator.GREATER_THAN, 7.0),
        ("less than 50.25 units", ConditionOperator.LESS_THAN, 50.25),
        ("under 12 units", ConditionOperator.LESS_THAN, 12.0),
        ("at least 6 units", ConditionOperator.GREATER_THAN_OR_EQUAL, 6.0),
        ("a minimum of 2 units", ConditionOperator.GREATER_THAN_OR_EQUAL, 2.0),
        ("up to 60 units", ConditionOperator.LESS_THAN_OR_EQUAL, 60.0),
        ("at most 4 units", ConditionOperator.LESS_THAN_OR_EQUAL, 4.0),
        ("not exceeding 9 units", ConditionOperator.LESS_THAN_OR_EQUAL, 9.0),
    ],
)
def test_compiles_a_stated_comparison(threshold, operator, value) -> None:
    projection = project_stated_quantity(rule(threshold=threshold))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.operator is operator
    assert projection.condition.value == value


@pytest.mark.parametrize(
    ("threshold", "operator"),
    [
        ("no more than 30 units", ConditionOperator.LESS_THAN_OR_EQUAL),
        ("not more than 30 units", ConditionOperator.LESS_THAN_OR_EQUAL),
        ("no less than 30 units", ConditionOperator.GREATER_THAN_OR_EQUAL),
        ("not less than 30 units", ConditionOperator.GREATER_THAN_OR_EQUAL),
    ],
)
def test_a_negated_comparative_is_not_read_as_its_opposite(threshold, operator) -> None:
    """"no more than" is a cap. Read as "more than" it would become a floor.

    This is the failure that matters most in the whole module: it does not
    produce a missing rule, it produces an inverted one, and an inverted rule
    passes every check that only asks whether a condition exists.
    """

    projection = project_stated_quantity(rule(threshold=threshold))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.operator is operator


def test_a_figure_written_twice_is_one_value_not_a_range() -> None:
    """Documents write a number in words and numerals for legal clarity."""

    projection = project_stated_quantity(rule(threshold="more than fifteen (15) units"))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.value == 15.0


def test_grouped_thousands_read_as_one_number() -> None:
    projection = project_stated_quantity(rule(threshold="more than 100 000 units"))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.value == 100000.0


@pytest.mark.parametrize(
    ("threshold", "refusal"),
    [
        ("30 to 90 units", QuantityRefusal.RANGE),
        ("(2 to 6) units", QuantityRefusal.RANGE),
        ("45 units per period", QuantityRefusal.NO_COMPARISON),
        ("one (1) unit", QuantityRefusal.NO_COMPARISON),
        ("3 units", QuantityRefusal.NO_COMPARISON),
        ("several units", QuantityRefusal.NOT_A_NUMBER),
        ("7:05", QuantityRefusal.NOT_A_NUMBER),
        ("50%", QuantityRefusal.NO_BASE),
    ],
)
def test_refuses_and_says_why(threshold, refusal) -> None:
    projection = project_stated_quantity(rule(threshold=threshold))

    assert projection is not None
    assert not projection.compiled
    assert projection.refusal is refusal
    assert projection.quantity_text == threshold


def test_a_bare_magnitude_never_becomes_a_limit() -> None:
    """The defect this feature could introduce, stated as its own test.

    "45 units per period" says what the quantity is. Nothing in it says a case
    fails by exceeding it. A compiler that guessed a direction here would
    manufacture a rule the document does not contain, and it would look
    exactly like a rule the document does contain.
    """

    projection = project_stated_quantity(rule(threshold="45 units per period"))

    assert projection is not None
    assert projection.condition is None


def test_no_threshold_is_not_a_refusal() -> None:
    """Silence is right where there is no quantity: nothing to explain."""

    assert project_stated_quantity(rule()) is None


def test_a_proportion_of_a_stated_base_is_left_to_the_other_compiler() -> None:
    projection = project_stated_quantity(
        rule(threshold="10% of the reference amount")
    )

    assert projection is None


def test_the_unit_travels_with_the_fact() -> None:
    """A comparison against a bare number is not yet a rule.

    "delay > 15" is satisfied by fifteen of anything. The unit is what makes it
    a policy, so it has to reach the consumer that supplies the value.
    """

    projection = project_stated_quantity(
        rule(threshold="more than 15 units", unit="units")
    )

    assert projection is not None
    assert projection.facts[0].unit == "units"


def test_the_unit_is_read_from_the_words_when_no_unit_field_is_set() -> None:
    projection = project_stated_quantity(rule(threshold="more than 15 calendar units"))

    assert projection is not None
    assert projection.facts[0].unit == "calendar units"


def test_the_fact_is_named_after_the_rules_own_subject() -> None:
    """Never a path into someone's schema, which the document never stated."""

    projection = project_stated_quantity(
        rule(subject="the accumulated delay", threshold="more than 15 units")
    )

    assert projection is not None
    assert "delay" in projection.condition.fact
    assert projection.facts[0].name == projection.condition.fact


def test_a_comparison_in_the_predicate_is_read_when_the_threshold_states_none() -> None:
    projection = project_stated_quantity(
        rule(predicate="shall not exceed", threshold="9 units")
    )

    assert projection is not None
    assert projection.compiled
    assert projection.condition.operator is ConditionOperator.LESS_THAN_OR_EQUAL


def test_the_threshold_wins_over_the_predicate() -> None:
    """A comparative beside the number qualifies that number.

    One in the predicate may govern something else the sentence also says, so
    where both are present the one attached to the quantity is the safer read.
    """

    projection = project_stated_quantity(
        rule(predicate="shall be at least", threshold="up to 5 units")
    )

    assert projection is not None
    assert projection.condition.operator is ConditionOperator.LESS_THAN_OR_EQUAL


def test_stated_comparison_infers_nothing_from_silence() -> None:
    assert stated_comparison("", None, "a plain phrase") is None


@pytest.mark.parametrize(
    ("threshold", "operator"),
    [
        # A trailing phrase that carries its own comparative governing
        # something other than the number: an accounting period, a scope, a
        # deadline for an unrelated step.
        ("more than 15 units within a stated period", ConditionOperator.GREATER_THAN),
        ("more than 30 units within a stated period", ConditionOperator.GREATER_THAN),
        ("at least 10 units within a stated period", ConditionOperator.GREATER_THAN_OR_EQUAL),
        ("less than 20 units over a stated period", ConditionOperator.LESS_THAN),
    ],
)
def test_a_comparative_governing_something_else_does_not_win(
    threshold, operator
) -> None:
    """The comparative attached to the number is the one that governs it.

    "within" is a genuine cap phrase -- "within 30 units" means at most 30 --
    but in "more than 15 units within a stated period" it governs the period,
    not the fifteen. Reading it as the comparison inverts the rule: a
    threshold the source sets as a floor compiles as a ceiling, and the result
    fires on exactly the cases the source exempts while looking computable.

    Losing a rule is recoverable. Inverting one is not, because nothing
    downstream can tell an inverted condition from an intended one.
    """

    projection = project_stated_quantity(rule(threshold=threshold))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.operator is operator


def test_a_comparison_stated_after_the_number_is_still_read() -> None:
    projection = project_stated_quantity(rule(threshold="30 units or less"))

    assert projection is not None
    assert projection.compiled
    assert projection.condition.operator is ConditionOperator.LESS_THAN_OR_EQUAL


def test_a_trailing_comparative_is_not_part_of_the_unit() -> None:
    """A unit is what the number counts, and "or less" counts nothing."""

    projection = project_stated_quantity(rule(threshold="30 units or less"))

    assert projection is not None
    assert projection.facts[0].unit == "units"


def test_a_qualifier_stays_in_the_unit() -> None:
    """"per week" changes what the count is taken over, so it is not noise."""

    projection = project_stated_quantity(rule(threshold="not more than 24 units per week"))

    assert projection is not None
    assert projection.facts[0].unit == "units per week"
