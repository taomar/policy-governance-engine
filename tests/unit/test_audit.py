"""Tests for the audit-trail writer.

The point under test is not "does a row get added" but the two rules that make
the trail trustworthy: it must refuse to record an action nobody is accountable
for, and it must not commit on its own, so an audit record can never outlive
the transaction that produced the action it describes.
"""

from __future__ import annotations

import uuid

import pytest

from policy_platform.infrastructure.persistence.audit import (
    CANDIDATE_REVIEWED,
    record_audit_event,
)


class _FakeSession:
    """Minimal stand-in that records what was staged and whether commit ran."""

    def __init__(self) -> None:
        self.added: list = []
        self.committed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:  # pragma: no cover - must never be called
        self.committed = True


def test_event_is_staged_with_the_supplied_detail() -> None:
    session = _FakeSession()
    entity_id = uuid.uuid4()

    event = record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="candidate_rule",
        entity_id=entity_id,
        actor="Dana Reviewer",
        policy_set_key="hr-guide-policy",
        details={"decision": "approve"},
    )

    assert session.added == [event]
    assert event.event_type == CANDIDATE_REVIEWED
    assert event.entity_type == "candidate_rule"
    assert event.entity_id == entity_id
    assert event.actor == "Dana Reviewer"
    assert event.details_json == {
        "decision": "approve",
        "policy_set_key": "hr-guide-policy",
    }


def test_writer_does_not_commit() -> None:
    """The record must land in the caller's transaction.

    Committing here would let the audit row survive a later rollback of the
    approval itself, leaving a record of something that never happened.
    """

    session = _FakeSession()

    record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="candidate_rule",
        entity_id=uuid.uuid4(),
        actor="Dana Reviewer",
    policy_set_key="hr-guide-policy",
    )

    assert session.committed is False


@pytest.mark.parametrize("actor", ["", "   ", "\t"])
def test_blank_actor_is_refused(actor: str) -> None:
    session = _FakeSession()

    with pytest.raises(ValueError, match="requires an actor"):
        record_audit_event(
            session,
            event_type=CANDIDATE_REVIEWED,
            entity_type="candidate_rule",
            entity_id=uuid.uuid4(),
            actor=actor,
        policy_set_key="hr-guide-policy",
        )

    assert session.added == []


def test_actor_is_stored_trimmed() -> None:
    session = _FakeSession()

    event = record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="candidate_rule",
        entity_id=uuid.uuid4(),
        actor="  Dana Reviewer  ",
    policy_set_key="hr-guide-policy",
    )

    assert event.actor == "Dana Reviewer"


def test_missing_details_defaults_to_empty_mapping() -> None:
    """`details_json` is non-nullable, so omitting detail must not produce None."""

    session = _FakeSession()

    event = record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="candidate_rule",
        entity_id=uuid.uuid4(),
        actor="Dana Reviewer",
    policy_set_key=None,
    )

    assert event.details_json == {"policy_set_key": None}


def test_policy_set_key_is_folded_into_details() -> None:
    """Consumers read the owning project from one place.

    The audit table is polymorphic — an event may hang off a candidate rule, a
    policy set or a correlation finding — so the project cannot be derived from
    the entity. Folding it in here is what lets a project timeline exist at all,
    and doing it in the writer rather than at each call site is what stops a
    caller forgetting, which has already happened once.
    """

    session = _FakeSession()

    event = record_audit_event(
    session,
    event_type=CANDIDATE_REVIEWED,
    entity_type="correlation_finding",
    entity_id=uuid.uuid4(),
    actor="Dana Reviewer",
    policy_set_key="saudi-labor-law",
    details={"disposition": "not_an_issue"},
    )

    assert event.details_json["policy_set_key"] == "saudi-labor-law"
    assert event.details_json["disposition"] == "not_an_issue"


def test_caller_details_cannot_forge_the_policy_set_key() -> None:
    """The named argument is authoritative over a stray dict entry.

    Otherwise the ambiguity the parameter was introduced to remove would come
    straight back through the details payload.
    """

    session = _FakeSession()

    event = record_audit_event(
    session,
    event_type=CANDIDATE_REVIEWED,
    entity_type="candidate_rule",
    entity_id=uuid.uuid4(),
    actor="Dana Reviewer",
    policy_set_key="saudi-labor-law",
    details={"policy_set_key": "some-other-project"},
    )

    assert event.details_json["policy_set_key"] == "saudi-labor-law"


def test_supplied_details_mapping_is_not_mutated() -> None:
    """A caller's dict is theirs; the writer must not write into it."""

    session = _FakeSession()
    details = {"decision": "approve"}

    record_audit_event(
    session,
    event_type=CANDIDATE_REVIEWED,
    entity_type="candidate_rule",
    entity_id=uuid.uuid4(),
    actor="Dana Reviewer",
    policy_set_key="hr-guide-policy",
    details=details,
    )

    assert details == {"decision": "approve"}


def test_entity_id_may_be_absent() -> None:
    """Some authoritative actions are not about a single row (a bulk review is
    about a set), so a null entity id must remain legal."""

    session = _FakeSession()

    event = record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="policy_set",
        entity_id=None,
        actor="Dana Reviewer",
    policy_set_key="hr-guide-policy",
    )

    assert event.entity_id is None
