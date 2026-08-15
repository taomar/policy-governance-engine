"""Read the persisted policy each candidate rule was filed under.

Separate from `policy_assembly` so that module stays a pure function of the
rules it is handed: assembly is the part with the invariants worth testing
exhaustively, and a test of it should not need a database.

Separate from `extraction.provision_linking` because these are opposite
directions of the same relationship. Linking decides, once, which provision
states a rule and writes it down; this reads what was written. Putting both in
one module would make it easy to reach for the writer from a read path, which is
how a read-time grouping becomes a read-time *write*.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, DocumentProvision
from policy_platform.infrastructure.assembly.policy_assembly import ProvisionGrouping


async def provision_groupings(
    session: AsyncSession, candidates: Sequence[CandidateRule]
) -> dict[str, ProvisionGrouping]:
    """The policy each candidate was filed under, keyed by canonical rule id.

    Keyed by `rule_id` rather than by the row's UUID because `assemble` works on
    canonical rules and never sees the row.

    One query for the whole page rather than one per rule: a review queue holds
    thousands, and a per-rule lookup would make the policy view slower than the
    flat list it exists to improve on.

    A candidate whose `provision_id` points at a row this query did not return
    is skipped rather than guessed at, and falls through to the heading
    fallback. That cannot happen while the foreign key holds; it is handled
    because the alternative is a KeyError in a read path a reviewer depends on.
    """

    provision_ids = {
        candidate.provision_id
        for candidate in candidates
        if candidate.provision_id is not None
    }
    if not provision_ids:
        return {}

    rows = (
        await session.execute(
            select(DocumentProvision).where(DocumentProvision.id.in_(provision_ids))
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}

    groupings: dict[str, ProvisionGrouping] = {}
    for candidate in candidates:
        row = by_id.get(candidate.provision_id)
        if row is None:
            continue
        rule_id = (candidate.payload_json or {}).get("rule_id")
        if not rule_id:
            continue
        groupings[str(rule_id)] = ProvisionGrouping(
            key=row.provision_key,
            heading_path=tuple(row.heading_path_json or ()),
        )
    return groupings
