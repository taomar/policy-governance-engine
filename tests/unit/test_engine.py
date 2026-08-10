"""Unit tests for the deterministic evaluation engine (Section 15 / Section 27.5)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from policy_platform.contracts.conditions import (
    AllCondition,
    AnyCondition,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.evaluator.engine import evaluate_policy
from tests.fixtures.factories import make_package, make_rule


def _fc(fact, op, value=None):
    return FactComparisonCondition(fact=fact, operator=op, value=value)


class TestEvaluatePolicy:
    def test_satisfied_when_condition_true(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 50})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.SATISFIED
        assert response.satisfied_rules == ["R1"]

    def test_not_satisfied_when_condition_false(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 500})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.NOT_SATISFIED
        assert response.failed_rules == ["R1"]

    def test_indeterminate_when_required_fact_missing(self):
        """Rule 5.5: missing fact must yield INDETERMINATE, never a silent false decision."""
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.INDETERMINATE
        assert response.missing_facts == ["amount"]

    def test_not_applicable_when_no_rules_apply(self):
        package = make_package([])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 50})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.NOT_APPLICABLE

    def test_rule_outside_effective_window_is_excluded(self):
        future_rule = make_rule(
            "R1", _fc("amount", ConditionOperator.EXISTS), effective_from=date(2099, 1, 1)
        )
        package = make_package([future_rule], effective_from=date(2099, 1, 1))
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"amount": 1},
            evaluation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.NOT_APPLICABLE
        assert "R1" not in response.applicable_rules

    def test_expired_rule_is_excluded(self):
        expired_rule = make_rule(
            "R1",
            _fc("amount", ConditionOperator.EXISTS),
            effective_from=date(2020, 1, 1),
            effective_to=date(2021, 1, 1),
        )
        package = make_package([expired_rule], effective_from=date(2020, 1, 1))
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"amount": 1},
            evaluation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        response = evaluate_policy(package, request)
        assert "R1" not in response.applicable_rules

    def test_non_machine_executable_rule_is_not_applicable(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.EXISTS), machine_executable=False)
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 1})

        response = evaluate_policy(package, request)

        assert response.rule_results[0].status == EvaluationStatus.NOT_APPLICABLE
        assert response.rule_results[0].not_applicable_reason == "rule_not_machine_executable"

    def test_executable_rule_with_empty_all_does_not_match_everything(self):
        # An empty `all` is vacuously TRUE under ordinary boolean algebra, so
        # without a guard this rule would apply to every request ever made —
        # the worst failure mode available to a policy engine, because it is
        # silent and universal rather than merely wrong.
        rule = make_rule("R1", AllCondition(all=[]), machine_executable=True)
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 1})

        response = evaluate_policy(package, request)

        assert response.rule_results[0].status == EvaluationStatus.NOT_APPLICABLE
        assert response.rule_results[0].not_applicable_reason == "rule_condition_empty"
        # Not asserted against `applicable_rules`: that field lists every rule
        # in effect on the date and considered, including ones ruled out — it
        # is not the set that matched. What matters is that an empty condition
        # can never reach a binding outcome.
        assert "R1" not in response.satisfied_rules
        assert response.required_actions == []
        assert response.denied_actions == []

    def test_executable_rule_with_empty_any_does_not_match_everything(self):
        # `any: []` is vacuously FALSE, so it cannot over-match the way `all`
        # does. It is still reported under the same reason: a rule claiming to
        # be executable while carrying no test is a data defect either way, and
        # a reviewer should not have to know the boolean identity of the empty
        # set to find out that nothing was projected.
        rule = make_rule("R1", AnyCondition(any=[]), machine_executable=True)
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 1})

        response = evaluate_policy(package, request)

        assert response.rule_results[0].status == EvaluationStatus.NOT_APPLICABLE
        assert response.rule_results[0].not_applicable_reason == "rule_condition_empty"

    def test_determinism_same_input_same_hash(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 50})

        response_1 = evaluate_policy(package, request)
        response_2 = evaluate_policy(package, request)

        assert response_1.result_hash == response_2.result_hash

    def test_determinism_unaffected_by_fact_dict_key_order(self):
        rule = make_rule(
            "R1",
            AllCondition(
                all=[
                    _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100),
                    _fc("region", ConditionOperator.EQUALS, "US"),
                ]
            ),
        )
        package = make_package([rule])
        request_1 = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 50, "region": "US"})
        request_2 = EvaluationRequest(policy_set_id="test-policy", facts={"region": "US", "amount": 50})

        response_1 = evaluate_policy(package, request_1)
        response_2 = evaluate_policy(package, request_2)

        assert response_1.result_hash == response_2.result_hash

    def test_different_facts_produce_different_hash(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])

        response_1 = evaluate_policy(package, EvaluationRequest(policy_set_id="test-policy", facts={"amount": 50}))
        response_2 = evaluate_policy(package, EvaluationRequest(policy_set_id="test-policy", facts={"amount": 60}))

        assert response_1.result_hash != response_2.result_hash

    def test_exception_overrides_effect_to_not_satisfied(self):
        from policy_platform.contracts.policy import RuleException

        exception = RuleException(
            exception_id="EXC-1",
            description="test exception",
            condition=_fc("category", ConditionOperator.EQUALS, "travel"),
        )
        rule = make_rule(
            "R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 1000), exceptions=[exception]
        )
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 500, "category": "travel"})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.NOT_SATISFIED
        assert "EXC-1" in response.triggered_exceptions

    def test_precedence_applied_before_result_aggregation(self):
        """A higher-authority rule's outcome should appear ordered ahead in applicable_rules."""
        from tests.fixtures.factories import make_authority

        low = make_rule("R-LOW", _fc("x", ConditionOperator.EXISTS), authority=make_authority(rank=5))
        high = make_rule("R-HIGH", _fc("x", ConditionOperator.EXISTS), authority=make_authority(rank=50))
        package = make_package([low, high])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.applicable_rules == ["R-HIGH", "R-LOW"]
