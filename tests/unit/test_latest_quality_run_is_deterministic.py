"""The read that shows a reviewer "the current quality evaluation" is stable.

`quality_report` (api/routers/ai.py) answers with "the most recent recorded
quality evaluation of the published version". It gets there through
`latest_quality_report`, which asks `QualityRunRepository.list_by_policy_set`
for one row ordered `run_at DESC` and returns `runs[0]`. So whichever row that
query puts first is what a reviewer is told is current.

`run_at` is stamped from the wall clock at evaluation time, and it is not a
total order: on a coarse clock two runs recorded in the same tick share it
(this is the same hazard `clauses.sequence` exists to avoid -- see the comment
on `DocumentClause` in domain/models.py). With only `run_at DESC` to go on, the
database is free to return either of the tied rows first, and nothing makes it
choose the same one twice. A reviewer can then be shown an older evaluation as
the current one, and shown a different one on the next read, with no run in
between.

`quality_runs` has no sequence column to recover true order from, so when
`run_at` genuinely ties the truly-latest row is unknowable -- but "unknowable"
is not the same as "may vary between reads". This pins the weaker, achievable
property: the choice is deterministic. The repository breaks the tie on the
primary key, so the row returned is fixed and reproducible rather than left to
the database's plan.

The tie is constructed explicitly -- two runs with an identical `run_at` --
rather than by racing the clock, because a defect that only appears when two
`datetime.now()` calls collide cannot be failed on demand, and a guard that
cannot be made to fail proves nothing. Before the tiebreak the read returns the
row the scan happens to surface first; after it, the greater id. The assertion
names that expected row.

Constraint 1: the id asserted on is the fixture's own; no observed corpus count
or timestamp appears in an assertion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.domain.models import Base, PolicySet, QualityRun
from policy_platform.infrastructure.quality.ai_quality import latest_quality_report


# JSONB and UUID are Postgres-only; compiling them for SQLite lets the real
# table be created so the real ordering query runs under the test.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000e001")
SET_KEY = "quality-latest-guard-set"
SCOPE = "published"

# Two runs, tied on run_at. Fixed ids so the tiebreak has a defined winner:
# `id DESC` selects the greater, EARLIER is inserted first so that, before the
# fix, the row the scan surfaces first is the *other* one.
EARLIER_INSERTED_ID = uuid.UUID("00000000-0000-4000-8000-00000000e0a1")
LATER_INSERTED_ID = uuid.UUID("00000000-0000-4000-8000-00000000e0a2")
DETERMINISTIC_WINNER_ID = max(EARLIER_INSERTED_ID, LATER_INSERTED_ID, key=str)

# A single instant both runs are stamped with. Never asserted on -- it exists
# only to force the tie the clock would otherwise create by accident.
_TIE_INSTANT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


def _run(run_id: uuid.UUID) -> QualityRun:
    return QualityRun(
        id=run_id,
        policy_set_id=SET_ID,
        scope=SCOPE,
        version_number=1,
        rule_count=1,
        high_count=0,
        medium_count=0,
        low_count=0,
        ai_review_used=True,
        methodology_version="2",
        findings_json=[],
        triggered_by="",
        run_at=_TIE_INSTANT,
    )


@pytest.mark.asyncio
async def test_latest_quality_run_is_deterministic_when_run_at_ties() -> None:
    """Two runs share a run_at; the read must pick the same one every time.

    Fails on `order_by(run_at.desc())` alone: with the tie unbroken the row
    returned is whatever the scan surfaces first, which is the earlier-inserted
    run here, not the tiebreak's winner. Passes once the primary key breaks the
    tie, making the current-evaluation read stable rather than plan-dependent.
    """
    session, engine = await _session()
    try:
        session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="guard"))
        # Insertion order is load-bearing for the pre-fix failure: the earlier
        # row is the one an unbroken tie surfaces, and it is not the winner.
        session.add(_run(EARLIER_INSERTED_ID))
        await session.flush()
        session.add(_run(LATER_INSERTED_ID))
        await session.commit()

        report = await latest_quality_report(session, policy_set_key=SET_KEY, scope=SCOPE)

        assert report["quality_run_id"] == str(DETERMINISTIC_WINNER_ID)
    finally:
        await session.close()
        await engine.dispose()
