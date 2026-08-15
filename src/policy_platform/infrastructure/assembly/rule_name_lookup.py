"""Reading generated rule handles back, by the rules they describe.

The write direction lives in `assistants/rule_namer.py`, which calls a model and
stores what came back. This is the read direction and it calls nothing: it loads
rows and returns them. They are kept apart for the reason `topic_label_lookup`
gives — a reader that can reach a writer eventually does, and then drawing a
queue costs model calls nobody asked for.

WHY THIS IS NOT PART OF POLICY ASSEMBLY

The generated subject label is served on the assembled policy, because it is
shown with the policy's heading and is about the policy. A rule handle is *not*
served on a rule, and that is the point of the whole feature: a rule's record is
evidence about a document, and our commentary must not be able to travel inside
it into an export or a published version. So this module is asked directly, by
rule id, by a caller that wants handles and knows it is asking for ours. Nothing
that assembles, exports or publishes a rule imports it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, CandidateRuleName


@dataclass(frozen=True)
class StoredRuleName:
    """One rule's handle, or the record of an attempt that produced none.

    `text` and `unavailable_code` are exclusive, the way the table's check
    constraint holds them. A caller that finds no entry at all is looking at a
    rule nobody has asked about, which is a different thing again.
    """

    text: str | None
    unavailable_code: str | None
    model_deployment: str | None
    prompt_version: str
    generated_at: datetime

    def as_payload(self) -> dict:
        """The shape the API hands to the interface.

        `generated` is stated here rather than inferred at the far end, because
        the one property this must never lose is that these words are ours and
        not the document's.
        """

        return {
            "generated": True,
            "text": self.text,
            "unavailable_code": self.unavailable_code,
            "model_deployment": self.model_deployment,
            "prompt_version": self.prompt_version,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


async def names_for_rules(
    session: AsyncSession, candidate_rule_ids: Sequence[uuid.UUID]
) -> dict[str, StoredRuleName]:
    """Stored handles for the rules asked about, keyed by rule id as a string.

    One query for the whole page: a per-rule lookup would be dozens of round
    trips to draw one card. Rules with no stored handle are absent from the
    result rather than present as a null, so "nobody has asked" stays a
    different answer from "asked, and nothing usable came back".
    """

    if not candidate_rule_ids:
        return {}

    rows = (
        await session.execute(
            select(CandidateRuleName).where(
                CandidateRuleName.candidate_rule_id.in_(list(candidate_rule_ids))
            )
        )
    ).scalars()

    return {
        str(row.candidate_rule_id): StoredRuleName(
            text=row.name_text,
            unavailable_code=row.unavailable_code,
            model_deployment=row.model_deployment,
            prompt_version=row.prompt_version,
            generated_at=row.generated_at,
        )
        for row in rows
    }


async def names_for_canonical_rules(
    session: AsyncSession,
    *,
    policy_set_id: uuid.UUID,
    rule_ids: Sequence[str],
) -> dict[str, StoredRuleName]:
    """Stored handles for rules named by their own identifier, within one set.

    WHY A SECOND WAY IN

    The handle is stored against the draft row it was generated from, because
    that is the row naming ran over. A published version holds no draft row —
    the rule *is* the record — so a reader of a published policy has no id to
    ask with. Without this it sees no handles at all, which is a difference
    between two surfaces showing the same rules, and a difference nobody chose.

    WHY IT IS SCOPED TO A POLICY SET

    A canonical rule id records where a rule was found in its document. Two
    documents can therefore state the same one about entirely different rules,
    and an unscoped lookup would hand back a handle written about somebody
    else's rule — words attached to a record they were never about, which is
    the exact failure the whole feature is arranged to prevent. So the set is
    required rather than optional, and the join carries it.

    WHEN SEVERAL ROWS SHARE ONE RULE ID

    Re-extraction produces a fresh draft row for the same rule, and naming may
    have run over more than one of them. The most recently generated handle
    wins. It is picked by time rather than by run, because one run is not
    ordered against another, and picking arbitrarily would let the same rule
    show two different handles on two page loads with nothing changed.
    """

    if not rule_ids:
        return {}

    rows = (
        await session.execute(
            select(CandidateRule.payload_json["rule_id"].astext, CandidateRuleName)
            .join(CandidateRuleName, CandidateRuleName.candidate_rule_id == CandidateRule.id)
            .where(
                CandidateRule.policy_set_id == policy_set_id,
                CandidateRule.payload_json["rule_id"].astext.in_(list(rule_ids)),
            )
            .order_by(CandidateRuleName.generated_at.asc())
        )
    ).all()

    # Ascending, so a later row overwrites an earlier one and the newest handle
    # is what survives. One pass, and no comparison written out by hand.
    return {
        rule_id: StoredRuleName(
            text=row.name_text,
            unavailable_code=row.unavailable_code,
            model_deployment=row.model_deployment,
            prompt_version=row.prompt_version,
            generated_at=row.generated_at,
        )
        for rule_id, row in rows
        if rule_id
    }
