"""Cursor-pagination properties for ``GET /candidate-rules?limit=&cursor=``.

Each test is named as a sentence describing the property held so a failure
reads as "this property no longer holds" rather than "test 3 broke".
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.api.routers.candidate_rules import list_candidate_rules
from policy_platform.api.schemas import PaginatedCandidateRulesResponse
from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import EvidenceReference, RuleLineage
from policy_platform.domain.models import (
    Base,
    CandidateRule,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)
from tests.fixtures.factories import make_rule


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_COND = FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS)

SET_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
SET_KEY = "pagination-test-set"
_BASE_TIME = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _payload(rule_id: str, clause_id: str = "clause-1") -> dict:
    rule = make_rule(rule_id, _COND).model_copy(
        update={
            "title": rule_id,
            "lineage": RuleLineage(source_elements=clause_id),
            "evidence": [
                EvidenceReference(
                    document_version_id="version-1",
                    source_hash="h" * 16,
                    page=1,
                    clause_id=clause_id,
                )
            ],
        }
    )
    return rule.model_dump(mode="json")


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


async def _seed(session: AsyncSession, count: int, *, statuses: list[str] | None = None) -> list[uuid.UUID]:
    """Seed ``count`` candidate rules and return their ids in insertion order.

    When ``statuses`` is given it must have ``count`` entries — one per rule.
    All rules share a single policy set, document, and extraction run.
    """
    session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="test"))
    doc_id = uuid.UUID("00000000-0000-4000-8000-000000000010")
    ver_id = uuid.UUID("00000000-0000-4000-8000-000000000011")
    run_id = uuid.UUID("00000000-0000-4000-8000-000000000012")
    session.add(SourceDocument(id=doc_id, title="Doc", owner="test", policy_set_id=SET_ID))
    session.add(DocumentVersion(id=ver_id, document_id=doc_id, version_number=1, content_hash="c" * 64, storage_path="/d.pdf"))
    session.add(ExtractionRun(id=run_id, document_version_id=ver_id, status="succeeded"))

    ids: list[uuid.UUID] = []
    for i in range(count):
        cid = uuid.UUID(int=1000 + i)
        st = statuses[i] if statuses else "candidate"
        session.add(CandidateRule(
            id=cid,
            policy_set_id=SET_ID,
            extraction_run_id=run_id,
            rule_type="obligation",
            review_status=st,
            delta_status="new",
            created_at=_BASE_TIME + timedelta(seconds=i),
            payload_json=_payload(f"RULE-{i:04d}"),
        ))
        ids.append(cid)

    await session.commit()
    return ids


# ---------------------------------------------------------------------------
# without limit the response is byte-identical to today's
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_limit_the_response_is_a_bare_list() -> None:
    """The compatibility property: no ``limit`` → a plain list, not a wrapper."""
    session, engine = await _session()
    try:
        ids = await _seed(session, 5)
        result = await list_candidate_rules(key=SET_KEY, session=session)
        assert isinstance(result, list)
        assert len(result) == 5
        assert [r.id for r in result] == [str(i) for i in ids]
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# a page plus its next_cursor walks the whole set exactly once
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_walking_pages_collects_every_record_exactly_once() -> None:
    """No record repeated, none missed."""
    session, engine = await _session()
    try:
        ids = await _seed(session, 25)
        collected: list[str] = []
        cursor = None
        pages = 0
        while True:
            result = await list_candidate_rules(key=SET_KEY, limit=7, cursor=cursor, session=session)
            assert isinstance(result, PaginatedCandidateRulesResponse)
            collected.extend(r.id for r in result.items)
            pages += 1
            cursor = result.next_cursor
            if cursor is None:
                break

        assert pages == 4  # ceil(25/7)
        assert len(collected) == 25
        assert collected == [str(i) for i in ids], "order or content mismatch"
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# a record whose status changes mid-walk does not cause another record to be
# skipped — the reason for keyset over offset
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_status_change_mid_walk_does_not_skip_a_record() -> None:
    """Keyset pagination anchors to a position, not an offset.

    If the reviewer is paging with ``status=candidate`` and approves a rule
    that appeared on a previous page, offset pagination would shift every
    subsequent row back by one, silently skipping whatever was at the boundary.
    Keyset pagination is immune because the cursor is a fixed point in the
    ``(created_at, id)`` space, not a count of rows to skip.
    """
    session, engine = await _session()
    try:
        all_candidate = ["candidate"] * 10
        ids = await _seed(session, 10, statuses=all_candidate)

        # Page 1: ids[0..4]
        page1 = await list_candidate_rules(key=SET_KEY, status="candidate", limit=5, session=session)
        assert isinstance(page1, PaginatedCandidateRulesResponse)
        assert len(page1.items) == 5
        cursor = page1.next_cursor

        # Simulate approving ids[2] (on page 1) — it leaves the status=candidate set.
        from sqlalchemy import update
        await session.execute(
            update(CandidateRule)
            .where(CandidateRule.id == ids[2])
            .values(review_status="approved")
        )
        await session.commit()

        # Page 2: should still get ids[5..9], not skip one.
        page2 = await list_candidate_rules(key=SET_KEY, status="candidate", limit=5, cursor=cursor, session=session)
        assert isinstance(page2, PaginatedCandidateRulesResponse)
        page2_ids = [r.id for r in page2.items]
        assert page2_ids == [str(ids[i]) for i in range(5, 10)]
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# rows sharing a sort value are still totally ordered
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rows_sharing_created_at_are_totally_ordered_across_pages() -> None:
    """Ties in ``created_at`` are broken by ``id``; no row is lost or repeated."""
    session, engine = await _session()
    try:
        session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="test"))
        doc_id = uuid.UUID("00000000-0000-4000-8000-000000000010")
        ver_id = uuid.UUID("00000000-0000-4000-8000-000000000011")
        run_id = uuid.UUID("00000000-0000-4000-8000-000000000012")
        session.add(SourceDocument(id=doc_id, title="Doc", owner="test", policy_set_id=SET_ID))
        session.add(DocumentVersion(id=ver_id, document_id=doc_id, version_number=1, content_hash="c" * 64, storage_path="/d.pdf"))
        session.add(ExtractionRun(id=run_id, document_version_id=ver_id, status="succeeded"))

        same_time = _BASE_TIME
        ids = []
        for i in range(8):
            cid = uuid.UUID(int=2000 + i)
            session.add(CandidateRule(
                id=cid,
                policy_set_id=SET_ID,
                extraction_run_id=run_id,
                rule_type="obligation",
                review_status="candidate",
                delta_status="new",
                created_at=same_time,
                payload_json=_payload(f"TIE-{i:04d}"),
            ))
            ids.append(cid)
        await session.commit()

        collected: list[str] = []
        cursor = None
        while True:
            result = await list_candidate_rules(key=SET_KEY, limit=3, cursor=cursor, session=session)
            assert isinstance(result, PaginatedCandidateRulesResponse)
            collected.extend(r.id for r in result.items)
            cursor = result.next_cursor
            if cursor is None:
                break

        assert len(collected) == 8
        assert len(set(collected)) == 8, "duplicates found"
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# a malformed cursor is refused with 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_malformed_cursor_returns_422() -> None:
    session, engine = await _session()
    try:
        await _seed(session, 1)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await list_candidate_rules(key=SET_KEY, limit=10, cursor="not-a-valid-cursor", session=session)
        assert exc_info.value.status_code == 422
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# the total reflects the active filter, not the whole table
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_total_reflects_active_filter_not_whole_table() -> None:
    session, engine = await _session()
    try:
        statuses = ["candidate"] * 7 + ["approved"] * 3
        await _seed(session, 10, statuses=statuses)

        result = await list_candidate_rules(key=SET_KEY, status="candidate", limit=5, session=session)
        assert isinstance(result, PaginatedCandidateRulesResponse)
        assert result.total == 7

        result_all = await list_candidate_rules(key=SET_KEY, limit=100, session=session)
        assert isinstance(result_all, PaginatedCandidateRulesResponse)
        assert result_all.total == 10
    finally:
        await session.close()
        await engine.dispose()
