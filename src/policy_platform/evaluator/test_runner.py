"""Deterministic PolicyTest executor (Section 21.6 / 9.11 step 6).

This is the ONLY place a `PolicyTestCase`'s expectations are compared
against a real evaluation outcome. Like `engine.py`, it must remain free of
any AI/DB/network call: `run_policy_test` takes a plain
`ApprovedPolicyPackage` + `PolicyTestCase` and returns a
`PolicyTestExecutionResult` — nothing here decides pass/fail by asking an
LLM, it only calls the real `evaluate_policy` and diffs the result against
the test's stored expectations. AI may PROPOSE a `PolicyTestCase` (see
`infrastructure/ai_test_proposal.py`), but only this function ever executes
one.
"""
from __future__ import annotations

from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.contracts.policy import ApprovedPolicyPackage
from policy_platform.contracts.policy_test import (
    PolicyTestCase,
    PolicyTestExecutionResult,
    PolicyTestRunStatus,
)
from policy_platform.evaluator.engine import evaluate_policy


def run_policy_test(test_case: PolicyTestCase, package: ApprovedPolicyPackage) -> PolicyTestExecutionResult:
    """Execute `test_case` against `package` via the real evaluator and
    compare the outcome against the test's expected_* assertions.

    Every mismatch is collected (not just the first) so a failing test's
    explanation tells a reviewer everything that was wrong in one read.
    """

    request = EvaluationRequest(
        policy_set_id=package.policy_set_id,
        policy_version_id=package.policy_version_id,
        use_active_version=False,
        evaluation_timestamp=test_case.evaluation_timestamp,
        facts=test_case.input_facts,
        correlation_id=None,
        calling_system_identity=f"policy_test:{test_case.name}",
    )
    response = evaluate_policy(package, request)

    mismatches: list[str] = []

    if response.overall_status != test_case.expected_overall_status:
        mismatches.append(
            f"expected overall_status={test_case.expected_overall_status.value}, "
            f"got {response.overall_status.value}"
        )

    if test_case.expected_rule_id:
        package_rule = next((rule for rule in package.rules if rule.rule_id == test_case.expected_rule_id), None)
        rule_result = next((r for r in response.rule_results if r.rule_id == test_case.expected_rule_id), None)
        if package_rule is None:
            mismatches.append(
                f"expected rule '{test_case.expected_rule_id}' does not exist in the tested policy version"
            )
        elif (
            rule_result is None
            and test_case.expected_rule_status == EvaluationStatus.NOT_APPLICABLE
            and test_case.expected_rule_id not in response.applicable_rules
        ):
            # Rules outside their effective window are deliberately excluded
            # before `_evaluate_rule`, so there is no per-rule result row. For an
            # effective-date assertion, that absence IS the expected
            # NOT_APPLICABLE outcome, not a dangling rule reference.
            pass
        elif rule_result is None:
            mismatches.append(
                f"rule '{test_case.expected_rule_id}' exists in the tested version but produced no per-rule result "
                "(it may be outside its effective window); expected "
                f"{test_case.expected_rule_status.value if test_case.expected_rule_status else 'a result'}"
            )
        elif test_case.expected_rule_status is not None and rule_result.status != test_case.expected_rule_status:
            mismatches.append(
                f"expected rule '{test_case.expected_rule_id}' status="
                f"{test_case.expected_rule_status.value}, got {rule_result.status.value}"
            )

    if test_case.expected_missing_facts is not None:
        expected_missing = set(test_case.expected_missing_facts)
        actual_missing = set(response.missing_facts)
        unmet = expected_missing - actual_missing
        if unmet:
            mismatches.append(
                f"expected missing_facts to include {sorted(unmet)}, but the evaluation's actual "
                f"missing_facts were {sorted(actual_missing)}"
            )

    if mismatches:
        return PolicyTestExecutionResult(
            status=PolicyTestRunStatus.FAIL, explanation="; ".join(mismatches), response=response
        )
    return PolicyTestExecutionResult(
        status=PolicyTestRunStatus.PASS, explanation="All expected assertions matched.", response=response
    )
