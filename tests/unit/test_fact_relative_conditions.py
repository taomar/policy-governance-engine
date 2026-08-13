"""Comparing a fact against a proportion of another fact.

The condition contract could originally only compare a fact to a literal
value. Measured against live AD-103 output with a trusted fact model
installed, every decision the formulator declared executable for a
compensation limit compared against a *percentage of another fact* — so a
complete and correct fact model still produced zero executable rules.

These tests cover the three layers that had to agree: the parser that reads
the FEEL, the contract that stores the result, and the evaluator that decides
it. The boundary cases matter most: an inclusive limit that is met exactly is
the single most likely value in a compensation dispute.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionOperator,
    FactComparisonCondition,
    FactOperand,
    FactRelativeComparisonCondition,
)
from policy_platform.evaluator.conditions import ConditionOutcome, evaluate_condition
from policy_platform.infrastructure.extraction.formulation_mapping import (
    parse_fact_relative_operand,
    parse_feel_unary_test,
)

SALARY = "employee.compensation.basic_salary"
INCREASE = "employee.compensation.proposed_increase"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "fact", "factor"),
    [
        (f"{SALARY} * 0.05", SALARY, 0.05),
        (f"0.05 * {SALARY}", SALARY, 0.05),
        (f"  {SALARY}*0.10  ", SALARY, 0.10),
        (SALARY, SALARY, 1.0),
        ("a.b.c * 2", "a.b.c", 2.0),
    ],
)
def test_operand_forms_that_are_understood(expression, fact, factor):
    operand = parse_fact_relative_operand(expression)

    assert operand is not None
    assert operand.fact == fact
    assert operand.factor == pytest.approx(factor)


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "5000",
        "0.05",
        # A bare identifier is not a fact path; requiring a dot keeps the
        # parser from reading FEEL keywords or output names as facts.
        "salary",
        # Anything beyond one multiplier stays refused rather than half-read.
        f"{SALARY} * 0.05 + 100",
        f"{SALARY} + {INCREASE}",
        f"max({SALARY}, 100)",
        f"{SALARY} * {INCREASE}",
        f"({SALARY}) * 0.05",
    ],
)
def test_operand_forms_that_are_refused(expression):
    assert parse_fact_relative_operand(expression) is None


def test_unary_test_builds_a_relative_leaf():
    leaves = parse_feel_unary_test(INCREASE, f"<= {SALARY} * 0.05")

    assert leaves is not None
    (leaf,) = leaves
    assert isinstance(leaf, FactRelativeComparisonCondition)
    assert leaf.fact == INCREASE
    assert leaf.operator is ConditionOperator.LESS_THAN_OR_EQUAL
    assert leaf.reference.fact == SALARY
    assert leaf.reference.factor == pytest.approx(0.05)


def test_a_literal_bound_keeps_its_existing_shape():
    """Nothing that already worked may change representation.

    Existing rules are persisted as JSONB and rendered by the web app; a
    literal comparison silently becoming a relative one would change both.
    """

    leaves = parse_feel_unary_test("expense.amount", ">= 5000")

    assert leaves is not None
    (leaf,) = leaves
    assert isinstance(leaf, FactComparisonCondition)
    assert leaf.value == 5000


def test_an_unreadable_expression_is_still_refused():
    assert parse_feel_unary_test(INCREASE, '< date("2024-01-01") + duration("P1Y")') is None


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def _leaf(operator: ConditionOperator, factor: float = 0.05):
    return FactRelativeComparisonCondition(
        fact=INCREASE, operator=operator, reference=FactOperand(fact=SALARY, factor=factor)
    )


@pytest.mark.parametrize(
    ("increase", "expected"),
    [
        (400, ConditionOutcome.TRUE),
        # 5% of 10000 is exactly 500. An inclusive bound met exactly is the
        # value most likely to be disputed, so it is pinned explicitly.
        (500, ConditionOutcome.TRUE),
        (501, ConditionOutcome.FALSE),
        (600, ConditionOutcome.FALSE),
    ],
)
def test_inclusive_upper_bound_at_the_boundary(increase, expected):
    result = evaluate_condition(
        _leaf(ConditionOperator.LESS_THAN_OR_EQUAL),
        {INCREASE: increase, SALARY: 10000},
    )

    assert result.outcome is expected


def test_exclusive_upper_bound_excludes_the_boundary():
    result = evaluate_condition(
        _leaf(ConditionOperator.LESS_THAN), {INCREASE: 500, SALARY: 10000}
    )

    assert result.outcome is ConditionOutcome.FALSE


@pytest.mark.parametrize(
    ("bag", "missing"),
    [
        ({INCREASE: 400}, {SALARY}),
        ({SALARY: 10000}, {INCREASE}),
        ({}, {INCREASE, SALARY}),
        ({INCREASE: 400, SALARY: None}, {SALARY}),
    ],
)
def test_a_missing_operand_is_indeterminate_not_false(bag, missing):
    """Rule 5.5. Reporting FALSE would deny a claim that was never tested.

    Both operands are reported together so a caller asking "what do I need to
    supply?" gets the whole answer in one pass.
    """

    result = evaluate_condition(_leaf(ConditionOperator.LESS_THAN_OR_EQUAL), bag)

    assert result.outcome is ConditionOutcome.INDETERMINATE
    assert result.missing_facts == missing


def test_a_non_numeric_operand_is_indeterminate_not_false():
    result = evaluate_condition(
        _leaf(ConditionOperator.LESS_THAN_OR_EQUAL),
        {INCREASE: "not a number", SALARY: 10000},
    )

    assert result.outcome is ConditionOutcome.INDETERMINATE


def test_an_operator_with_no_numeric_meaning_is_indeterminate():
    """`contains` against a scaled number is meaningless, not false."""

    result = evaluate_condition(
        _leaf(ConditionOperator.CONTAINS), {INCREASE: 400, SALARY: 10000}
    )

    assert result.outcome is ConditionOutcome.INDETERMINATE


def test_it_composes_with_the_existing_boolean_nodes():
    """The real AD-103 3.2.3 shape: a proportional limit AND an approval."""

    tree = AllCondition(
        all=[
            _leaf(ConditionOperator.LESS_THAN_OR_EQUAL),
            FactComparisonCondition(
                fact="approval.board_approved",
                operator=ConditionOperator.EQUALS,
                value=True,
            ),
        ]
    )

    within_and_approved = {INCREASE: 400, SALARY: 10000, "approval.board_approved": True}
    within_not_approved = {INCREASE: 400, SALARY: 10000, "approval.board_approved": False}

    assert evaluate_condition(tree, within_and_approved).outcome is ConditionOutcome.TRUE
    assert evaluate_condition(tree, within_not_approved).outcome is ConditionOutcome.FALSE


def test_a_definite_false_still_wins_over_a_missing_operand():
    """AND semantics are unchanged: FALSE short-circuits past INDETERMINATE."""

    tree = AllCondition(
        all=[
            _leaf(ConditionOperator.LESS_THAN_OR_EQUAL),
            FactComparisonCondition(
                fact="approval.board_approved",
                operator=ConditionOperator.EQUALS,
                value=True,
            ),
        ]
    )

    result = evaluate_condition(tree, {"approval.board_approved": False})

    assert result.outcome is ConditionOutcome.FALSE


# --------------------------------------------------------------------------
# Round-tripping, because these trees are persisted as JSONB
# --------------------------------------------------------------------------


def test_the_node_round_trips_through_json():
    tree = AllCondition(all=[_leaf(ConditionOperator.LESS_THAN_OR_EQUAL)])

    restored = AllCondition.model_validate(tree.model_dump(mode="json"))

    assert restored == tree
    leaf = restored.all[0]
    assert isinstance(leaf, FactRelativeComparisonCondition)
    assert leaf.reference.factor == pytest.approx(0.05)


def test_the_discriminator_distinguishes_the_two_leaf_kinds():
    """A relative leaf must never be read back as a literal comparison."""

    payload = {
        "type": "all",
        "all": [
            {
                "type": "factRelativeComparison",
                "fact": INCREASE,
                "operator": "lessThanOrEqual",
                "reference": {"fact": SALARY, "factor": 0.05},
            },
            {"type": "factComparison", "fact": "a.b", "operator": "equals", "value": 1},
        ],
    }

    tree = AllCondition.model_validate(payload)

    assert isinstance(tree.all[0], FactRelativeComparisonCondition)
    assert isinstance(tree.all[1], FactComparisonCondition)
