"""Unit tests for the condition AST interpreter (Section 14.1 / Rule 5.5)."""
from __future__ import annotations

from policy_platform.contracts.conditions import (
    AllCondition,
    AnyCondition,
    ConditionOperator,
    FactComparisonCondition,
    NotCondition,
)
from policy_platform.evaluator.conditions import ConditionOutcome, evaluate_condition


def _fc(fact: str, op: ConditionOperator, value=None) -> FactComparisonCondition:
    return FactComparisonCondition(fact=fact, operator=op, value=value)


class TestLeafComparisons:
    def test_equals_true(self):
        cond = _fc("status", ConditionOperator.EQUALS, "active")
        result = evaluate_condition(cond, {"status": "active"})
        assert result.outcome == ConditionOutcome.TRUE

    def test_equals_false(self):
        cond = _fc("status", ConditionOperator.EQUALS, "active")
        result = evaluate_condition(cond, {"status": "inactive"})
        assert result.outcome == ConditionOutcome.FALSE

    def test_missing_fact_is_indeterminate_not_false(self):
        """Rule 5.5: a missing required fact must be INDETERMINATE, never silently FALSE."""
        cond = _fc("amount", ConditionOperator.GREATER_THAN, 100)
        result = evaluate_condition(cond, {})
        assert result.outcome == ConditionOutcome.INDETERMINATE
        assert result.missing_facts == {"amount"}

    def test_null_fact_value_is_indeterminate(self):
        cond = _fc("amount", ConditionOperator.GREATER_THAN, 100)
        result = evaluate_condition(cond, {"amount": None})
        assert result.outcome == ConditionOutcome.INDETERMINATE

    def test_greater_than_and_less_than(self):
        assert evaluate_condition(_fc("x", ConditionOperator.GREATER_THAN, 5), {"x": 10}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(_fc("x", ConditionOperator.LESS_THAN, 5), {"x": 10}).outcome == ConditionOutcome.FALSE

    def test_in_operator(self):
        cond = _fc("region", ConditionOperator.IN, ["US", "CA"])
        assert evaluate_condition(cond, {"region": "US"}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {"region": "FR"}).outcome == ConditionOutcome.FALSE

    def test_exists_operator_true_and_false(self):
        cond = _fc("optional_field", ConditionOperator.EXISTS)
        assert evaluate_condition(cond, {"optional_field": "x"}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {}).outcome == ConditionOutcome.FALSE

    def test_is_null_operator(self):
        cond = _fc("field", ConditionOperator.IS_NULL)
        assert evaluate_condition(cond, {"field": None}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {"field": "value"}).outcome == ConditionOutcome.FALSE
        # missing entirely -> indeterminate (can't confirm null vs missing)
        assert evaluate_condition(cond, {}).outcome == ConditionOutcome.INDETERMINATE

    def test_date_comparison_via_iso_strings(self):
        cond = _fc("hire_date", ConditionOperator.BEFORE, "2024-06-01")
        assert evaluate_condition(cond, {"hire_date": "2024-01-01"}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {"hire_date": "2024-12-01"}).outcome == ConditionOutcome.FALSE

    def test_incompatible_types_are_indeterminate_not_error(self):
        cond = _fc("amount", ConditionOperator.GREATER_THAN, 100)
        result = evaluate_condition(cond, {"amount": "not-a-number"})
        assert result.outcome == ConditionOutcome.INDETERMINATE


class TestBooleanCombinators:
    def test_all_true_when_all_children_true(self):
        cond = AllCondition(all=[_fc("a", ConditionOperator.EQUALS, 1), _fc("b", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 1, "b": 2})
        assert result.outcome == ConditionOutcome.TRUE

    def test_all_false_short_circuits_even_with_indeterminate_sibling(self):
        """AND: a definite FALSE wins over an INDETERMINATE sibling (Section 15)."""
        cond = AllCondition(all=[_fc("a", ConditionOperator.EQUALS, 1), _fc("missing", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 999})  # a is FALSE, missing is INDETERMINATE
        assert result.outcome == ConditionOutcome.FALSE

    def test_all_indeterminate_when_no_false_but_some_indeterminate(self):
        cond = AllCondition(all=[_fc("a", ConditionOperator.EQUALS, 1), _fc("missing", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 1})
        assert result.outcome == ConditionOutcome.INDETERMINATE
        assert result.missing_facts == {"missing"}

    def test_any_true_short_circuits(self):
        cond = AnyCondition(any=[_fc("a", ConditionOperator.EQUALS, 1), _fc("missing", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 1})
        assert result.outcome == ConditionOutcome.TRUE

    def test_any_indeterminate_when_no_true_but_some_indeterminate(self):
        cond = AnyCondition(any=[_fc("a", ConditionOperator.EQUALS, 1), _fc("missing", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 999})
        assert result.outcome == ConditionOutcome.INDETERMINATE

    def test_any_false_when_all_children_false(self):
        cond = AnyCondition(any=[_fc("a", ConditionOperator.EQUALS, 1), _fc("b", ConditionOperator.EQUALS, 2)])
        result = evaluate_condition(cond, {"a": 999, "b": 999})
        assert result.outcome == ConditionOutcome.FALSE

    def test_not_inverts_true_and_false(self):
        cond_true = NotCondition(**{"not": _fc("a", ConditionOperator.EQUALS, 1)})
        assert evaluate_condition(cond_true, {"a": 1}).outcome == ConditionOutcome.FALSE
        assert evaluate_condition(cond_true, {"a": 2}).outcome == ConditionOutcome.TRUE

    def test_not_propagates_indeterminate_unchanged(self):
        """NOT must not convert an unknown into a definite answer."""
        cond = NotCondition(**{"not": _fc("missing", ConditionOperator.EQUALS, 1)})
        result = evaluate_condition(cond, {})
        assert result.outcome == ConditionOutcome.INDETERMINATE

    def test_nested_combinators(self):
        # (a == 1 AND b == 2) OR (c == 3)
        cond = AnyCondition(
            any=[
                AllCondition(all=[_fc("a", ConditionOperator.EQUALS, 1), _fc("b", ConditionOperator.EQUALS, 2)]),
                _fc("c", ConditionOperator.EQUALS, 3),
            ]
        )
        assert evaluate_condition(cond, {"a": 1, "b": 2, "c": 999}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {"a": 999, "b": 999, "c": 3}).outcome == ConditionOutcome.TRUE
        assert evaluate_condition(cond, {"a": 999, "b": 999, "c": 999}).outcome == ConditionOutcome.FALSE
