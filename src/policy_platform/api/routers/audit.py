"""Read access to the audit trail.

The trail is written by `infrastructure/persistence/audit.py` from the endpoints that take
authoritative action. This router is deliberately read-only: an audit record
that can be edited or deleted through the API is not evidence of anything, so
there is no POST, PUT or DELETE here and there should not be one.

Filtering is by the same polymorphic pair the table is keyed on
(`entity_type` + `entity_id`) plus `event_type`, because the two questions a
governance reviewer actually asks are "what happened to this rule?" and "show
me every approval". Filters are optional and combine with AND; the unfiltered
call returns the most recent activity across the whole platform, which is the
useful default for a small team.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import AuditEvent
from policy_platform.infrastructure.persistence.db import get_session

router = APIRouter(prefix="/api/audit-events", tags=["audit"])

#: Hard ceiling on one page. The trail grows without bound — it is never
#: pruned, by design — so an unbounded query would eventually be a way to hang
#: the API by accident.
_MAX_LIMIT = 500


def _to_response(event: AuditEvent) -> dict:
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "actor": event.actor,
        "details": event.details_json or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@router.get("")
async def list_audit_events(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    event_type: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Most recent audit events first, optionally narrowed to one entity."""

    query = select(AuditEvent)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if actor:
        query = query.where(AuditEvent.actor == actor)

    result = await session.execute(query.order_by(desc(AuditEvent.created_at)).limit(limit))
    events = list(result.scalars())

    return {
        "events": [_to_response(e) for e in events],
        "count": len(events),
        # Says "there is more" without a second count(*) over a table that only
        # ever grows: a full page is the signal to narrow the filters.
        "truncated": len(events) == limit,
    }
