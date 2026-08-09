"""Unit tests for the deterministic PolicyTest executor (Section 21.6).

Mirrors test_engine.py's conventions: pure functions, `make_package`/
`make_rule` fixtures, no DB. Exercises `run_policy_test` (the pure
comparison logic in `evaluator/test_runner.py`) directly — this is the
function that decides pass/fail for every `PolicyTest`, so it must never
delegate that judgment to AI.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationStatus
from policy_platform.contracts.policy_test import PolicyTestCase, PolicyTestKind, PolicyTestRunStatus
from policy_platform.evaluator.test_runner import run_policy_test
from tests.fixtures.factories import make_package, make_rule


def _fc(fact, op, value=None):
    return FactComparisonCondition(fact=fact, operator=op, value=value)


class TestRunPolicyTest:
    def test_positive_test_passes_when_overall_status_matches(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Positive: amount within limit",
            test_kind=PolicyTestKind.POSITIVE,
            input_facts={"amount": 50},
            expected_overall_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS
        assert result.response.overall_status == EvaluationStatus.SATISFIED

    def test_negative_test_passes_when_overall_status_matches(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Negative: amount over limit",
            test_kind=PolicyTestKind.NEGATIVE,
            input_facts={"amount": 500},
            expected_overall_status=EvaluationStatus.NOT_SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_fails_with_explanation_when_overall_status_mismatches(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Wrong expectation",
            test_kind=PolicyTestKind.POSITIVE,
            input_facts={"amount": 500},
            expected_overall_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "overall_status" in result.explanation
        assert "SATISFIED" in result.explanation

    def test_boundary_test_at_exact_threshold(self):
        """greaterThanOrEqual at the exact boundary value must be SATISFIED."""
        rule = make_rule("R1", _fc("tenure_years", ConditionOperator.GREATER_THAN_OR_EQUAL, 5))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Boundary: exactly 5 years tenure",
            test_kind=PolicyTestKind.BOUNDARY,
            input_facts={"tenure_years": 5},
            expected_overall_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_missing_fact_test_expects_indeterminate_and_named_fact(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Missing fact: amount omitted",
            test_kind=PolicyTestKind.MISSING_FACT,
            input_facts={},
            expected_overall_status=EvaluationStatus.INDETERMINATE,
            expected_missing_facts=["amount"],
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_missing_fact_test_fails_when_expected_fact_not_actually_missing(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Wrong missing-fact expectation",
            test_kind=PolicyTestKind.MISSING_FACT,
            input_facts={"amount": 50},
            expected_overall_status=EvaluationStatus.SATISFIED,
            expected_missing_facts=["some_other_fact"],
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "missing_facts" in result.explanation

    def test_effective_date_test_rule_not_yet_in_effect(self):
        rule = make_rule(
            "R1", _fc("amount", ConditionOperator.EXISTS), effective_from=date(2099, 1, 1)
        )
        package = make_package([rule], effective_from=date(2099, 1, 1))
        test_case = PolicyTestCase(
            name="Effective-date: before rule starts",
            test_kind=PolicyTestKind.EFFECTIVE_DATE,
            input_facts={"amount": 1},
            evaluation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expected_overall_status=EvaluationStatus.NOT_APPLICABLE,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_effective_date_rule_level_not_applicable_passes_when_rule_is_omitted(self):
        rule = make_rule(
            "R1", _fc("amount", ConditionOperator.EXISTS), effective_from=date(2099, 1, 1)
        )
        package = make_package([rule], effective_from=date(2099, 1, 1))
        test_case = PolicyTestCase(
            name="Effective-date: selected rule before activation",
            test_kind=PolicyTestKind.EFFECTIVE_DATE,
            input_facts={"amount": 1},
            evaluation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expected_overall_status=EvaluationStatus.NOT_APPLICABLE,
            expected_rule_id="R1",
            expected_rule_status=EvaluationStatus.NOT_APPLICABLE,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_unknown_expected_rule_still_fails_when_not_applicable_expected(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.EXISTS))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Unknown rule is not a valid effective-date assertion",
            test_kind=PolicyTestKind.EFFECTIVE_DATE,
            input_facts={"amount": 1},
            expected_overall_status=EvaluationStatus.NOT_APPLICABLE,
            expected_rule_id="DOES_NOT_EXIST",
            expected_rule_status=EvaluationStatus.NOT_APPLICABLE,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "does not exist" in result.explanation

    def test_expected_rule_id_and_status_match_passes(self):
        rule_a = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        # A comparison operator (unlike EXISTS) yields INDETERMINATE, not
        # false, when its fact is absent — used here so the package as a
        # whole is INDETERMINATE while R1 itself is still cleanly SATISFIED.
        rule_b = make_rule("R2", _fc("other", ConditionOperator.GREATER_THAN, 0))
        package = make_package([rule_a, rule_b])
        test_case = PolicyTestCase(
            name="Precedence: pin one rule's outcome",
            test_kind=PolicyTestKind.PRECEDENCE,
            input_facts={"amount": 50},
            expected_overall_status=EvaluationStatus.INDETERMINATE,
            expected_rule_id="R1",
            expected_rule_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.PASS

    def test_expected_rule_id_status_mismatch_fails(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Wrong rule status expectation",
            test_kind=PolicyTestKind.SCOPE,
            input_facts={"amount": 500},
            expected_overall_status=EvaluationStatus.NOT_SATISFIED,
            expected_rule_id="R1",
            expected_rule_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "R1" in result.explanation

    def test_expected_rule_id_not_found_fails_cleanly(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Dangling rule reference",
            test_kind=PolicyTestKind.EXCEPTION,
            input_facts={"amount": 50},
            expected_overall_status=EvaluationStatus.SATISFIED,
            expected_rule_id="DOES_NOT_EXIST",
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "DOES_NOT_EXIST" in result.explanation

    def test_multiple_mismatches_are_all_collected_in_explanation(self):
        rule = make_rule("R1", _fc("amount", ConditionOperator.LESS_THAN_OR_EQUAL, 100))
        package = make_package([rule])
        test_case = PolicyTestCase(
            name="Multiple wrong expectations",
            test_kind=PolicyTestKind.POSITIVE,
            input_facts={"amount": 500},
            expected_overall_status=EvaluationStatus.SATISFIED,
            expected_rule_id="R1",
            expected_rule_status=EvaluationStatus.SATISFIED,
        )

        result = run_policy_test(test_case, package)

        assert result.status == PolicyTestRunStatus.FAIL
        assert "overall_status" in result.explanation
        assert "R1" in result.explanation
