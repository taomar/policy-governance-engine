"""Publishing a version re-runs the policy's active guards and records each run.

WHY THIS TEST EXISTS

A guard is a `PolicyTest` a reviewer kept as a standing check: once active, it is
meant to re-run automatically against every future published version, so a later
edit that changes an answer surfaces as a failing run instead of going unnoticed.
The whole value of that promise is that it fires *without anyone asking* — which
is exactly the kind of capability this repository has shipped before as wired but
reaching nobody (handover Section 4.1, its most-logged failure).

The on-publish re-run hook lives in `publish_approved_candidates`
(`candidate_rules.py`), calls `run_active_tests_for_version`, and works today. But
"works today" is not "stays working": nothing here fails if a refactor drops the
call, neuters the `is_active` filter, or stops recording the run. These tests are
that missing net. They drive the *real* publish endpoint over an in-memory
database — the real version import, the real hook — and assert the observable
promise:

* an active guard produces a recorded `PolicyTestRun` marked ``on_publish``,
  attributed to the publisher and tied to the version just published; and
* a retired guard (``is_active=False``) produces none — the gate that decides
  which guards re-run is pinned, not assumed.

The run's pass/fail is deliberately not asserted: that is the evaluator's job and
is tested where the evaluator is tested. What is pinned here is the *wiring* — that
publishing reaches the guard at all. Proven red by neutering the hook, so the test
is known to detect the regression it guards against rather than passing vacuously.
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

# `api.app` builds an application at import time, and `Settings` needs a URL. Set
# before the import so collection does not depend on a local .env; the URL is
# never connected to, because the session dependency is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import candidate_rules as candidate_rules_router  # noqa: E402
from policy_platform.contracts.conditions import AllCondition  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    Base,
    CandidateRule,
    DocumentProvision,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    PolicyIndexState,
    PolicyTest,
    PolicyTestRun,
    SourceDocument,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from policy_platform.infrastructure.search.policy_index import PolicyIndexBuildOutcome, policy_index_name  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000a001")
_VERSION_ID = uuid.UUID("00000000-0000-4000-8000-00000000a002")
_RUN_ID = uuid.UUID("00000000-0000-4000-8000-00000000a003")
_DOC_ID = uuid.UUID("00000000-0000-4000-8000-00000000a004")
_PROVISION_ID = uuid.UUID("00000000-0000-4000-8000-00000000a005")
_ACTIVE_TEST_ID = uuid.UUID("00000000-0000-4000-8000-00000000a006")
_RETIRED_TEST_ID = uuid.UUID("00000000-0000-4000-8000-00000000a007")
_CANDIDATE_ID = uuid.UUID("00000000-0000-4000-8000-00000000a008")

_KEY = "guard-rerun"
_RULE_ID = "AI-guard-rerun01"
_PUBLISHER = "reviewer@example.test"


def _guard(test_id: uuid.UUID, *, is_active: bool, name: str) -> PolicyTest:
    """A minimal, valid `PolicyTest` for this policy set.

    The expected status is a well-formed `EvaluationStatus`; the run's actual
    pass/fail is the evaluator's concern and is not what these tests assert.
    """

    return PolicyTest(
        id=test_id,
        policy_set_id=_SET_ID,
        name=name,
        description="",
        test_kind="positive",
        input_facts_json={},
        expected_overall_status="NOT_APPLICABLE",
        scenario_text="A saved case kept as a standing check.",
        proposed_by="human",
        review_status="active",
        is_active=is_active,
    )


@pytest.fixture
async def published(monkeypatch):
    """A real app over in-memory SQLite with one approved, unpublished candidate
    and two guards seeded: one active, one retired. The publish request travels
    the real endpoint and the real on-publish hook. Yields the HTTP client and
    the sessionmaker so a test can read what the publish recorded."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(PolicySet(id=_SET_ID, key=_KEY, name=_KEY, owner="guard"))
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
                provision_key="guard-rerun-key",
                heading_path_json=["A Heading The Document Wrote"],
                heading_element_ids_json=["E000050"],
                first_sequence=0,
            )
        )
        # An approved, never-published candidate: the one thing a publish needs to
        # mint a new version. `review_status="approved"` + `published_version_id`
        # still null is exactly what `publish_approved_candidates` selects.
        rule = make_rule(_RULE_ID, AllCondition(all=[]))
        session.add(
            CandidateRule(
                id=_CANDIDATE_ID,
                policy_set_id=_SET_ID,
                extraction_run_id=_RUN_ID,
                provision_id=_PROVISION_ID,
                rule_type="obligation",
                review_status="approved",
                delta_status="new",
                payload_json=rule.model_dump(mode="json"),
            )
        )
        session.add(_guard(_ACTIVE_TEST_ID, is_active=True, name="Active guard"))
        session.add(_guard(_RETIRED_TEST_ID, is_active=False, name="Retired guard"))
        await session.commit()

    async def _fake_rebuild_project_policy_index(*, policy_set_key, version_number, projections, **_kw):
        projection_list = list(projections)
        return PolicyIndexBuildOutcome(
            state="built",
            policy_set_key=policy_set_key,
            index_name=policy_index_name(policy_set_key),
            version_number=version_number,
            document_count=len(projection_list),
            indexed_at="2026-08-18T12:00:00+00:00",
        )

    monkeypatch.setattr(
        candidate_rules_router,
        "rebuild_project_policy_index",
        _fake_rebuild_project_policy_index,
    )

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, maker
    await engine.dispose()


async def _runs_for(maker, test_id: uuid.UUID) -> list[PolicyTestRun]:
    async with maker() as session:
        rows = (
            await session.execute(
                select(PolicyTestRun).where(PolicyTestRun.policy_test_id == test_id)
            )
        ).scalars().all()
        return list(rows)


async def test_publishing_reruns_the_active_guard_and_records_an_on_publish_run(published) -> None:
    """The promise, end to end: publish a version and the policy's active guard
    has a fresh `PolicyTestRun` marked ``on_publish``, attributed to the
    publisher and tied to the version just minted. Before the publish there is
    nothing; the run exists only because publishing created it."""

    http, maker = published

    # Nothing has run yet: the guard exists but has never executed. This is the
    # "exists, never run" state, distinct from "no guard" and from "has run".
    assert await _runs_for(maker, _ACTIVE_TEST_ID) == []

    response = await http.post(
        f"/api/policy-sets/{_KEY}/publish",
        json={"approved_by": _PUBLISHER, "effective_from": date(2024, 1, 1).isoformat(), "is_active": True},
    )

    assert response.status_code == 201
    version_id = response.json()["id"]

    runs = await _runs_for(maker, _ACTIVE_TEST_ID)
    # Exactly one run, and it is the publish's doing: the trigger says so, the
    # attribution is the publisher, and it is bound to the version just created.
    assert len(runs) == 1
    run = runs[0]
    assert run.run_trigger == "on_publish"
    assert run.triggered_by == _PUBLISHER
    assert str(run.policy_version_id) == version_id


async def test_publishing_reports_and_persists_policy_index_rebuild_outcome(published) -> None:
    """Publishing must leave an operator-visible index outcome, not a silent stale index."""

    http, maker = published

    response = await http.post(
        f"/api/policy-sets/{_KEY}/publish",
        json={"approved_by": _PUBLISHER, "effective_from": date(2024, 1, 1).isoformat(), "is_active": True},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["policy_index_build"] == {
        "state": "built",
        "policy_set_key": _KEY,
        "index_name": policy_index_name(_KEY),
        "version_number": 1,
        "document_count": 1,
        "indexed_at": "2026-08-18T12:00:00Z",
        "error": None,
        # The double below does not build documents, so the split is zero and no
        # rendering contract is claimed. What is asserted here is that publish
        # reports the whole outcome shape rather than a subset of it — a caller
        # reading "built" needs to be able to see whether the corpus is actually
        # matchable, and these four fields are where that is said.
        "policy_document_count": 0,
        "rule_document_count": 0,
        "projection_profile": None,
        "manifest_state": None,
        # The double uploads nothing, so no corpus was validated and there is no
        # verdict to report. `None` is that absence stated: it is distinct from a
        # recorded `unavailable`, which would claim a validation was attempted.
        "quality": None,
    }

    async with maker() as session:
        state = (await session.execute(select(PolicyIndexState))).scalar_one()
        assert state.index_name == policy_index_name(_KEY)
        assert state.indexed_version_number == 1
        assert state.document_count == 1
        assert state.status == "built"


async def test_publishing_does_not_rerun_a_retired_guard(published) -> None:
    """The gate that decides which guards re-run is `is_active`, and it is real:
    a retired guard is kept but excluded, so publishing records nothing for it
    while the active guard beside it does run. A refactor that re-ran every test
    regardless of `is_active` would turn retired guards back into live noise;
    this pins the filter so that regression is caught."""

    http, maker = published

    response = await http.post(
        f"/api/policy-sets/{_KEY}/publish",
        json={"approved_by": _PUBLISHER, "effective_from": date(2024, 1, 1).isoformat(), "is_active": True},
    )
    assert response.status_code == 201

    # The active guard ran; the retired one did not. Both facts together prove
    # the publish reached the guards and honoured the gate rather than skipping
    # the hook wholesale.
    assert len(await _runs_for(maker, _ACTIVE_TEST_ID)) == 1
    assert await _runs_for(maker, _RETIRED_TEST_ID) == []


async def test_on_publish_run_is_the_only_run_recorded(published) -> None:
    """A single publish records exactly one run in the whole table — the active
    guard's — so "the guard has a run" cannot be an artifact of some other write
    path recording runs behind the scenes. One publish, one guard, one run."""

    http, maker = published

    await http.post(
        f"/api/policy-sets/{_KEY}/publish",
        json={"approved_by": _PUBLISHER, "effective_from": date(2024, 1, 1).isoformat(), "is_active": True},
    )

    async with maker() as session:
        total = (await session.execute(select(func.count()).select_from(PolicyTestRun))).scalar_one()
    assert total == 1
