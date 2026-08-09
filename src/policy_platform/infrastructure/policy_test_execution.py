"""DB-aware execution of `PolicyTest` rows (Section 21.6 / 9.11 step 6).

Bridges the repository layer and the pure `evaluator.test_runner` function:
loads a `PolicyTest` + resolves the `ApprovedPolicyVersion` to run it
against, builds the `ApprovedPolicyPackage` via the same
`approved_policy_version_to_package` mapper `evaluations.py` uses, calls the
pure `run_policy_test`, and persists the outcome as an immutable
`PolicyTestRun` row. Used by both the manual "run now" endpoint
(`api/routers/policy_tests.py`) and the on-publish auto-rerun hook
(`api/routers/candidate_rules.py::publish_approved_candidates`), so both
call paths share identical execution semantics.

Never lets AI decide pass/fail: only `evaluator.test_runner.run_policy_test`
(itself a thin wrapper around `evaluator.engine.evaluate_policy`) computes a
result here.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.evaluation import EvaluationStatus
from policy_platform.contracts.policy import ApprovedPolicyPackage
from policy_platform.contracts.policy_test import PolicyTestCase, PolicyTestKind
from policy_platform.domain.models import PolicyTest, PolicyTestRun
from policy_platform.evaluator.test_runner import run_policy_test
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.policy_test_commitment import expectation_hash, expectation_snapshot_for_test
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    PolicyTestRepository,
    PolicyTestBatchRepository,
    PolicyTestRunRepository,
)


def _build_test_case(test: PolicyTest) -> PolicyTestCase:
    return PolicyTestCase(
        name=test.name,
        test_kind=PolicyTestKind(test.test_kind),
        input_facts=test.input_facts_json or {},
        evaluation_timestamp=test.evaluation_timestamp_override,
        expected_overall_status=EvaluationStatus(test.expected_overall_status),
        expected_rule_id=test.expected_rule_id,
        expected_rule_status=EvaluationStatus(test.expected_rule_status) if test.expected_rule_status else None,
        expected_missing_facts=test.expected_missing_facts_json,
    )


def _execute_single_test(test: PolicyTest, package: ApprovedPolicyPackage) -> tuple[str, str, dict | None]:
    """Run one test, never letting a malformed test or evaluator surprise
    propagate as an unhandled exception — a bad test becomes a `status="error"`
    run instead, so one bad `PolicyTest` can never block publish or abort a
    batch of otherwise-fine tests."""
    try:
        test_case = _build_test_case(test)
        result = run_policy_test(test_case, package)
        return result.status.value, result.explanation, result.response.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - isolate one bad test from the rest of the run
        return "error", f"test execution failed: {exc}", None


async def _package_for_test(
    session: AsyncSession,
    test: PolicyTest,
    package: ApprovedPolicyPackage,
) -> ApprovedPolicyPackage:
    """Restrict blind-batch execution to the reviewer-selected policy subset.

    Legacy/manual tests keep full-package behavior. Generated validation batches
    explicitly answer "how do these selected policies behave?", so unrelated
    rules must not make the package INDETERMINATE through facts the scenario was
    never intended to provide.
    """

    if test.generation_batch_id is None:
        return package
    batch = await PolicyTestBatchRepository(session).get_by_id(test.generation_batch_id)
    if batch is None:
        return package
    selected_ids = set(batch.selected_rule_ids_json or [])
    return package.model_copy(update={"rules": [rule for rule in package.rules if rule.rule_id in selected_ids]})


async def execute_test_by_id(
    session: AsyncSession,
    *,
    test_id: uuid.UUID,
    run_trigger: str,
    triggered_by: str,
    policy_version_id: uuid.UUID | None = None,
) -> PolicyTestRun:
    """Run one test on demand, against a specific version if given, else the
    policy set's currently active version. Used by the manual "Run now"
    endpoint. Raises `ValueError` (mapped to 404 by the router) if the test
    or a resolvable version cannot be found."""

    test_repo = PolicyTestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if test is None:
        raise ValueError(f"policy test '{test_id}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = (
        await version_repo.get_by_id(policy_version_id)
        if policy_version_id is not None
        else await version_repo.get_active_version(test.policy_set_id)
    )
    if version is None:
        raise ValueError("no approved policy version available to run this test against")
    if version.policy_set_id != test.policy_set_id:
        raise ValueError("selected policy version belongs to a different policy set")

    package = await _package_for_test(session, test, approved_policy_version_to_package(version))
    status, explanation, actual_response_json = _execute_single_test(test, package)
    expected_assertions = expectation_snapshot_for_test(test)
    committed_hash = test.expectation_hash or expectation_hash(expected_assertions)

    run_repo = PolicyTestRunRepository(session)
    return await run_repo.record(
        policy_test_id=test.id,
        policy_version_id=version.id,
        status=status,
        explanation=explanation,
        actual_response_json=actual_response_json,
        run_trigger=run_trigger,
        triggered_by=triggered_by,
        expected_assertions_json=expected_assertions,
        expectation_hash=committed_hash,
    )


async def run_active_tests_for_version(
    session: AsyncSession,
    *,
    policy_set_id: uuid.UUID,
    policy_version_id: uuid.UUID,
    run_trigger: str,
    triggered_by: str,
) -> list[PolicyTestRun]:
    """Re-run every active `PolicyTest` for `policy_set_id` against
    `policy_version_id` (Section 9.11 step 6). Called by
    `publish_approved_candidates` right after a new version is committed,
    and reusable for any future "re-run all" admin action. Each test is
    isolated via `_execute_single_test` so one misconfigured test can never
    abort the rest of the batch or the publish call that triggered it."""

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(policy_version_id)
    if version is None:
        raise ValueError(f"approved policy version '{policy_version_id}' not found")
    package = approved_policy_version_to_package(version)

    test_repo = PolicyTestRepository(session)
    tests = await test_repo.list_by_policy_set(policy_set_id, is_active=True)

    run_repo = PolicyTestRunRepository(session)
    runs: list[PolicyTestRun] = []
    for test in tests:
        test_package = await _package_for_test(session, test, package)
        status, explanation, actual_response_json = _execute_single_test(test, test_package)
        expected_assertions = expectation_snapshot_for_test(test)
        committed_hash = test.expectation_hash or expectation_hash(expected_assertions)
        run = await run_repo.record(
            policy_test_id=test.id,
            policy_version_id=version.id,
            status=status,
            explanation=explanation,
            actual_response_json=actual_response_json,
            run_trigger=run_trigger,
            triggered_by=triggered_by,
            expected_assertions_json=expected_assertions,
            expectation_hash=committed_hash,
        )
        runs.append(run)
    return runs
