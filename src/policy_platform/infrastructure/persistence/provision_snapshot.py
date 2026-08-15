"""Which policy an approved rule was published under, frozen at publish time.

WHY A SNAPSHOT AND NOT A FOREIGN KEY

`ApprovedPolicyVersion` is an immutable record of what a human approved on a
day. It already copies `formulation_json`, `condition_json` and `lineage_json`
out of the candidate rather than pointing at it, for the reason migration
`e4c7a2b8d190` gives: a published version that reads its content through a
live foreign key is a published version that changes when the draft side
changes, and then nobody can say what was approved.

The policy a rule belongs to is content in exactly that sense. A reviewer who
approved fourteen rules as `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES
SPONSORSHIP` approved them under that name; re-running extraction against a
corrected parse could produce a differently-bounded provision with a different
key, and the published version must still say what the reviewer saw. So the
key and the heading chain are copied, and `document_provisions` is free to be
rebuilt without touching a single published row.

WHY THE HEADING CHAIN IS COPIED TOO AND NOT JUST THE KEY

The key is a digest. A published version holding only digests can be grouped
but cannot be read: an auditor opening it a year later would have a policy
called `a7b3cc4423…`. The headings are the document's own words and are what
makes the group legible, so they travel with it.

WHAT THIS DOES NOT DO

It does not decide grouping. Every value here was decided by the pipeline and
is being carried, not recomputed — a second opinion on which policy a rule
belongs to could disagree with the first, silently, in the one place that is
supposed to be a permanent record.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    ApprovedRule,
    CandidateRule,
    DocumentProvision,
)


@dataclass(frozen=True)
class ProvisionSnapshot:
    """The policy a rule was published under, as text and key."""

    #: The provision's stable key. Grouping a published version reads this.
    key: str
    #: The governing headings, outermost first, each verbatim as the document
    #: wrote it. A list and never a joined path: a separator would be a
    #: character this system put between two of the document's own headings.
    heading_path: list[str]


async def snapshots_for_candidates(
    session: AsyncSession,
    candidates: Sequence[CandidateRule],
) -> dict[str, ProvisionSnapshot]:
    """The provision of each candidate, keyed by `rule_id`.

    A candidate the pipeline could not file under a provision is absent rather
    than present with a null: a document whose structure defeats grouping must
    still publish, and an absent key says "not grouped" where an empty one
    would claim a policy named nothing.
    """

    wanted: set[uuid.UUID] = {
        candidate.provision_id for candidate in candidates if candidate.provision_id is not None
    }
    if not wanted:
        return {}

    rows = (
        await session.execute(
            select(DocumentProvision).where(DocumentProvision.id.in_(wanted))
        )
    ).scalars()
    by_id = {row.id: row for row in rows}

    snapshots: dict[str, ProvisionSnapshot] = {}
    for candidate in candidates:
        provision = by_id.get(candidate.provision_id) if candidate.provision_id else None
        if provision is None:
            continue
        rule_id = (candidate.payload_json or {}).get("rule_id")
        if not rule_id:
            continue
        snapshots[str(rule_id)] = ProvisionSnapshot(
            key=provision.provision_key,
            heading_path=list(provision.heading_path_json or []),
        )
    return snapshots


def snapshots_carried_forward(rules: Sequence[ApprovedRule]) -> dict[str, ProvisionSnapshot]:
    """The provision each already-published rule was published under.

    Publishing carries every rule of the active version forward, so a rule that
    is not part of this batch must keep the policy it was approved under. Left
    out, a rule would silently lose its policy on the next unrelated publish —
    the same "fewer records than they started with" failure that an
    irreversible reduction produced once already, arriving one version at a
    time instead of all at once.
    """

    carried: dict[str, ProvisionSnapshot] = {}
    for rule in rules:
        if not rule.provision_key:
            continue
        carried[rule.rule_id] = ProvisionSnapshot(
            key=rule.provision_key,
            heading_path=list(rule.provision_heading_json or []),
        )
    return carried
