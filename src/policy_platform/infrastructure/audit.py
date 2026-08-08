"""Recording of authoritative governance actions to the audit trail.

`AuditEvent` existed as a table, a model and an export before anything wrote to
it, which is worse than not having it at all: a reader — or an auditor — sees
"immutable audit trail record for authoritative actions (approvals,
publications, etc.)" and reasonably concludes approvals are audited. They were
not.

This module is the single writer. It exists as a function rather than as
inline `session.add(AuditEvent(...))` calls at each endpoint so that the shape
of an audit record is decided in one place: if every caller invents its own
`event_type` spelling and its own `details_json` keys, the trail is
unqueryable, which defeats the point of keeping it.

Two deliberate constraints:

* The event is added to the *caller's* session and not committed here. An audit
  record must land in the same transaction as the action it describes, or a
  failure between the two produces either an action nobody can account for or a
  record of something that never happened.
* `actor` is required and must be non-empty. An unattributed approval is not an
  audit record; it is a rumour.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import AuditEvent

#: Event types currently emitted. Kept as a module constant so the vocabulary is
#: greppable and new call sites are pushed toward reusing an existing name
#: rather than coining a synonym.
CANDIDATE_REVIEWED = "candidate_rule.reviewed"
CANDIDATE_REVIEW_OVERRIDDEN = "candidate_rule.review_overridden"
CANDIDATES_BULK_REVIEWED = "candidate_rule.bulk_reviewed"
CANDIDATES_PUBLISHED = "policy_version.published"
FINDING_DISPOSED = "correlation_finding.disposed"


def record_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor: str,
    details: dict | None = None,
) -> AuditEvent:
    """Stage an audit record in the caller's transaction.

    Raises ValueError for a blank actor rather than storing an anonymous
    record, because a governance trail that cannot say who acted answers none
    of the questions it is kept to answer.
    """

    if not actor or not actor.strip():
        raise ValueError(f"audit event '{event_type}' requires an actor")

    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor.strip(),
        details_json=details or {},
    )
    session.add(event)
    return event
