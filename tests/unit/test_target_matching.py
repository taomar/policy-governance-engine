"""Unit tests for Target (scope) matching in the evaluator (Section 15.2 step 4,
Section 14 PolicyScope, Section 5.5/5.7 missing-fact handling applied to Target
matching).

Uses the reserved fact-key convention documented in `PrincipalContext.to_facts()`
and `evaluator.engine._SCOPE_DIMENSIONS`: `subject.persona`,
`subject.organizationalUnit`, `subject.jurisdiction`, `context.process`.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.evaluator.engine import evaluate_policy
from tests.fixtures.factories import make_package, make_rule, make_scope

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


class TestTargetMatching:
    def test_matching_persona_proceeds_to_condition_evaluation(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(personas=["manager"]))
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "subject.persona": "manager"},
        )

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.SATISFIED
        assert response.rule_results[0].status == EvaluationStatus.SATISFIED

    def test_mismatched_persona_is_not_applicable_with_reason(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(personas=["manager"]))
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "subject.persona": "employee"},
        )

        response = evaluate_policy(package, request)

        result = response.rule_results[0]
        assert result.status == EvaluationStatus.NOT_APPLICABLE
        assert result.not_applicable_reason == "scope_mismatch:persona"
        # NOT_SATISFIED/NOT_APPLICABLE rules never appear in satisfied_rules
        assert "R1" not in response.satisfied_rules

    def test_absent_persona_fact_is_indeterminate_not_false(self):
        """Section 5.5/5.7: a restricted scope dimension with no matching
        fact supplied must never be silently treated as a mismatch."""
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(personas=["manager"]))
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        result = response.rule_results[0]
        assert result.status == EvaluationStatus.INDETERMINATE
        assert "subject.persona" in result.missing_facts
        assert response.overall_status == EvaluationStatus.INDETERMINATE

    def test_wildcard_scope_never_restricts(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope())  # all-wildcard default
        package = make_package([rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.overall_status == EvaluationStatus.SATISFIED

    def test_organizational_unit_mismatch_is_not_applicable(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(organizational_units=["finance"]))
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "subject.organizationalUnit": "engineering"},
        )

        response = evaluate_policy(package, request)

        assert response.rule_results[0].not_applicable_reason == "scope_mismatch:organizationalUnit"

    def test_jurisdiction_mismatch_is_not_applicable(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(jurisdictions=["US"]))
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "subject.jurisdiction": "EU"},
        )

        response = evaluate_policy(package, request)

        assert response.rule_results[0].not_applicable_reason == "scope_mismatch:jurisdiction"

    def test_process_mismatch_is_not_applicable(self):
        rule = make_rule("R1", _ALWAYS_TRUE, scope=make_scope(processes=["expense_report"]))
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "context.process": "leave_request"},
        )

        response = evaluate_policy(package, request)

        assert response.rule_results[0].not_applicable_reason == "scope_mismatch:process"

    def test_dimensions_checked_in_deterministic_order(self):
        """When multiple scope dimensions could fail, jurisdiction is checked
        first (matching _SCOPE_DIMENSIONS' fixed order), so it is the one
        reported even though persona also mismatches."""
        rule = make_rule(
            "R1",
            _ALWAYS_TRUE,
            scope=make_scope(jurisdictions=["US"], personas=["manager"]),
        )
        package = make_package([rule])
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "subject.jurisdiction": "EU", "subject.persona": "employee"},
        )

        response = evaluate_policy(package, request)

        assert response.rule_results[0].not_applicable_reason == "scope_mismatch:jurisdiction"
