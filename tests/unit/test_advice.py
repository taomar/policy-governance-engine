"""Unit tests for XACML Obligations/Advice: rule-level `advice` (ADR-0011).

Advice is non-blocking supplementary guidance attached to a rule's decision,
distinct from `effect`/`require_action` (the mandatory Obligation-equivalent
action). Verifies: per-rule transparency on `RuleEvaluationResult.advice`,
aggregation into `EvaluationResponse.advice_notes` scoped to the winning
side only (mirroring `required_actions`/`denied_actions`), and that advice
never leaks from a NOT_SATISFIED or overridden-out rule into the aggregate.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.contracts.policy import Advice, EffectType
from policy_platform.evaluator.engine import evaluate_policy
from tests.fixtures.factories import make_authority, make_package, make_rule

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


class TestAdvice:
    def test_satisfied_rule_surfaces_its_own_advice(self):
        rule = make_rule(
            "R1",
            _ALWAYS_TRUE,
            advice=[Advice(advice_id="A1", text="Consider notifying the requester's manager")],
        )
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        rule_result = next(r for r in response.rule_results if r.rule_id == "R1")
        assert rule_result.status == EvaluationStatus.SATISFIED
        assert rule_result.advice == ["Consider notifying the requester's manager"]
        assert response.advice_notes == ["Consider notifying the requester's manager"]

    def test_not_satisfied_rule_has_no_advice(self):
        rule = make_rule(
            "R1",
            FactComparisonCondition(fact="amount", operator=ConditionOperator.LESS_THAN_OR_EQUAL, value=100),
            advice=[Advice(advice_id="A1", text="Should never appear")],
        )
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"amount": 500})

        response = evaluate_policy(package, request)

        rule_result = next(r for r in response.rule_results if r.rule_id == "R1")
        assert rule_result.status == EvaluationStatus.NOT_SATISFIED
        assert rule_result.advice == []
        assert response.advice_notes == []

    def test_advice_from_multiple_non_conflicting_rules_all_aggregate(self):
        allow_rule = make_rule(
            "R-ALLOW",
            _ALWAYS_TRUE,
            effect_type=EffectType.ALLOW,
            effect_action="allow_purchase",
            advice=[Advice(advice_id="A1", text="Log for audit")],
        )
        require_rule = make_rule(
            "R-REQUIRE",
            _ALWAYS_TRUE,
            effect_type=EffectType.REQUIRE_ACTION,
            effect_action="notify_finance",
            advice=[Advice(advice_id="A2", text="Attach receipt")],
        )
        package = make_package([allow_rule, require_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert set(response.advice_notes) == {"Log for audit", "Attach receipt"}

    def test_overridden_rule_advice_excluded_from_aggregate_but_visible_on_rule(self):
        """An overridden-out SATISFIED rule's own advice stays visible on its
        `RuleEvaluationResult` (transparency), but does not pollute the
        aggregate `advice_notes`, which only reflects the winning side —
        exactly mirroring how `required_actions`/`denied_actions` behave."""
        allow_rule = make_rule(
            "R-ALLOW",
            _ALWAYS_TRUE,
            effect_type=EffectType.ALLOW,
            effect_action="allow_purchase",
            authority=make_authority(rank=5),
            advice=[Advice(advice_id="A1", text="Overridden advice, should not aggregate")],
        )
        deny_rule = make_rule(
            "R-DENY",
            _ALWAYS_TRUE,
            effect_type=EffectType.DENY,
            effect_action="deny_purchase",
            authority=make_authority(rank=50),
            advice=[Advice(advice_id="A2", text="Winning advice")],
        )
        package = make_package([allow_rule, deny_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.advice_notes == ["Winning advice"]
        allow_result = next(r for r in response.rule_results if r.rule_id == "R-ALLOW")
        # still transparent on the individual (overridden) rule result
        assert allow_result.advice == ["Overridden advice, should not aggregate"]
        assert allow_result.overridden_by == "R-DENY"

    def test_advice_contributes_to_result_hash_determinism(self):
        """Section 27.5: same (package, facts) must always yield the same
        result_hash — advice is part of the hashed payload, so two rules
        differing only in advice text must hash differently."""
        rule_with_advice = make_rule("R1", _ALWAYS_TRUE, advice=[Advice(advice_id="A1", text="Some advice")])
        rule_without_advice = make_rule("R1", _ALWAYS_TRUE)
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response_with = evaluate_policy(make_package([rule_with_advice]), request)
        response_without = evaluate_policy(make_package([rule_without_advice]), request)

        assert response_with.result_hash != response_without.result_hash

    def test_no_advice_defaults_to_empty_lists(self):
        """Backward compatibility: rules with no advice (the overwhelming
        majority of existing/real sample data) behave exactly as before."""
        rule = make_rule("R1", _ALWAYS_TRUE)
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        rule_result = next(r for r in response.rule_results if r.rule_id == "R1")
        assert rule_result.advice == []
        assert response.advice_notes == []
