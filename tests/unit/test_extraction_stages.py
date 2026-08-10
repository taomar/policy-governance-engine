"""Tests for extraction stage persistence.

The migration and model are exercised against a real (in-memory SQLite)
database rather than mocked. A schema change that only ever ran against a mock
would prove nothing about whether it applies, and Postgres is not available in
every environment this suite runs in.

Postgres-specific column types are mapped for SQLite so the *shape* of the
schema — columns, constraints, ordering behaviour — is genuinely tested. What
this cannot test is Postgres-specific DDL, so the migration file itself is
additionally checked for reversibility.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.domain.models import ExtractionStage
from policy_platform.infrastructure.extraction_stage_repository import (
    ExtractionStageRepository,
)


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the table
# actually be created, so the schema's shape — columns, ordering, constraint
# behaviour — is genuinely exercised. The compromise is confined to the test.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


@pytest.fixture
async def session() -> AsyncSession:
    """A real database session over in-memory SQLite.

    Only the stage table is created, so the foreign keys to `document_versions`
    and `extraction_runs` have no target. SQLite does not enforce foreign keys
    by default, which is what keeps this focused on the table under test rather
    than requiring the whole schema.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_conn: ExtractionStage.__table__.create(sync_conn, checkfirst=True)
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active

    await engine.dispose()


def _ids() -> tuple[uuid.UUID, str]:
    return uuid.uuid4(), "k" * 64


class TestRecording:
    async def test_a_stage_is_persisted_and_read_back(self, session) -> None:
        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        await repo.record(
            document_version_id=version_id,
            idempotency_key=key,
            stage_name="docling_converted",
            sequence=1,
            detail="22 elements",
            duration_seconds=0.12,
        )
        stages = await repo.list_for_run(key)

        assert len(stages) == 1
        assert stages[0].stage_name == "docling_converted"
        assert stages[0].detail == "22 elements"

    async def test_stages_order_by_sequence_not_timestamp(self, session) -> None:
        """Several stages of one run routinely land in the same clock tick."""

        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        for name, sequence in [("third", 3), ("first", 1), ("second", 2)]:
            await repo.record(
                document_version_id=version_id,
                idempotency_key=key,
                stage_name=name,
                sequence=sequence,
            )

        assert [s.stage_name for s in await repo.list_for_run(key)] == [
            "first",
            "second",
            "third",
        ]

    async def test_runs_are_isolated_by_key(self, session) -> None:
        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        await repo.record(
            document_version_id=version_id, idempotency_key=key, stage_name="a", sequence=1
        )
        await repo.record(
            document_version_id=version_id,
            idempotency_key="j" * 64,
            stage_name="a",
            sequence=1,
        )

        assert len(await repo.list_for_run(key)) == 1


class TestRetrySupport:
    async def test_only_successful_stages_count_as_completed(self, session) -> None:
        """A failed stage produced no output, so re-running it is the only
        correct response."""

        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        await repo.record(
            document_version_id=version_id, idempotency_key=key, stage_name="converted", sequence=1
        )
        await repo.record(
            document_version_id=version_id,
            idempotency_key=key,
            stage_name="verified",
            sequence=2,
            status="failed",
        )

        assert await repo.completed_stage_names(key) == {"converted"}

    async def test_attempt_numbers_are_derived_not_guessed(self, session) -> None:
        """A caller that guessed would collide with the unique constraint and
        turn a legitimate retry into a write failure."""

        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        assert await repo.next_attempt(key, "converted") == 1

        await repo.record(
            document_version_id=version_id,
            idempotency_key=key,
            stage_name="converted",
            sequence=1,
            status="failed",
        )
        assert await repo.next_attempt(key, "converted") == 2

        await repo.record(
            document_version_id=version_id,
            idempotency_key=key,
            stage_name="converted",
            sequence=1,
            attempt=2,
        )
        assert await repo.next_attempt(key, "converted") == 3

    async def test_repeated_attempts_are_all_retained(self, session) -> None:
        """A retry history is the evidence for whether a failure was transient."""

        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        for attempt in (1, 2):
            await repo.record(
                document_version_id=version_id,
                idempotency_key=key,
                stage_name="converted",
                sequence=1,
                attempt=attempt,
                status="failed" if attempt == 1 else "ok",
            )

        stages = await repo.list_for_run(key)
        assert [s.attempt for s in stages] == [1, 2]


class TestRunStatus:
    async def test_a_run_with_no_stages_has_no_status(self, session) -> None:
        assert await ExtractionStageRepository(session).latest_status("m" * 64) is None

    async def test_a_clean_run_is_ok(self, session) -> None:
        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        for index, name in enumerate(["a", "b"], start=1):
            await repo.record(
                document_version_id=version_id,
                idempotency_key=key,
                stage_name=name,
                sequence=index,
            )

        assert await repo.latest_status(key) == "ok"

    async def test_any_failed_stage_fails_the_run(self, session) -> None:
        """A later stage succeeding does not repair content an earlier one lost."""

        repo = ExtractionStageRepository(session)
        version_id, key = _ids()

        await repo.record(
            document_version_id=version_id,
            idempotency_key=key,
            stage_name="converted",
            sequence=1,
            status="failed",
        )
        await repo.record(
            document_version_id=version_id, idempotency_key=key, stage_name="verified", sequence=9
        )

        assert await repo.latest_status(key) == "failed"


class TestMigration:
    """The migration is additive and reversible.

    Checked by reading the file rather than by executing it, because applying
    Postgres DDL needs a Postgres. What can be verified without one is that it
    creates only new objects and drops exactly what it created.
    """

    MIGRATION = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "a1b2c3d4e5f6_extraction_stages_table.py"
    )

    def test_migration_exists_and_chains_to_the_previous_head(self) -> None:
        source = self.MIGRATION.read_text(encoding="utf-8")
        assert 'revision: str = "a1b2c3d4e5f6"' in source
        assert '"d2e3f4a5b6c7"' in source

    def test_migration_only_creates_new_objects(self) -> None:
        """No existing table or column may be touched, so this is safe to apply
        to a populated database."""

        source = self.MIGRATION.read_text(encoding="utf-8")
        for forbidden in ("op.drop_column", "op.alter_column", "op.rename_table"):
            assert forbidden not in source.split("def downgrade")[0]

    def test_downgrade_reverses_everything_upgrade_created(self) -> None:
        source = self.MIGRATION.read_text(encoding="utf-8")
        upgrade, downgrade = source.split("def downgrade")

        assert upgrade.count("op.create_index") == downgrade.count("op.drop_index")
        assert "op.drop_table(\"extraction_stages\")" in downgrade
        assert "op.drop_constraint" in downgrade

    def test_migration_columns_match_the_model_exactly(self) -> None:
        """Both are hand-written, so they can drift.

        A model column missing from the migration fails only on a fresh
        deployment, long after the change was reviewed — which is the worst
        moment to discover it.
        """

        import re

        model_columns = {column.name for column in ExtractionStage.__table__.columns}
        migration_columns = set(
            re.findall(r'sa\.Column\(\s*"([^"]+)"', self.MIGRATION.read_text(encoding="utf-8"))
        )

        assert model_columns == migration_columns
