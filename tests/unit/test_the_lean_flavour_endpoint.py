"""The lean-flavour endpoint serves the projection and separates its states.

Thin by design — the projection is tested directly elsewhere — so what this
pins is the wiring: the route is reachable off the blocked `/policies` prefix,
an existing policy comes back as the lean flavour, and the three answers a
caller must tell apart (a policy, no such policy, a malformed id) stay distinct
status codes rather than collapsing into one.
"""
from __future__ import annotations

import os
import uuid

import pytest

# `api.app` builds an application at import time, and `Settings` needs a URL.
# Set before the import so collection does not depend on a local .env; the URL
# is never connected to, because the session dependency is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.contracts.conditions import AllCondition  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    Base,
    CandidateRule,
    DocumentProvision,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
_VERSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e2")
_RUN_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e3")
_DOC_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e4")
_PROVISION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e5")
_RULE_IDS = ("AI-endpoint01", "AI-endpoint02")


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(PolicySet(id=_SET_ID, key="ep-guard", name="ep-guard", owner="guard"))
        session.add(SourceDocument(id=_DOC_ID, title="Handbook", owner="guard", policy_set_id=_SET_ID))
        session.add(
            DocumentVersion(
                id=_VERSION_ID,
                document_id=_DOC_ID,
                version_number=1,
                content_hash="c" * 64,
                storage_path="/handbook.pdf",
            )
        )
        session.add(ExtractionRun(id=_RUN_ID, document_version_id=_VERSION_ID, status="succeeded"))
        session.add(
            DocumentProvision(
                id=_PROVISION_ID,
                policy_set_id=_SET_ID,
                document_version_id=_VERSION_ID,
                provision_key="ep-key",
                heading_path_json=["A Heading The Document Wrote"],
                heading_element_ids_json=["E000050"],
                first_sequence=0,
            )
        )
        for index, rule_id in enumerate(_RULE_IDS, start=1):
            session.add(
                CandidateRule(
                    id=uuid.UUID(int=index),
                    policy_set_id=_SET_ID,
                    extraction_run_id=_RUN_ID,
                    provision_id=_PROVISION_ID,
                    rule_type="obligation",
                    review_status="candidate",
                    delta_status="new",
                    payload_json=make_rule(rule_id, AllCondition(all=[])).model_dump(mode="json"),
                )
            )
        await session.commit()

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await engine.dispose()


async def test_the_endpoint_returns_the_lean_flavour_for_a_known_provision(client) -> None:
    response = await client.get(f"/api/policy-payload/{_PROVISION_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["flavor"] == "lean"
    assert body["representation"] == "canonical"
    assert body["provision_id"] == str(_PROVISION_ID)
    assert {rule["rule_id"] for rule in body["rules"]} == set(_RULE_IDS)


async def test_an_unknown_provision_is_a_404_not_an_empty_200(client) -> None:
    missing = uuid.UUID("00000000-0000-4000-8000-0000000000ee")

    response = await client.get(f"/api/policy-payload/{missing}")

    assert response.status_code == 404


async def test_a_malformed_provision_id_is_a_422(client) -> None:
    response = await client.get("/api/policy-payload/not-a-uuid")

    assert response.status_code == 422
