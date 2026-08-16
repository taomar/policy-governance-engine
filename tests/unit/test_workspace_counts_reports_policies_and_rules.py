"""The workspace-counts endpoint reports published policies as their own figure.

WHY THIS TEST EXISTS

The project tab strip badged its "Policies" tab with a number the endpoint
aliased ``policies`` but computed as ``count(*)`` of ``approved_rules`` in the
active version. A published policy holds many rules, so on a version of two
policies holding twenty-eight rules the badge read "Policies 28". That violates
the binding constraint that *the policy is the currency*: a count under a policy
label must be policies, never rules relabelled.

The review side already solves exactly this. ``review_pending`` counts pending
candidate rules and ``review_pending_policies`` counts the same work in the unit
it is decided in, the two partitioning the rows on whether ``provision_id`` is
null so a provision-less row is its own unit and nothing is double-counted. The
publish side must mirror it: ``policy_rules`` (the rules, kept because a policy
is made of rules) beside ``published_policies`` (the policies), each true and
neither derivable from the other.

WHAT THESE TESTS PIN

* On an active version, ``published_policies`` is the count of *policies*
  (distinct ``provision_key`` plus each provision-less rule as its own unit),
  a figure distinct from ``policy_rules`` -- not the rule count wearing a
  policy label.
* A policy set with no active published version reports ``policy_rules`` = 0
  and ``published_policies`` = 0, both *present*: a measured zero, so the
  surface can tell "no published policies" from "the count was not served".
* Rules in an *inactive* version are not charged to the active-version badge.

These are HTTP-boundary tests: the numbers can only have come from seeded rows,
so they are evidence the endpoint counts the database, not a shape it invented.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Awaitable, Callable

import pytest

# The postgresql ``UUID`` type renders a bind value as 32-char hex on SQLite, and
# this endpoint binds the policy set's id into a raw ``text()`` query, so aiosqlite
# is handed a ``uuid.UUID`` directly rather than a value SQLAlchemy pre-converted.
# Teach the driver to render it the same way the column stores it, or the join
# never matches. Only raw UUID params reach this adapter; ORM-bound ids are
# already strings by the time they reach the driver, so other suites are unaffected.
sqlite3.register_adapter(uuid.UUID, lambda value: value.hex)

# `api.app` builds an application at import time and `Settings` needs a URL. Set
# before the import so collection does not depend on a local .env; the URL is
# never connected to, because the session dependency is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    ApprovedPolicyVersion,
    ApprovedRule,
    Base,
    PolicyAuthority,
    PolicySet,
    SourceDocument,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


def _seed_version(
    session: AsyncSession,
    *,
    key: str,
    provision_keys: tuple[str | None, ...],
    is_active: bool = True,
) -> None:
    """Seed one policy set with one document and one version holding the rules.

    ``provision_keys`` is one entry per rule -- repeats share a policy, ``None``
    is a provision-less rule that is its own policy unit -- so a caller states
    the shape it wants to count in the unit under test.
    """
    set_id = uuid.uuid4()
    version_id = uuid.uuid4()
    authority_id = uuid.uuid4()
    session.add(PolicySet(id=set_id, key=key, name=key, owner="owner"))
    session.add(SourceDocument(id=uuid.uuid4(), title="Doc", owner="owner", policy_set_id=set_id))
    session.add(PolicyAuthority(id=authority_id, level="policy", owner="owner", rank=1))
    session.add(
        ApprovedPolicyVersion(
            id=version_id,
            policy_set_id=set_id,
            version_number=1,
            effective_from=date(2024, 1, 1),
            is_active=is_active,
            approved_by="owner",
            approved_at=datetime.now(timezone.utc),
        )
    )
    for index, provision_key in enumerate(provision_keys):
        session.add(
            ApprovedRule(
                id=uuid.uuid4(),
                policy_version_id=version_id,
                authority_id=authority_id,
                rule_id=f"{key}-R{index}",
                title=f"Rule {index}",
                rule_type="obligation",
                effective_from=date(2024, 1, 1),
                scope_json={},
                condition_json={},
                effect_json={},
                provision_key=provision_key,
            )
        )


def _seed_no_version(session: AsyncSession, *, key: str) -> None:
    """A policy set with a document but nothing published -- no active version."""
    set_id = uuid.uuid4()
    session.add(PolicySet(id=set_id, key=key, name=key, owner="owner"))
    session.add(SourceDocument(id=uuid.uuid4(), title="Doc", owner="owner", policy_set_id=set_id))


async def _counts_for(seed: Callable[[AsyncSession], None], key: str) -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            seed(session)
            await session.commit()

        app = create_app()

        async def _override():
            async with maker() as session:
                yield session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            response = await http.get(f"/api/policy-sets/{key}/workspace-counts")
        assert response.status_code == 200, response.text
        return response.json()
    finally:
        await engine.dispose()


async def test_active_version_reports_policies_as_a_figure_distinct_from_rules() -> None:
    # Four rules: two share provision P1, one is P2, one has no provision. That is
    # three policies -- two grouped, one provision-less unit -- holding four rules.
    body = await _counts_for(
        lambda session: _seed_version(session, key="wc-mixed", provision_keys=("P1", "P1", "P2", None)),
        "wc-mixed",
    )

    assert body["policy_rules"] == 4
    assert body["published_policies"] == 3
    # The policy figure is not the rule count relabelled: they disagree here by
    # construction, which is the whole point of carrying both.
    assert body["published_policies"] != body["policy_rules"]


async def test_no_active_version_reports_measured_zero_for_both() -> None:
    body = await _counts_for(lambda session: _seed_no_version(session, key="wc-empty"), "wc-empty")

    # Both keys are present and zero: a zero the endpoint measured, which a caller
    # can tell apart from a key it never sent.
    assert "policy_rules" in body
    assert "published_policies" in body
    assert body["policy_rules"] == 0
    assert body["published_policies"] == 0


async def test_inactive_version_is_not_charged_to_the_active_badge() -> None:
    body = await _counts_for(
        lambda session: _seed_version(
            session, key="wc-inactive", provision_keys=("P1", "P2"), is_active=False
        ),
        "wc-inactive",
    )

    assert body["policy_rules"] == 0
    assert body["published_policies"] == 0
