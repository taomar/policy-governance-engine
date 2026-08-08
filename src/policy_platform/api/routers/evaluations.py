"""Evaluation endpoint: the only HTTP entrypoint into the deterministic evaluator.

Per Rule 5.4, this router's only responsibility is to (1) look up the active
approved policy version, (2) hand it + the request facts to
`policy_platform.evaluator.engine.evaluate_policy`, and (3) persist an
append-only audit row. It must never call AI/Search/network itself, nor let
the evaluator do so.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationResponse
from policy_platform.evaluator.engine import evaluate_policy
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    EvaluationRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.post("", response_model=EvaluationResponse)
async def evaluate(
    request: EvaluationRequest, session: AsyncSession = Depends(get_session)
) -> EvaluationResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(request.policy_set_id)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{request.policy_set_id}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    if request.policy_version_id and not request.use_active_version:
        import uuid as _uuid

        version = await version_repo.get_by_id(_uuid.UUID(request.policy_version_id))
    else:
        version = await version_repo.get_active_version(policy_set.id)

    if version is None:
        raise HTTPException(
            status_code=404, detail=f"no approved policy version found for policy set '{request.policy_set_id}'"
        )

    package = approved_policy_version_to_package(version)
    response = evaluate_policy(package, request)

    evaluation_repo = EvaluationRepository(session)
    await evaluation_repo.record(
        policy_set_id=policy_set.id,
        policy_version_id=version.id,
        correlation_id=request.correlation_id,
        calling_system_identity=request.calling_system_identity,
        request_facts=request.facts,
        overall_status=response.overall_status.value,
        result_hash=response.result_hash,
        response_json=response.model_dump(mode="json"),
        evaluation_timestamp=response.evaluation_timestamp,
    )
    await session.commit()

    return response
