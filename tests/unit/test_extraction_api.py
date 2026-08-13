"""Tests for the extraction API surface.

Run against a real database engine and a real FastAPI app rather than mocks, so
the routes are exercised the way a client would call them. What matters here is
not that the endpoints return data, but that they return it *without* offering
anything that would undermine the guarantees the rest of the integration
establishes: no way to mutate a canonical artifact, and no duplicate of the
review workflow the application already owns.
"""
from __future__ import annotations

import os
import uuid

import pytest

# `api.app` constructs an application at import time, and `Settings` requires a
# database URL. Set before the import so collecting this module does not depend
# on a developer's local .env — the URL is never connected to, because every
# session is overridden below.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+psycopg://test:test@localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    Clause,
    DocumentVersion,
    ExtractionStage,
    SourceDocument,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


ELEMENTS = [
    ("Ea1b2c3d4e5f60011", "heading", "1. Scope", None),
    ("Ea1b2c3d4e5f60012", "paragraph", "Employees must apply in writing.", "1. Scope"),
    ("Ea1b2c3d4e5f60013", "paragraph", "Approval is required.", "1. Scope"),
]


@pytest.fixture
async def client():
    """A real app over in-memory SQLite, with one document version seeded."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            SourceDocument.__table__,
            DocumentVersion.__table__,
            Clause.__table__,
            ExtractionStage.__table__,
        ):
            await connection.run_sync(lambda c, t=table: t.create(c, checkfirst=True))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    version_id = uuid.uuid4()
    document_id = uuid.uuid4()

    async with maker() as session:
        session.add(
            SourceDocument(id=document_id, title="HR Policy", owner="hr", source_system="test")
        )
        session.add(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                content_hash="a" * 64,
                storage_path="/tmp/x.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        )
        for index, (element_id, element_type, text, section) in enumerate(ELEMENTS):
            session.add(
                Clause(
                    document_version_id=version_id,
                    clause_ref=f"p1-{element_id}",
                    section=section,
                    page=1,
                    text=text,
                    sequence=index,
                    element_id=element_id,
                    element_type=element_type,
                    source_fragments=[
                        {"page": 1, "start_offset": 0, "end_offset": len(text), "text": text}
                    ],
                )
            )
        await session.commit()

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client, version_id, maker

    await engine.dispose()


class TestCanonicalDocument:
    async def test_elements_are_returned_in_reading_order(self, client) -> None:
        http, version_id, _ = client
        response = await http.get(f"/api/extraction/{version_id}/canonical")

        assert response.status_code == 200
        body = response.json()
        assert body["total_elements"] == 3
        assert [e["element_id"] for e in body["elements"]] == [e[0] for e in ELEMENTS]

    async def test_source_fragments_are_exposed_for_span_highlighting(self, client) -> None:
        """A reviewer needs the offsets to highlight the span on the source."""

        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/canonical")).json()

        fragment = body["elements"][1]["source_fragments"][0]
        assert fragment["start_offset"] == 0
        assert fragment["end_offset"] == len(ELEMENTS[1][2])

    async def test_paging_is_bounded(self, client) -> None:
        """A large handbook would otherwise be a way to hang a browser."""

        http, version_id, _ = client
        assert (
            await http.get(f"/api/extraction/{version_id}/canonical?limit=5000")
        ).status_code == 422

    async def test_paging_returns_a_window(self, client) -> None:
        http, version_id, _ = client
        body = (
            await http.get(f"/api/extraction/{version_id}/canonical?offset=1&limit=1")
        ).json()

        assert len(body["elements"]) == 1
        assert body["elements"][0]["element_id"] == ELEMENTS[1][0]
        assert body["total_elements"] == 3

    async def test_an_unknown_version_is_404_not_empty(self, client) -> None:
        """An empty list would read as 'this document has no content'."""

        http, _, _ = client
        assert (
            await http.get(f"/api/extraction/{uuid.uuid4()}/canonical")
        ).status_code == 404


class TestStructure:
    async def test_structure_is_recomputed_from_the_elements(self, client) -> None:
        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/structure")).json()

        assert body["node_count"] == 3
        assert body["edge_count"] > 0
        assert set(body["leaf_element_ids"]) == {ELEMENTS[1][0], ELEMENTS[2][0]}

    async def test_edges_carry_their_kind(self, client) -> None:
        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/structure")).json()

        kinds = {edge["kind"] for edge in body["edges"]}
        assert "precedes" in kinds
        assert "parent_heading" in kinds


class TestReadingPlan:
    async def test_units_expose_their_dependency_reasons(self, client) -> None:
        """'Why did the model see this alongside that rule' is the first
        question asked about a wrong extraction."""

        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/reading-plan")).json()

        assert body["is_exhaustive"] is True
        assert body["uncovered_target_ids"] == []
        reasons = {c["reason"] for unit in body["units"] for c in unit["context"]}
        assert "ancestor_heading" in reasons


class TestCoverage:
    async def test_every_leaf_has_a_disposition(self, client) -> None:
        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/coverage")).json()

        assert body["is_complete"] is True
        assert body["unaccounted_element_ids"] == []
        assert body["accounted"] == body["total_leaf_elements"]

    async def test_dispositions_carry_their_reason(self, client) -> None:
        http, version_id, _ = client
        body = (await http.get(f"/api/extraction/{version_id}/coverage")).json()

        assert all(entry["reason"] for entry in body["elements"])


class TestStages:
    async def test_stages_are_listed_for_a_version(self, client) -> None:
        http, version_id, maker = client

        async with maker() as session:
            session.add(
                ExtractionStage(
                    document_version_id=version_id,
                    idempotency_key="k" * 64,
                    stage_name="docling_converted",
                    sequence=1,
                    status="ok",
                    detail="3 elements",
                )
            )
            await session.commit()

        body = (await http.get(f"/api/extraction/{version_id}/stages")).json()

        assert len(body["stages"]) == 1
        assert body["stages"][0]["stage_name"] == "docling_converted"

    async def test_stages_can_be_scoped_to_one_run(self, client) -> None:
        http, version_id, maker = client

        async with maker() as session:
            for key in ("k" * 64, "j" * 64):
                session.add(
                    ExtractionStage(
                        document_version_id=version_id,
                        idempotency_key=key,
                        stage_name="converted",
                        sequence=1,
                    )
                )
            await session.commit()

        body = (
            await http.get(f"/api/extraction/{version_id}/stages?idempotency_key={'k' * 64}")
        ).json()

        assert len(body["stages"]) == 1


class TestSurfaceDiscipline:
    async def test_the_router_is_read_only(self, client) -> None:
        """An endpoint that could mutate a canonical artifact would break the
        one guarantee the artifact exists to provide."""

        from policy_platform.api.routers import extraction

        methods = {
            method
            for route in extraction.router.routes
            for method in getattr(route, "methods", set())
        }
        assert methods <= {"GET", "HEAD", "OPTIONS"}

    async def test_no_review_or_approval_endpoints_are_duplicated(self) -> None:
        """The directive forbids a second review, approval or publication
        subsystem beside the application's own."""

        from policy_platform.api.routers import extraction

        paths = {getattr(route, "path", "") for route in extraction.router.routes}
        for forbidden in ("approve", "reject", "publish", "activate", "review"):
            assert not any(forbidden in path for path in paths)

    async def test_conversion_is_not_exposed_as_a_live_call(self) -> None:
        """A 53-page PDF takes minutes, and re-converting would produce a new
        artifact behind spans already stored against the old one."""

        from policy_platform.api.routers import extraction

        paths = {getattr(route, "path", "") for route in extraction.router.routes}
        assert not any("convert" in path for path in paths)
