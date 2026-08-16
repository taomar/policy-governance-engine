"""Flavour 2 endpoint — the lean, model-facing projection of one policy.

Kept in its own router rather than folded into `ai.py`, and deliberately off
the `/policies` path (the agent browser blocks that prefix), so both the SPA's
JSON tab and tooling can reach it. The tab fetches the lean flavour here instead
of rebuilding it client-side, which is what stops the two views of one policy
from drifting; the case-testing mechanism skips the HTTP hop and calls
`case_payload_for_provision` directly.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.projection.policy_case_payload import (
    case_payload_for_provision,
    to_compact,
    to_pretty,
)

router = APIRouter(prefix="/api/policy-payload", tags=["policy-payload"])


@router.get("/{provision_id}")
async def get_policy_case_payload(
    provision_id: str,
    pretty: bool = False,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """The lean payload for one provision (what the interface calls a policy).

    The body is the projection's own governed serialization, not FastAPI's
    re-encoding of the dict: the compact transport form is the exact bytes a
    model and the retrieval path consume, so the API emits those and nothing
    else. `?pretty=true` returns the indented diagnostic form for a human
    reading the response directly; both are produced deterministically from the
    same dict, so the transport bytes can never drift from what a reviewer sees.

    A provision that resolves to nothing is a 404. A provision that exists but
    currently carries no rules is a 200 with an empty `rules` list — "no such
    policy" and "a policy with nothing in it right now" are different answers
    and must not read alike.
    """

    try:
        pid = uuid.UUID(provision_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="provision_id must be a UUID.") from exc

    payload = await case_payload_for_provision(session, pid)
    if payload is None:
        raise HTTPException(status_code=404, detail="No provision with that id.")

    body = to_pretty(payload) if pretty else to_compact(payload)
    return Response(content=body, media_type="application/json")
