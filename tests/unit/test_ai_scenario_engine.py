"""Unit tests for the pure, non-AI parts of ai_scenario_engine.py.

Only `find_rule_result` and `_rule_context` are exercised here — everything
else in the module makes real AI/DB calls (see the module's own docstring:
AI only translates scenario<->facts/explanation, the real `evaluate_policy`
always decides). This mirrors test_policy_test_runner.py's convention of
testing evaluator-adjacent logic with plain `make_package`/`make_rule`
fixtures and no mocking.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.evaluator.engine import evaluate_policy
from policy_platform.infrastructure.assistants.ai_scenario_engine import _rule_context, find_rule_result
from tests.fixtures.factories import make_package, make_rule


def _fc(fact, op, value=None):
    return FactComparisonCondition(fact=fact, operator=op, value=value)


class TestFindRuleResult:
    def test_finds_the_matching_rule_result_among_several(self):
        rule_a = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        rule_b = make_rule("R2", _fc("amount", ConditionOperator.GREATER_THAN, 1000))
        package = make_package([rule_a, rule_b])
        request = EvaluationRequest(policy_set_id=package.policy_set_id, facts={"amount": 50})

        response = evaluate_policy(package, request)
        result = find_rule_result("R1", response.rule_results)

        assert result is not None
        assert result.rule_id == "R1"
        assert result.status == EvaluationStatus.SATISFIED

    def test_returns_none_when_rule_not_in_results(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id=package.policy_set_id, facts={"amount": 50})

        response = evaluate_policy(package, request)
        result = find_rule_result("DOES_NOT_EXIST", response.rule_results)

        assert result is None

    def test_rule_not_in_effect_is_absent_from_results_and_applicable_rules(self):
        from datetime import date

        rule = make_rule(
            "R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100), effective_from=date(2099, 1, 1)
        )
        package = make_package([rule], effective_from=date(2099, 1, 1))
        request = EvaluationRequest(policy_set_id=package.policy_set_id, facts={"amount": 50})

        response = evaluate_policy(package, request)
        result = find_rule_result("R1", response.rule_results)

        assert result is None
        assert "R1" not in response.applicable_rules


class TestRuleContext:
    def test_includes_condition_required_facts_and_scope(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))

        context = _rule_context(rule)

        assert context["rule_id"] == "R1"
        assert context["condition"].fact == "amount"
        assert context["scope"]["personas"] == ["*"]
        assert context["required_facts"] == []
        assert context["effect"]["type"] == "allow"
        assert context["machine_executable"] is True
        assert context["dmn_mapping_statuses"] == []
        assert context["formulation_requirements"] == []
