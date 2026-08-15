"""Read the persisted policy each *published* rule was filed under.

The sibling of `provision_lookup`, for the other side of the review boundary.
That one reads the link off a candidate row; this one reads it off an approved
row. They are separate functions rather than one generic helper because the two
rows record the link differently, and the difference is the point:

* A candidate holds a foreign key to `document_provisions`. It is a live record
  and the provision it points at is a live row, so the link is resolved by
  identity every time it is read.
* An approved rule holds the provision's *key* and the heading chain, copied in
  at publish time. A published version is an immutable snapshot, and a snapshot
  that resolved its own grouping through a mutable join would not be one: the
  headings shown against a version published last year would change the day a
  document was re-read.

So the grouping of a published version comes out of the version itself, and the
only thing looked up here is the provision's identity — which is what the Explain
control needs a target for, and which cannot be snapshotted onto the rule without
duplicating a primary key into a second table.

A rule whose key resolves to no provision row is skipped rather than guessed at,
exactly as the candidate path skips one whose foreign key does not resolve. It
then falls through to `assemble`'s heading fallback, which is what keeps a rule
published before provisions existed grouped at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import ApprovedRule, DocumentProvision
from policy_platform.infrastructure.assembly.policy_assembly import ProvisionGrouping


async def approved_provision_groupings(
    session: AsyncSession,
    policy_set_id: uuid.UUID,
    rules: Sequence[ApprovedRule],
) -> dict[str, ProvisionGrouping]:
    """The policy each published rule was filed under, keyed by canonical rule id.

    Keyed by `rule_id` for the same reason the candidate path is: `assemble`
    works on canonical rules and never sees the row.

    One query for the whole version rather than one per rule. Scoped to the
    policy set so a key can only ever resolve to a provision of this project,
    which is a cheaper guarantee to state than to reason about later.
    """

    keys = {rule.provision_key for rule in rules if rule.provision_key}
    if not keys:
        return {}

    rows = (
        await session.execute(
            select(DocumentProvision.provision_key, DocumentProvision.id).where(
                DocumentProvision.policy_set_id == policy_set_id,
                DocumentProvision.provision_key.in_(keys),
            )
        )
    ).all()
    provision_ids = {key: str(provision_id) for key, provision_id in rows}

    groupings: dict[str, ProvisionGrouping] = {}
    for rule in rules:
        key = rule.provision_key
        if not key:
            continue
        provision_id = provision_ids.get(key)
        if provision_id is None:
            continue
        groupings[str(rule.rule_id)] = ProvisionGrouping(
            key=key,
            provision_id=provision_id,
            # The chain as it was when this version was published, verbatim.
            # Read off the snapshot and not off the provision row beside it:
            # the row is the current reading of the document and this is what
            # was published, and where they differ the published version is the
            # one this endpoint is describing.
            heading_path=tuple(rule.provision_heading_json or ()),
        )
    return groupings
