from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://policy_admin:policy_admin_pw@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+asyncpg://policy_admin:policy_admin_pw@localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import policy_sets as policy_sets_router  # noqa: E402
from policy_platform.domain.models import ApprovedPolicyVersion, Base, PolicyIndexState, PolicySet  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_language import (  # noqa: E402
    ENGLISH_PROJECTION_PROFILE,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from policy_platform.infrastructure.persistence.policy_set_teardown import DeletionOutcome  # noqa: E402
from policy_platform.infrastructure.search.policy_index import (  # noqa: E402
    PolicyIndexBuildOutcome,
    PolicyIndexDropOutcome,
    policy_index_name,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_SET_ID = uuid.UUID("00000000-0000-4000-8000-000000000301")


@pytest.fixture
async def app_with_project(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(PolicySet(id=_SET_ID, key="xx", name="Empty project", owner="policy"))
        await session.commit()

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http, maker, monkeypatch
    finally:
        await engine.dispose()


async def test_manual_policy_index_rebuild_reports_empty_project_without_crashing(app_with_project) -> None:
    http, maker, monkeypatch = app_with_project

    async def _fake_rebuild(*, policy_set_key, version_number, projections, **_kw):
        projection_list = list(projections)
        assert policy_set_key == "xx"
        assert version_number is None
        assert projection_list == []
        return PolicyIndexBuildOutcome(
            state="built",
            policy_set_key=policy_set_key,
            index_name=policy_index_name(policy_set_key),
            version_number=version_number,
            document_count=0,
            indexed_at="2026-08-18T12:00:00+00:00",
        )

    monkeypatch.setattr(policy_sets_router, "rebuild_project_policy_index", _fake_rebuild)

    response = await http.post("/api/policy-sets/xx/policy-index/rebuild")

    assert response.status_code == 200
    assert response.json()["version_number"] is None
    assert response.json()["document_count"] == 0
    async with maker() as session:
        state = (await session.execute(select(PolicyIndexState))).scalar_one()
        assert state.status == "built"
        assert state.indexed_version_number is None
        assert state.document_count == 0


async def test_get_policy_index_reports_recorded_current_state_without_live_search(app_with_project) -> None:
    http, maker, _monkeypatch = app_with_project
    async with maker() as session:
        session.add(
            ApprovedPolicyVersion(
                policy_set_id=_SET_ID,
                version_number=6,
                effective_from=date(2026, 1, 1),
                is_active=True,
                approved_by="policy",
                approved_at=datetime(2026, 8, 18, 11, 0, tzinfo=UTC),
            )
        )
        session.add(
            PolicyIndexState(
                policy_set_id=_SET_ID,
                index_name=policy_index_name("xx"),
                indexed_version_number=6,
                document_count=10,
                built_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
                status="built",
                attempted_version_number=6,
                attempted_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
                # Built under the rendering contract the query side uses.
                # Without it the record would be reporting an index that
                # matches the active version but cannot be matched *against*,
                # which is stale on the second axis — see the test below.
                projection_profile=ENGLISH_PROJECTION_PROFILE,
            )
        )
        await session.commit()

    response = await http.get("/api/policy-sets/xx/policy-index")

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_set_key"] == "xx"
    assert payload["index_name"] == policy_index_name("xx")
    assert payload["last_attempt"] == "built"
    assert payload["freshness"] == "current"
    assert payload["active_version_number"] == 6
    assert payload["indexed_version_number"] == 6
    assert payload["document_count"] == 10
    assert payload["source"] == "recorded_build_state"
    assert payload["live_probe"] is False


async def test_an_index_built_without_a_projection_reads_stale_on_the_second_axis(
    app_with_project,
) -> None:
    """Matching the active version is not the same as being matchable.

    A row written before the corpus was rendered — or by a rebuild that could not
    render it — records a build that really happened and really indexed
    documents. It just did not put them in the language a question is asked in.
    Reporting that as `current` would tell an operator there is nothing to do,
    while every case against the project refuses.
    """

    http, maker, _monkeypatch = app_with_project
    async with maker() as session:
        session.add(
            ApprovedPolicyVersion(
                policy_set_id=_SET_ID,
                version_number=6,
                effective_from=date(2026, 1, 1),
                is_active=True,
                approved_by="policy",
                approved_at=datetime(2026, 8, 18, 11, 0, tzinfo=UTC),
            )
        )
        session.add(
            PolicyIndexState(
                policy_set_id=_SET_ID,
                index_name=policy_index_name("xx"),
                indexed_version_number=6,
                document_count=10,
                built_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
                status="built",
                attempted_version_number=6,
                attempted_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
                projection_profile=None,
            )
        )
        await session.commit()

    payload = (await http.get("/api/policy-sets/xx/policy-index")).json()

    assert payload["last_attempt"] == "built"
    assert payload["freshness"] == "stale"
    # The version comparison is untouched: what moved is the second axis.
    assert payload["active_version_number"] == payload["indexed_version_number"] == 6


async def test_get_policy_index_reports_nothing_to_index_when_no_active_version(app_with_project) -> None:
    http, _maker, _monkeypatch = app_with_project

    response = await http.get("/api/policy-sets/xx/policy-index")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_attempt"] == "never_attempted"
    assert payload["freshness"] == "nothing_to_index"
    assert payload["active_version_number"] is None
    assert payload["indexed_version_number"] is None
    assert payload["document_count"] == 0
    assert payload["attempted_at"] is None


async def test_get_policy_index_reports_unknown_project_as_404(app_with_project) -> None:
    http, _maker, _monkeypatch = app_with_project

    response = await http.get("/api/policy-sets/missing/policy-index")

    assert response.status_code == 404
    assert response.json()["detail"] == "policy set 'missing' not found"


async def test_delete_reports_project_policy_index_separately_from_authoring_index(app_with_project) -> None:
    http, _maker, monkeypatch = app_with_project

    async def _fake_drop(*, policy_set_key, **_kw):
        return PolicyIndexDropOutcome(
            state="dropped",
            policy_set_key=policy_set_key,
            index_name=policy_index_name(policy_set_key),
            deleted=True,
            attempted_at="2026-08-18T12:00:00+00:00",
        )

    monkeypatch.setattr(policy_sets_router, "drop_project_policy_index", _fake_drop)

    async def _fake_delete_policy_set(_session, policy_set, *, actor):
        assert actor == "manager"
        outcome = DeletionOutcome(policy_set_key=policy_set.key, policy_set_name=policy_set.name)
        outcome.search_documents_identified = 0
        outcome.search_documents_deleted = 0
        return outcome, []

    monkeypatch.setattr(policy_sets_router, "delete_policy_set", _fake_delete_policy_set)

    response = await http.delete("/api/policy-sets/xx", params={"actor": "manager", "confirm": "xx"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["search_index"] == "clean"
    assert payload["policy_index"] == "clean"
    assert payload["policy_index_name"] == policy_index_name("xx")
    assert payload["policy_index_deleted"] is True
    assert payload["policy_index_error"] is None
