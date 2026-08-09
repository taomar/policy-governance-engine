"""PolicyTest / PolicyTestRun endpoints (Section 21.6 / 11.6 / 9.11 step 6).

Named, saved test cases for a policy set — distinct from the ad hoc
`/api/evaluations` simulation endpoint (see evaluations.py). AI may propose
tests via `/propose`, but every test is actually executed by the real
deterministic evaluator (`infrastructure/policy_test_execution.py`), never
by AI. Follows the same error-handling convention as `ai.py`:
`_require_ai_configured()` gate + 503 for AI-unavailable, 404 for
not-found, 422 for validation errors.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    CreatePolicyTestRequest,
    GeneratePolicyValidationBatchRequest,
    PolicyTestListItemResponse,
    PolicyTestResponse,
    PolicyTestReviewRequest,
    PolicyTestRunResponse,
    PolicyTestBatchResponse,
    ProposePolicyTestsRequest,
    ProposePolicyTestsResponse,
    RunPolicyTestRequest,
    RunPolicyValidationBatchRequest,
)
from policy_platform.domain.models import PolicyTest, PolicyTestBatch, PolicyTestRun
from policy_platform.infrastructure import ai_test_proposal
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.policy_test_execution import execute_test_by_id
from policy_platform.infrastructure.policy_test_commitment import build_expectation_snapshot, expectation_hash
from policy_platform.infrastructure.repositories import (
    PolicySetRepository,
    PolicyTestRepository,
    PolicyTestBatchRepository,
    PolicyTestRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

router = APIRouter(prefix="/api/policy-tests", tags=["policy-tests"])


def _require_ai_configured() -> None:
    if not get_settings().ai_enabled:
        raise HTTPException(status_code=503, detail="Azure OpenAI is not configured on this server")


def _test_to_response(test: PolicyTest, *, reveal_expectations: bool = True) -> PolicyTestResponse:
    return PolicyTestResponse(
        id=str(test.id),
        policy_set_id=str(test.policy_set_id),
        name=test.name,
        description=test.description,
        test_kind=test.test_kind,
        input_facts=test.input_facts_json or {},
        evaluation_timestamp=test.evaluation_timestamp_override,
        scenario_text=test.scenario_text,
        generation_batch_id=str(test.generation_batch_id) if test.generation_batch_id else None,
        expectation_hash=test.expectation_hash,
        expectation_revealed=reveal_expectations,
        expected_overall_status=test.expected_overall_status if reveal_expectations else None,
        expected_rule_id=test.expected_rule_id,
        expected_rule_status=test.expected_rule_status if reveal_expectations else None,
        expected_missing_facts=test.expected_missing_facts_json if reveal_expectations else None,
        proposed_by=test.proposed_by,
        review_status=test.review_status,
        reviewed_by=test.reviewed_by,
        reviewed_at=test.reviewed_at,
        review_notes=test.review_notes,
        is_active=test.is_active,
        created_at=test.created_at,
    )


def _run_to_response(run: PolicyTestRun) -> PolicyTestRunResponse:
    return PolicyTestRunResponse(
        id=str(run.id),
        policy_test_id=str(run.policy_test_id),
        policy_version_id=str(run.policy_version_id),
        status=run.status,
        explanation=run.explanation,
        actual_response_json=run.actual_response_json,
        expected_assertions_json=run.expected_assertions_json,
        expectation_hash=run.expectation_hash,
        run_trigger=run.run_trigger,
        triggered_by=run.triggered_by,
        run_at=run.run_at,
    )


async def _batch_to_response(
    session: AsyncSession,
    batch: PolicyTestBatch,
) -> PolicyTestBatchResponse:
    test_repo = PolicyTestRepository(session)
    tests = await test_repo.list_by_batch(batch.id)
    latest_runs = await PolicyTestRunRepository(session).get_latest_for_tests([test.id for test in tests])
    run_history = await PolicyTestRunRepository(session).list_for_tests([test.id for test in tests])
    reveal = batch.status == "executed"
    return PolicyTestBatchResponse(
        id=str(batch.id),
        policy_set_id=str(batch.policy_set_id),
        policy_version_id=str(batch.policy_version_id),
        version_number=batch.policy_version.version_number,
        grounding_mode=batch.grounding_mode,
        selected_rule_ids=list(batch.selected_rule_ids_json or []),
        grounding_context=batch.grounding_context_json or {},
        scenario_count=batch.scenario_count,
        tests_per_policy=(
            batch.scenario_count // len(batch.selected_rule_ids_json)
            if batch.selected_rule_ids_json
            and batch.scenario_count % len(batch.selected_rule_ids_json) == 0
            else batch.scenario_count
        ),
        reasoning_effort=batch.reasoning_effort,
        guidance=batch.guidance,
        created_by=batch.created_by,
        status=batch.status,
        executed_at=batch.executed_at,
        created_at=batch.created_at,
        tests=[
            PolicyTestListItemResponse(
                test=_test_to_response(test, reveal_expectations=reveal or test.id in latest_runs),
                latest_run=_run_to_response(latest_runs[test.id]) if test.id in latest_runs else None,
                runs=[_run_to_response(run) for run in run_history.get(test.id, [])],
            )
            for test in tests
        ],
    )


async def _require_policy_set(session: AsyncSession, key: str):
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    return policy_set


@router.get("/policy-sets/{key}", response_model=list[PolicyTestListItemResponse])
async def list_policy_tests(
    key: str,
    is_active: bool | None = None,
    test_kind: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PolicyTestListItemResponse]:
    policy_set = await _require_policy_set(session, key)
    test_repo = PolicyTestRepository(session)
    tests = await test_repo.list_by_policy_set(policy_set.id, is_active=is_active, test_kind=test_kind)

    latest_runs = await PolicyTestRunRepository(session).get_latest_for_tests([t.id for t in tests])
    return [
        PolicyTestListItemResponse(
            test=_test_to_response(t, reveal_expectations=t.generation_batch_id is None or t.id in latest_runs),
            latest_run=_run_to_response(latest_runs[t.id]) if t.id in latest_runs else None,
        )
        for t in tests
    ]


@router.get("/policy-sets/{key}/failing", response_model=list[PolicyTestListItemResponse])
async def list_failing_policy_tests(
    key: str, session: AsyncSession = Depends(get_session)
) -> list[PolicyTestListItemResponse]:
    """Active tests whose most recent run did not pass — the data source for
    the Findings/Quality page's "Failed policy tests" section (Section 9.9).
    A test that has never been run is excluded: it is "unverified", not
    "failing", and surfacing it here would be misleading.
    """
    policy_set = await _require_policy_set(session, key)
    test_repo = PolicyTestRepository(session)
    tests = await test_repo.list_by_policy_set(policy_set.id, is_active=True)

    latest_runs = await PolicyTestRunRepository(session).get_latest_for_tests([t.id for t in tests])
    return [
        PolicyTestListItemResponse(test=_test_to_response(t), latest_run=_run_to_response(latest_runs[t.id]))
        for t in tests
        if t.id in latest_runs and latest_runs[t.id].status != "pass"
    ]


@router.post("/policy-sets/{key}", response_model=PolicyTestResponse, status_code=201)
async def create_policy_test(
    key: str, body: CreatePolicyTestRequest, session: AsyncSession = Depends(get_session)
) -> PolicyTestResponse:
    policy_set = await _require_policy_set(session, key)
    test_repo = PolicyTestRepository(session)
    test = await test_repo.create(
        policy_set_id=policy_set.id,
        name=body.name,
        description=body.description,
        test_kind=body.test_kind,
        input_facts_json=body.input_facts,
        evaluation_timestamp_override=body.evaluation_timestamp,
        expected_overall_status=body.expected_overall_status,
        expected_rule_id=body.expected_rule_id,
        expected_rule_status=body.expected_rule_status,
        expected_missing_facts_json=body.expected_missing_facts,
        # Human-authored tests skip AI review entirely — a human is already
        # directly asserting the expectation (see schemas.CreatePolicyTestRequest).
        proposed_by="human",
        review_status="active",
        is_active=True,
    )
    await session.commit()
    return _test_to_response(test)


@router.post("/policy-sets/{key}/propose", response_model=ProposePolicyTestsResponse)
async def propose_policy_tests(
    key: str, body: ProposePolicyTestsRequest, session: AsyncSession = Depends(get_session)
) -> ProposePolicyTestsResponse:
    """AI proposes candidate tests (Section 11.6's "Policy Test Proposal
    Agent"). Proposals are persisted immediately so they show up in the
    review queue, but with review_status="pending_review" and
    is_active=False — they cannot run on-publish or count as a Finding
    until a human accepts them via `/{{test_id}}/review`.
    """
    _require_ai_configured()
    await _require_policy_set(session, key)
    try:
        result = await ai_test_proposal.propose_policy_tests(
            session, policy_set_key=key, reasoning_effort=body.reasoning_effort, guidance=body.guidance
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    policy_set = await _require_policy_set(session, key)
    test_repo = PolicyTestRepository(session)
    created: list[PolicyTest] = []
    for payload in result["proposed_tests"]:
        test = await test_repo.create(
            policy_set_id=policy_set.id,
            proposed_by="ai",
            review_status="pending_review",
            is_active=False,
            **payload,
        )
        created.append(test)
    await session.commit()

    return ProposePolicyTestsResponse(
        policy_set_key=key,
        version_number=result["version_number"],
        reasoning_effort=result["reasoning_effort"],
        proposed_tests=[_test_to_response(t) for t in created],
        skipped=result["skipped"],
    )


@router.post(
    "/policy-sets/{key}/validation-batches",
    response_model=PolicyTestBatchResponse,
    status_code=201,
)
async def generate_validation_batch(
    key: str,
    body: GeneratePolicyValidationBatchRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyTestBatchResponse:
    """Generate a selected-rule blind validation set with committed expectations."""

    _require_ai_configured()
    if body.tests_per_policy == 0:
        raise HTTPException(status_code=422, detail="Set tests per policy to at least 1 before generating.")
    policy_set = await _require_policy_set(session, key)
    try:
        result = await ai_test_proposal.propose_policy_tests(
            session,
            policy_set_key=key,
            reasoning_effort=body.reasoning_effort,
            guidance=body.guidance,
            rule_ids=body.rule_ids,
            tests_per_policy=body.tests_per_policy,
            grounding_mode=body.grounding_mode,
            policy_version_id=body.policy_version_id,
            user_scenario=body.scenario_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    proposals = result["proposed_tests"]
    expected_total = body.tests_per_policy * len(body.rule_ids)
    counts_by_rule = {
        rule_id: sum(1 for proposal in proposals if proposal["expected_rule_id"] == rule_id)
        for rule_id in body.rule_ids
    }
    invalid_counts = {
        rule_id: count for rule_id, count in counts_by_rule.items() if count != body.tests_per_policy
    }
    if len(proposals) != expected_total or invalid_counts:
        raise HTTPException(
            status_code=422,
            detail=(
                f"AI generated {len(proposals)} valid scenario(s), but this batch requires "
                f"{body.tests_per_policy} per selected policy ({expected_total} total). "
                f"Per-policy counts: {counts_by_rule}. Refine the selection/guidance and try again."
            ),
        )

    batch = await PolicyTestBatchRepository(session).create(
        policy_set_id=policy_set.id,
        policy_version_id=uuid.UUID(result["policy_version_id"]),
        grounding_mode=body.grounding_mode,
        selected_rule_ids_json=result["selected_rule_ids"],
        grounding_context_json=result["grounding_context"],
        scenario_count=expected_total,
        reasoning_effort=body.reasoning_effort,
        guidance=body.guidance,
        created_by=body.created_by,
    )
    test_repo = PolicyTestRepository(session)
    for payload in proposals:
        snapshot = build_expectation_snapshot(
            scenario_text=payload["scenario_text"],
            input_facts=payload["input_facts_json"],
            evaluation_timestamp=payload["evaluation_timestamp_override"],
            expected_overall_status=payload["expected_overall_status"],
            expected_rule_id=payload["expected_rule_id"],
            expected_rule_status=payload["expected_rule_status"],
            expected_missing_facts=payload["expected_missing_facts_json"],
        )
        await test_repo.create(
            policy_set_id=policy_set.id,
            proposed_by="ai",
            review_status="pending_review",
            is_active=False,
            generation_batch_id=batch.id,
            scenario_text=payload.pop("scenario_text"),
            expectation_hash=expectation_hash(snapshot),
            **payload,
        )
    await session.commit()
    await session.refresh(batch, attribute_names=["policy_version"])
    return await _batch_to_response(session, batch)


@router.get("/policy-sets/{key}/validation-batches", response_model=list[PolicyTestBatchResponse])
async def list_validation_batches(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> list[PolicyTestBatchResponse]:
    policy_set = await _require_policy_set(session, key)
    batches = await PolicyTestBatchRepository(session).list_by_policy_set(policy_set.id)
    for batch in batches:
        await session.refresh(batch, attribute_names=["policy_version"])
    return [await _batch_to_response(session, batch) for batch in batches]


@router.post("/validation-batches/{batch_id}/run", response_model=PolicyTestBatchResponse)
async def run_validation_batch(
    batch_id: uuid.UUID,
    body: RunPolicyValidationBatchRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyTestBatchResponse:
    batch_repo = PolicyTestBatchRepository(session)
    batch = await batch_repo.get_by_id(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"validation batch '{batch_id}' not found")
    tests = await PolicyTestRepository(session).list_by_batch(batch.id)
    for test in tests:
        await execute_test_by_id(
            session,
            test_id=test.id,
            run_trigger="manual",
            triggered_by=body.triggered_by,
            policy_version_id=uuid.UUID(body.policy_version_id) if body.policy_version_id else batch.policy_version_id,
        )
    await batch_repo.mark_executed(batch)
    await session.commit()
    await session.refresh(batch, attribute_names=["policy_version"])
    return await _batch_to_response(session, batch)


@router.post("/{test_id}/review", response_model=PolicyTestResponse)
async def review_policy_test(
    test_id: uuid.UUID, body: PolicyTestReviewRequest, session: AsyncSession = Depends(get_session)
) -> PolicyTestResponse:
    """Accept or reject an AI-proposed test. Accepting flips it to
    review_status="active"/is_active=True so it joins the on-publish
    auto-rerun and the Findings view; rejecting keeps the row (never
    deleted, for history) with review_status="rejected"/is_active=False.
    """
    test_repo = PolicyTestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"policy test '{test_id}' not found")

    if body.decision == "accept":
        updated = await test_repo.set_review_status(
            test, review_status="active", is_active=True, reviewed_by=body.reviewer, review_notes=body.notes
        )
    else:
        updated = await test_repo.set_review_status(
            test, review_status="rejected", is_active=False, reviewed_by=body.reviewer, review_notes=body.notes
        )
    await session.commit()
    return _test_to_response(updated)


@router.post("/{test_id}/run", response_model=PolicyTestRunResponse)
async def run_policy_test_now(
    test_id: uuid.UUID, body: RunPolicyTestRequest, session: AsyncSession = Depends(get_session)
) -> PolicyTestRunResponse:
    try:
        run = await execute_test_by_id(
            session,
            test_id=test_id,
            run_trigger="manual",
            triggered_by=body.triggered_by,
            policy_version_id=uuid.UUID(body.policy_version_id) if body.policy_version_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return _run_to_response(run)


@router.get("/{test_id}/runs", response_model=list[PolicyTestRunResponse])
async def list_policy_test_runs(
    test_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[PolicyTestRunResponse]:
    test_repo = PolicyTestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"policy test '{test_id}' not found")
    runs = await PolicyTestRunRepository(session).list_by_test(test_id)
    return [_run_to_response(r) for r in runs]
