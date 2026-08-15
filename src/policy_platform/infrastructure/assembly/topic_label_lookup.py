"""Reading the generated subject names back, for a policy set.

The write direction lives in `assistants/provision_topic_label.py`, which calls
a model and stores what came back. This is the read direction and it calls
nothing: it loads rows and returns them.

They are kept apart for the reason `provision_lookup.py` gives about the same
relationship. A reader that can reach a writer eventually does, and then
displaying a queue costs seventy model calls that nobody asked for and that a
reviewer waits through. Assembly reads. Generation is asked for.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import DocumentProvision, ProvisionTopicLabel


@dataclass(frozen=True)
class StoredTopicLabel:
    """One provision's label, or the record of an attempt that produced none.

    `text` and `unavailable_code` are exclusive, the way the table's check
    constraint holds them. A caller that finds no entry at all is looking at a
    provision nobody has asked about, which is a different thing from one that
    was asked about and yielded nothing — and the interface says so differently.
    """

    text: str | None
    unavailable_code: str | None
    model_deployment: str | None
    prompt_version: str
    generated_at: datetime

    def as_payload(self) -> dict:
        """The shape the API hands to the interface.

        `generated` is stated on the payload rather than inferred at the far
        end, because the one property the reading side must never lose is that
        these words are ours. A field the interface has to derive is a field
        some future caller derives differently.
        """

        return {
            "generated": True,
            "text": self.text,
            "unavailable_code": self.unavailable_code,
            "model_deployment": self.model_deployment,
            "prompt_version": self.prompt_version,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


async def labels_for_policy_set(
    session: AsyncSession, policy_set_id: uuid.UUID
) -> dict[str, StoredTopicLabel]:
    """Every stored label for one policy set, keyed by provision key.

    Keyed by the provision key rather than the row id because that is the key
    the assembled policy already carries, so the interface joins on something it
    can see. A policy assembled without a persisted provision — the read-time
    fallback grouping — has no key here and correctly finds nothing, which
    displays as "no label has been generated" rather than as an error.

    One query. A per-card lookup would be seventy round trips to draw one page.
    """

    rows = (
        await session.execute(
            select(DocumentProvision.provision_key, ProvisionTopicLabel)
            .join(
                ProvisionTopicLabel,
                ProvisionTopicLabel.provision_id == DocumentProvision.id,
            )
            .where(DocumentProvision.policy_set_id == policy_set_id)
        )
    ).all()

    return {
        provision_key: StoredTopicLabel(
            text=label.label_text,
            unavailable_code=label.unavailable_code,
            model_deployment=label.model_deployment,
            prompt_version=label.prompt_version,
            generated_at=label.generated_at,
        )
        for provision_key, label in rows
    }
