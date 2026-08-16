"""The startup reconciler fails only the runs the API itself owns.

At startup the API closes out extraction runs a previous incarnation left
`running` or `pending`: an in-process task whose process is gone cannot be
resumed, so it is failed rather than left dangling forever. The sweep that does
this once had no ownership predicate -- it updated every `running`/`pending` row
in `extraction_runs`, table-wide. A run a *different* process (a headless or CLI
extraction) is driving is legitimately `running`; the table-wide sweep stamped
it `failed` on nothing but the API's own restart.

That is a state collapse, not a housekeeping detail. A still-working run and an
interrupted run are different states, and `failed` is also one of the statuses
baseline selection refuses -- so a healthy run flipped to `failed` is silently
removed from baseline selection, the wrong-baseline mechanism the handover
records as the source of a large, confidently-wrong stability measurement.

`owner_kind` records which runtime's liveness a run is bound to, and the sweep
is now scoped to `owner_kind == OWNER_API`. These tests construct the two states
the old predicate could not tell apart -- an API-owned dangling run and a live
foreign run -- and assert the reconciler fails the first and leaves the second
untouched. Removing the `owner_kind` clause turns the second assertion red,
which is what makes the clause load-bearing rather than decorative.

No assertion carries an observed count or a corpus literal; the only literals
are status labels, which are the domain's own state vocabulary.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.api.app import _reconcile_interrupted_runs_for_session
from policy_platform.domain.models import Base, ExtractionRun
from policy_platform.infrastructure.extraction.ai_extraction import (
    _UNUSABLE_BASELINE_STATUSES,
)
from policy_platform.infrastructure.persistence.repositories.candidates import OWNER_API


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# `extraction_runs` table be created, so the real columns and the real UPDATE
# the reconciler issues are exercised, not a stand-in.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


# Fixed, never uuid4(): a fixture whose outcome depends on a generated id is not
# a fixture. Foreign-key enforcement is off under SQLite, so a fabricated
# version id lets these runs stand alone -- the reconciler reads `status` and
# `owner_kind`, and reaches nothing through the foreign key.
VERSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000d0")
API_RUNNING = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
API_PENDING = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
API_COMPLETED = uuid.UUID("00000000-0000-4000-8000-0000000000a3")
FOREIGN_RUNNING = uuid.UUID("00000000-0000-4000-8000-0000000000f1")

# Any owner_kind that is not OWNER_API: a run whose liveness is not bound to the
# API process. The exact token does not matter, only that it is not the API's.
OWNER_HEADLESS = "headless"


async def _fresh_engine() -> object:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _run(run_id: uuid.UUID, *, status: str, owner_kind: str) -> ExtractionRun:
    return ExtractionRun(
        id=run_id,
        document_version_id=VERSION_ID,
        status=status,
        owner_kind=owner_kind,
    )


async def _seed(engine: object, runs: list[ExtractionRun]) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(runs)
        await session.commit()


async def _reconcile(engine: object) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _reconcile_interrupted_runs_for_session(session)


async def _state(engine: object) -> dict[uuid.UUID, tuple[str, str, str | None]]:
    """Read committed state through a fresh session.

    The reconciler issues a Core bulk UPDATE, which does not sync the session
    that ran it; a fresh session reads the true committed rows rather than a
    stale identity map.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        rows = (await session.execute(select(ExtractionRun))).scalars().all()
        return {row.id: (row.status, row.owner_kind, row.error_message) for row in rows}


@pytest.mark.asyncio
async def test_reconciler_fails_only_api_owned_interrupted_runs() -> None:
    engine = await _fresh_engine()
    try:
        await _seed(
            engine,
            [
                _run(API_RUNNING, status="running", owner_kind=OWNER_API),
                _run(API_PENDING, status="pending", owner_kind=OWNER_API),
                _run(API_COMPLETED, status="completed", owner_kind=OWNER_API),
                _run(FOREIGN_RUNNING, status="running", owner_kind=OWNER_HEADLESS),
            ],
        )

        await _reconcile(engine)

        state = await _state(engine)

        # The API's own runs left mid-flight by a previous incarnation are the
        # ones this process can honestly declare dead, so they are failed.
        assert state[API_RUNNING][0] == "failed"
        assert state[API_PENDING][0] == "failed"
        # The failure is recorded in-band, not silently.
        assert state[API_RUNNING][2] is not None
        assert state[API_PENDING][2] is not None

        # A terminal API run is not touched: it did not die mid-flight.
        assert state[API_COMPLETED][0] == "completed"

        # The run another process is still working is left exactly as it was --
        # its status unchanged and no interrupted-message stamped over it. This
        # is the assertion the missing `owner_kind` clause turned red.
        assert state[FOREIGN_RUNNING][0] == "running"
        assert state[FOREIGN_RUNNING][2] is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_spared_foreign_run_is_kept_out_of_an_unusable_baseline_state() -> None:
    """Why the ownership scope matters beyond the label.

    `failed` is one of the statuses baseline selection refuses, so stamping a
    live foreign run `failed` would not merely mislabel it -- it would remove a
    healthy run from baseline selection, which is the wrong-baseline mechanism
    the handover records. This asserts the reconciler does not move a foreign run
    into that unusable state. It deliberately does not assert that a still
    `running` run is itself a usable baseline -- it is not one yet; the point is
    that the run is left free to finish and become one.
    """
    engine = await _fresh_engine()
    try:
        await _seed(engine, [_run(FOREIGN_RUNNING, status="running", owner_kind=OWNER_HEADLESS)])

        await _reconcile(engine)

        status, _owner, error_message = (await _state(engine))[FOREIGN_RUNNING]

        # The harm being avoided is specifically baseline-disqualification...
        assert "failed" in _UNUSABLE_BASELINE_STATUSES
        # ...and the reconciler did not inflict it: the foreign run is not failed.
        assert status != "failed"
        # It keeps the exact state it arrived in.
        assert status == "running"
        assert error_message is None
    finally:
        await engine.dispose()
