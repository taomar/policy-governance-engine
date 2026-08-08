"""Evaluation endpoint: the only HTTP entrypoint into the deterministic evaluator.

Per Rule 5.4, this router's only responsibility is to (1) look up the active
approved policy version, (2) hand it + the request facts to
`policy_platform.evaluator.engine.evaluate_policy`, and (3) persist an
append-only audit row. It must never call AI/Search/network itself, nor let
the evaluator do so.

This module also exposes the read-only "Decision Log" — the queryable browse
path over that same append-only `evaluations` table (ADR-0009's "Decision/audit
logging depth (OPA Decision Logs)... Adopt, incremental" item). Every call to
`evaluate` below already persists a full request/response pair; before this,
nothing could read it back short of a manual DB query. Deliberately read-only,
same posture as `audit.py`: a decision-log entry that could be edited or
deleted through the API would not be usable as evidence.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import EvaluationLogDetail, EvaluationLogSummary
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationResponse
from policy_platform.domain.models import Evaluation
from policy_platform.evaluator.engine import evaluate_policy
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    EvaluationRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

#: Same rationale as audit.py's _MAX_LIMIT: this table is append-only and never
#: pruned, so an unbounded query would be a way to hang the API by accident.
_MAX_LOG_LIMIT = 500


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


def _to_log_summary(row: Evaluation) -> EvaluationLogSummary:
    return EvaluationLogSummary(
        id=str(row.id),
        policy_set_id=str(row.policy_set_id),
        policy_version_id=str(row.policy_version_id),
        correlation_id=row.correlation_id,
        calling_system_identity=row.calling_system_identity,
        overall_status=row.overall_status,
        result_hash=row.result_hash,
        evaluation_timestamp=row.evaluation_timestamp,
    )


def _to_log_detail(row: Evaluation) -> EvaluationLogDetail:
    return EvaluationLogDetail(
        **_to_log_summary(row).model_dump(),
        request_facts=row.request_facts_json,
        response=row.response_json,
    )


@router.get("/policy-sets/{key}")
async def list_evaluation_log(
    key: str,
    overall_status: str | None = None,
    correlation_id: str | None = None,
    calling_system_identity: str | None = None,
    limit: int = Query(default=100, ge=1, le=_MAX_LOG_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The decision log: most recent evaluation calls first for one policy set.

    Every `POST /api/evaluations` call against this policy set is recorded
    here as immutable evidence — who called, what facts were given, what the
    engine decided, and a hash a caller can use to prove the result was not
    tampered with after the fact (OPA Decision-Log parity, ADR-0009).
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    rows = await EvaluationRepository(session).list_by_policy_set(
        policy_set.id,
        overall_status=overall_status,
        correlation_id=correlation_id,
        calling_system_identity=calling_system_identity,
        limit=limit,
    )
    return {
        "evaluations": [_to_log_summary(r) for r in rows],
        "count": len(rows),
        # Same "is there more" heuristic as audit.py — no second COUNT(*) over a
        # table that only ever grows.
        "truncated": len(rows) == limit,
    }


@router.get("/{evaluation_id}", response_model=EvaluationLogDetail)
async def get_evaluation_log_detail(
    evaluation_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> EvaluationLogDetail:
    """Full detail for one past decision, including the raw facts and response."""
    row = await EvaluationRepository(session).get_by_id(evaluation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"evaluation '{evaluation_id}' not found")
    return _to_log_detail(row)
