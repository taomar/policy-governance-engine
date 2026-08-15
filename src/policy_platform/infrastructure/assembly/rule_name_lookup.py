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

from policy_platform.domain.models import CandidateRuleName


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
