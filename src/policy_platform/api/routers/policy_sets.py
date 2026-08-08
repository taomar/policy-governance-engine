"""Policy-set and approved-version endpoints.

Version creation here is an explicit manual-import stand-in for the full
governance workflow (candidate extraction -> review -> approval), which is
deferred (see docs/known-limitations.md). It still enforces Rule 5.3
(insert-only, immutable approved versions) at the repository layer.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    AggregateLimitResponse,
    ApprovedPolicyVersionResponse,
    CreateAggregateLimitRequest,
    CreatePolicySetRequest,
    ImportPolicyVersionRequest,
    MarkPolicySetReviewedRequest,
    PolicySetResponse,
    UpdateAggregateLimitRequest,
    UpdatePolicySetRequest,
)
from policy_platform.contracts.policy import AggregateLimit, CanonicalRule
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.export import (
    ExportFormat,
    content_disposition,
    extension_for,
    media_type_for,
    models_to_export,
)
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.policy_version_import import import_approved_policy_version
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    PolicyAggregateLimitRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/policy-sets", tags=["policy-sets"])


def _to_response(ps) -> PolicySetResponse:
    return PolicySetResponse(
        id=str(ps.id),
        key=ps.key,
        name=ps.name,
        owner=ps.owner,
        description=ps.description,
        category=ps.category,
        tags=list(ps.tags_json or []),
        review_due_date=ps.review_due_date,
        last_reviewed_at=ps.last_reviewed_at,
        is_review_overdue=ps.review_due_date is not None and ps.review_due_date < date.today(),
        accountable_owner=ps.accountable_owner,
        delegate_approver=ps.delegate_approver,
        escalation_contact=ps.escalation_contact,
        consulted_parties=list(ps.consulted_parties_json or []),
        informed_parties=list(ps.informed_parties_json or []),
    )


def _aggregate_limit_to_response(row) -> AggregateLimitResponse:
    return AggregateLimitResponse(
        id=str(row.id),
        policy_set_id=str(row.policy_set_id),
        aggregate_key=row.aggregate_key,
        description=row.description,
        contributing_rules=list(row.contributing_rules_json or []),
        aggregator=row.aggregator,
        max_value=row.max_value,
        period=row.period,
    )


@router.get("", response_model=list[PolicySetResponse])
async def list_policy_sets(session: AsyncSession = Depends(get_session)) -> list[PolicySetResponse]:
    repo = PolicySetRepository(session)
    policy_sets = await repo.list_all()
    return [_to_response(ps) for ps in policy_sets]


@router.post("", response_model=PolicySetResponse, status_code=201)
async def create_policy_set(
    body: CreatePolicySetRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    if await repo.get_by_key(body.key) is not None:
        raise HTTPException(status_code=409, detail=f"policy set '{body.key}' already exists")
    policy_set = await repo.create(
        key=body.key,
        name=body.name,
        owner=body.owner,
        description=body.description,
        category=body.category,
        tags=body.tags,
        accountable_owner=body.accountable_owner,
        delegate_approver=body.delegate_approver,
        escalation_contact=body.escalation_contact,
        consulted_parties=body.consulted_parties,
        informed_parties=body.informed_parties,
    )
    await session.commit()
    return _to_response(policy_set)


@router.patch("/{key}", response_model=PolicySetResponse)
async def update_policy_set(
    key: str, body: UpdatePolicySetRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    policy_set = await repo.update_metadata(
        policy_set,
        name=body.name,
        description=body.description,
        category=body.category,
        tags=body.tags,
        review_due_date=body.review_due_date,
        clear_review_due_date=body.clear_review_due_date,
        accountable_owner=body.accountable_owner,
        delegate_approver=body.delegate_approver,
        escalation_contact=body.escalation_contact,
        consulted_parties=body.consulted_parties,
        informed_parties=body.informed_parties,
    )
    await session.commit()
    return _to_response(policy_set)


@router.post("/{key}/review", response_model=PolicySetResponse)
async def mark_policy_set_reviewed(
    key: str, body: MarkPolicySetReviewedRequest, session: AsyncSession = Depends(get_session)
) -> PolicySetResponse:
    """Attest that a human just reviewed this policy set (ISO 37301 §9.3).

    Stamps `last_reviewed_at` to now and, if `next_due_date` is supplied,
    advances `review_due_date` to the next cycle in the same call — so
    "reviewed today, next check in a year" is one request, not two.
    """
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    policy_set = await repo.mark_reviewed(policy_set, next_due_date=body.next_due_date)
    await session.commit()
    return _to_response(policy_set)


@router.get("/{key}", response_model=PolicySetResponse)
async def get_policy_set(key: str, session: AsyncSession = Depends(get_session)) -> PolicySetResponse:
    repo = PolicySetRepository(session)
    policy_set = await repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    return _to_response(policy_set)


@router.get("/{key}/versions", response_model=list[ApprovedPolicyVersionResponse])
async def list_policy_versions(
    key: str, session: AsyncSession = Depends(get_session)
) -> list[ApprovedPolicyVersionResponse]:
    """All versions of a policy set (active and superseded), newest first.

    Powers the admin UI's version-history timeline — distinct from
    `/active-version`, which only ever returns the single current version.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    versions = await version_repo.list_all_versions(policy_set.id)
    return [
        ApprovedPolicyVersionResponse(
            id=str(v.id),
            policy_set_id=str(v.policy_set_id),
            version_number=v.version_number,
            effective_from=v.effective_from,
            effective_to=v.effective_to,
            is_active=v.is_active,
            approved_by=v.approved_by,
            approved_at=v.approved_at,
            rule_count=len(v.rules),
        )
        for v in versions
    ]


@router.get("/{key}/versions/{version_id}/rules", response_model=list[CanonicalRule])
async def get_policy_version_rules(
    key: str, version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[CanonicalRule]:
    """Full canonical rule detail for one version — used to render readable rule cards.

    (`/versions` intentionally omits rule bodies to stay lightweight; this
    endpoint is the drill-down.)
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    return package.rules


@router.get("/{key}/versions/{version_id}/aggregate-limits", response_model=list[AggregateLimit])
async def get_policy_version_aggregate_limits(
    key: str, version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[AggregateLimit]:
    """Immutable aggregate limits snapshotted into this published version.

    Distinct from `/aggregate-limits` (this policy set's mutable *draft*
    definitions) — this is what was actually in effect as of this version,
    exactly like `/versions/{version_id}/rules` vs. the candidate-rule draft
    endpoints.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    return package.aggregate_limits


@router.get("/{key}/aggregate-limits", response_model=list[AggregateLimitResponse])
async def list_aggregate_limits(
    key: str, session: AsyncSession = Depends(get_session)
) -> list[AggregateLimitResponse]:
    """Mutable draft aggregate limits — the policy set's current desired state.

    Edited directly by a Policy Manager (no per-candidate review workflow),
    and snapshotted verbatim into `ApprovedAggregateLimit` at publish time.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    rows = await repo.list_by_policy_set(policy_set.id)
    return [_aggregate_limit_to_response(r) for r in rows]


@router.post("/{key}/aggregate-limits", response_model=AggregateLimitResponse, status_code=201)
async def create_aggregate_limit(
    key: str, body: CreateAggregateLimitRequest, session: AsyncSession = Depends(get_session)
) -> AggregateLimitResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    if await repo.get_by_key(policy_set.id, body.aggregate_key) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"aggregate limit '{body.aggregate_key}' already exists for policy set '{key}'",
        )
    row = await repo.create(
        policy_set_id=policy_set.id,
        aggregate_key=body.aggregate_key,
        description=body.description,
        contributing_rules=[c.model_dump(mode="json") for c in body.contributing_rules],
        aggregator=body.aggregator,
        max_value=body.max_value,
        period=body.period,
    )
    await session.commit()
    return _aggregate_limit_to_response(row)


@router.put("/{key}/aggregate-limits/{aggregate_key}", response_model=AggregateLimitResponse)
async def update_aggregate_limit(
    key: str,
    aggregate_key: str,
    body: UpdateAggregateLimitRequest,
    session: AsyncSession = Depends(get_session),
) -> AggregateLimitResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    row = await repo.get_by_key(policy_set.id, aggregate_key)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"aggregate limit '{aggregate_key}' not found for policy set '{key}'"
        )
    row = await repo.update(
        row,
        description=body.description,
        contributing_rules=[c.model_dump(mode="json") for c in body.contributing_rules],
        aggregator=body.aggregator,
        max_value=body.max_value,
        period=body.period,
    )
    await session.commit()
    return _aggregate_limit_to_response(row)


@router.delete("/{key}/aggregate-limits/{aggregate_key}", status_code=204)
async def delete_aggregate_limit(
    key: str, aggregate_key: str, session: AsyncSession = Depends(get_session)
) -> Response:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    repo = PolicyAggregateLimitRepository(session)
    row = await repo.get_by_key(policy_set.id, aggregate_key)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"aggregate limit '{aggregate_key}' not found for policy set '{key}'"
        )
    await repo.delete(row)
    await session.commit()
    return Response(status_code=204)


@router.get("/{key}/versions/{version_id}/export")
async def export_policy_version_rules(
    key: str,
    version_id: uuid.UUID,
    format: ExportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download every rule in one approved version as JSON, JSONL, or CSV.

    Verbatim structural export: no rule field is reworded or summarized,
    only re-serialized — safe for audit/archival use or hand-off to another
    system.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"version '{version_id}' not found")

    package = approved_policy_version_to_package(version)
    content = models_to_export(package.rules, format)
    filename = f"{key}-v{version.version_number}-rules.{extension_for(format)}"
    return Response(
        content=content, media_type=media_type_for(format), headers=content_disposition(filename)
    )


@router.post(
    "/{key}/versions",
    response_model=ApprovedPolicyVersionResponse,
    status_code=201,
)
async def import_policy_version(
    key: str, body: ImportPolicyVersionRequest, session: AsyncSession = Depends(get_session)
) -> ApprovedPolicyVersionResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version = await import_approved_policy_version(
        session,
        policy_set_id=policy_set.id,
        version_number=body.version_number,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        approved_by=body.approved_by,
        is_active=body.is_active,
        rules=body.rules,
        aggregate_limits=body.aggregate_limits,
    )
    await session.commit()
    return ApprovedPolicyVersionResponse(
        id=str(version.id),
        policy_set_id=str(version.policy_set_id),
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        is_active=version.is_active,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rule_count=len(body.rules),
    )


@router.get("/{key}/active-version", response_model=ApprovedPolicyVersionResponse)
async def get_active_version(key: str, session: AsyncSession = Depends(get_session)) -> ApprovedPolicyVersionResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_active_version(policy_set.id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"no active approved version for policy set '{key}'")

    return ApprovedPolicyVersionResponse(
        id=str(version.id),
        policy_set_id=str(version.policy_set_id),
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        is_active=version.is_active,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rule_count=len(version.rules),
    )
