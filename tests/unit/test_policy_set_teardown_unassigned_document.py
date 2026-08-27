from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from policy_platform.domain.models import (
    CandidateRule,
    Clause,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)
from policy_platform.infrastructure.persistence.policy_set_teardown import delete_policy_set


def _async_url() -> str:
    fallback = "postgresql://policy_admin:policy_admin_pw@localhost:5433/policy_platform_advtool"
    url = os.environ.get("DATABASE_URL", fallback)
    if not url.startswith(("postgresql://", "postgresql+asyncpg://")):
        url = fallback
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _require_database(engine) -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on local database availability
        pytest.skip(f"local Postgres fixture is unavailable: {exc}")


@pytest.mark.asyncio
async def test_teardown_removes_clauses_reached_through_project_runs_when_document_is_unassigned():
    """The project owns the extraction even when source_documents.policy_set_id is NULL."""

    engine = create_async_engine(_async_url())
    await _require_database(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    policy_set_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    run_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    suffix = str(policy_set_id)[:8]

    async with maker() as session:
        try:
            policy_set = PolicySet(
                id=policy_set_id,
                key=f"teardown-unassigned-{suffix}",
                name="Teardown unassigned document fixture",
                description="",
                owner="test",
                category="test",
            )
            session.add(policy_set)
            session.add(
                SourceDocument(
                    id=document_id,
                    title=f"Unassigned teardown fixture {suffix}",
                    source_system="test",
                    owner="test",
                    policy_set_id=None,
                )
            )
            await session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    version_number=1,
                    content_hash=f"hash-{suffix}",
                    storage_path=f"test/{suffix}.txt",
                    mime_type="text/plain",
                )
            )
            await session.flush()
            session.add_all(
                [
                    Clause(
                        id=clause_id,
                        document_version_id=version_id,
                        clause_ref="1",
                        text="The project-owned rule is grounded here.",
                        sequence=0,
                    ),
                    ExtractionRun(
                        id=run_id,
                        document_version_id=version_id,
                        status="completed",
                        owner_kind="test",
                    ),
                ]
            )
            await session.flush()
            session.add(
                CandidateRule(
                    id=rule_id,
                    extraction_run_id=run_id,
                    policy_set_id=policy_set_id,
                    revision=1,
                    rule_type="obligation",
                    payload_json={"rule_id": "R-1", "statement": "Do the thing."},
                    review_status="candidate",
                )
            )
            await session.flush()

            outcome, search_ids = await delete_policy_set(session, policy_set, actor="pytest")

            remaining_clauses = await session.scalar(
                select(func.count()).select_from(Clause).where(Clause.id == clause_id)
            )
            assert remaining_clauses == 0
            assert outcome.rows_deleted.get("clauses") == 1
            assert search_ids
        finally:
            await session.rollback()
            await engine.dispose()


@pytest.mark.asyncio
async def test_teardown_retains_a_document_version_reached_by_another_project_run():
    """A reused source version is not deleted out from under another project."""

    engine = create_async_engine(_async_url())
    await _require_database(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    policy_set_id = uuid.uuid4()
    other_policy_set_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    run_id = uuid.uuid4()
    other_run_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    other_rule_id = uuid.uuid4()
    suffix = str(policy_set_id)[:8]

    async with maker() as session:
        try:
            session.add_all(
                [
                    PolicySet(
                        id=policy_set_id,
                        key=f"teardown-shared-{suffix}",
                        name="Teardown shared document fixture",
                        description="",
                        owner="test",
                        category="test",
                    ),
                    PolicySet(
                        id=other_policy_set_id,
                        key=f"teardown-shared-other-{suffix}",
                        name="Other teardown shared document fixture",
                        description="",
                        owner="test",
                        category="test",
                    ),
                    SourceDocument(
                        id=document_id,
                        title=f"Shared teardown fixture {suffix}",
                        source_system="test",
                        owner="test",
                        policy_set_id=None,
                    ),
                ]
            )
            await session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    version_number=1,
                    content_hash=f"shared-hash-{suffix}",
                    storage_path=f"test/shared-{suffix}.txt",
                    mime_type="text/plain",
                )
            )
            await session.flush()
            session.add_all(
                [
                    Clause(
                        id=clause_id,
                        document_version_id=version_id,
                        clause_ref="1",
                        text="Both projects ground rules in this source version.",
                        sequence=0,
                    ),
                    ExtractionRun(
                        id=run_id,
                        document_version_id=version_id,
                        status="completed",
                        owner_kind="test",
                    ),
                    ExtractionRun(
                        id=other_run_id,
                        document_version_id=version_id,
                        status="completed",
                        owner_kind="test",
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    CandidateRule(
                        id=rule_id,
                        extraction_run_id=run_id,
                        policy_set_id=policy_set_id,
                        revision=1,
                        rule_type="obligation",
                        payload_json={"rule_id": "R-1"},
                        review_status="candidate",
                    ),
                    CandidateRule(
                        id=other_rule_id,
                        extraction_run_id=other_run_id,
                        policy_set_id=other_policy_set_id,
                        revision=1,
                        rule_type="obligation",
                        payload_json={"rule_id": "R-2"},
                        review_status="candidate",
                    ),
                ]
            )
            await session.flush()

            policy_set = await session.get(PolicySet, policy_set_id)
            assert policy_set is not None
            outcome, search_ids = await delete_policy_set(session, policy_set, actor="pytest")

            remaining_clauses = await session.scalar(
                select(func.count()).select_from(Clause).where(Clause.id == clause_id)
            )
            other_rules = await session.scalar(
                select(func.count()).select_from(CandidateRule).where(CandidateRule.id == other_rule_id)
            )
            deleted_runs = await session.scalar(
                select(func.count()).select_from(ExtractionRun).where(ExtractionRun.id == run_id)
            )
            other_runs = await session.scalar(
                select(func.count()).select_from(ExtractionRun).where(ExtractionRun.id == other_run_id)
            )
            assert remaining_clauses == 1
            assert other_rules == 1
            assert deleted_runs == 0
            assert other_runs == 1
            assert outcome.document_versions_retained == 1
            assert search_ids == []
        finally:
            await session.rollback()
            await engine.dispose()
