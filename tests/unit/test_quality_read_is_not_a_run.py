"""Reading a quality result is not the same act as producing one.

Both quality endpoints used to evaluate on GET: opening the Quality page spent
minutes of model time and appended a row to the evaluation history. That history
is the only thing that answers "is this policy set improving?" -- the page says
so in its own words -- so a page load was silently writing into the record it
asked the reader to interpret. Two reads minutes apart returned 34 and 32
findings, naming the same underlying problem differently each time.

The property under test is behavioural: a GET must leave the number of stored
runs exactly as it found it, and must not reach the model. Asserting that a
particular function is no longer called would pass again the moment someone
inlines it.

The second property is that "nothing has been evaluated" survives the API
boundary. An empty findings list would be read as a clean bill of health, which
is the opposite conclusion from "nobody has looked yet".
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

# `api.app` builds an application at import time and `Settings` requires a
# database URL. Set before the import so collection does not depend on a
# developer's local .env -- the URL is never connected to, because every session
# is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import ai as ai_router  # noqa: E402
from policy_platform.contracts.conditions import (  # noqa: E402
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.domain.models import (  # noqa: E402
    CandidateRule,
    PolicySet,
    QualityRun,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from policy_platform.infrastructure.quality import ai_quality  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


POLICY_SET_KEY = "quality-contract"

#: Distinctive enough that a fresh evaluation could not produce it by accident,
#: so "the stored run came back" is provable rather than plausible.
STORED_FINDING = {
    "severity": "high",
    "category": "stored_marker",
    "finding": "Recorded by the seeded run, not by anything this request did.",
    "affected_rule_ids": [],
    "recommendation": "",
    "source": "deterministic",
}


class _Settings:
    """AI switched on, so a GET that still evaluated would reach the client."""

    ai_enabled = True
    azure_openai_deployment = "test-deployment"


@pytest.fixture
async def client(monkeypatch):
    """A real app over in-memory SQLite, with one empty policy set seeded.

    AI is reported as configured and the client is replaced by one that records
    every call, so "no model call happened" is measured rather than assumed --
    an AI-disabled environment would make that assertion vacuous.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            PolicySet.__table__,
            QualityRun.__table__,
            CandidateRule.__table__,
        ):
            await connection.run_sync(lambda c, t=table: t.create(c, checkfirst=True))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    policy_set_id = uuid.uuid4()
    async with maker() as session:
        session.add(
            PolicySet(id=policy_set_id, key=POLICY_SET_KEY, name="Quality contract", owner="qa")
        )
        await session.commit()

    chat_calls: list[dict] = []

    class _RecordingClient:
        def __init__(self, settings) -> None:
            pass

        async def chat(self, messages, **kwargs) -> str:
            chat_calls.append(kwargs)
            return '{"findings": []}'

    monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_quality, "AzureOpenAIClient", _RecordingClient)
    monkeypatch.setattr(ai_router, "get_settings", lambda: _Settings())

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client, maker, policy_set_id, chat_calls

    await engine.dispose()


async def _run_count(maker, policy_set_id: uuid.UUID) -> int:
    async with maker() as session:
        result = await session.execute(
            select(func.count()).select_from(QualityRun).where(
                QualityRun.policy_set_id == policy_set_id
            )
        )
        return int(result.scalar_one())


async def _seed_run(maker, policy_set_id: uuid.UUID, scope: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with maker() as session:
        session.add(
            QualityRun(
                id=run_id,
                policy_set_id=policy_set_id,
                scope=scope,
                version_number=7 if scope == "published" else None,
                rule_count=3,
                high_count=1,
                medium_count=0,
                low_count=0,
                ai_review_used=True,
                methodology_version="2",
                findings_json=[STORED_FINDING],
                triggered_by="",
                run_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    return run_id


async def _seed_candidate(maker, policy_set_id: uuid.UUID) -> None:
    """One reviewable candidate, so a review has something to review.

    `extraction_run_id` points at nothing: SQLite does not enforce foreign keys
    unless asked to, and building a document/version/run chain would add fixture
    surface that says nothing about the contract under test.
    """

    rule = make_rule(
        "R1", FactComparisonCondition(fact="amount", operator=ConditionOperator.EXISTS, value=None)
    )
    async with maker() as session:
        session.add(
            CandidateRule(
                extraction_run_id=uuid.uuid4(),
                policy_set_id=policy_set_id,
                rule_type=rule.rule_type.value,
                payload_json=rule.model_dump(mode="json"),
                review_status="candidate",
            )
        )
        await session.commit()


class TestReadingDoesNotEvaluate:
    """The defect itself: a GET wrote a row and spent a model call."""

    @pytest.mark.parametrize(
        "path,scope",
        [
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality", "published"),
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality", "candidates"),
        ],
    )
    async def test_a_read_appends_nothing_to_the_history(self, client, path, scope) -> None:
        http, maker, policy_set_id, _ = client
        await _seed_run(maker, policy_set_id, scope)
        before = await _run_count(maker, policy_set_id)

        for _ in range(3):
            assert (await http.get(path)).status_code == 200

        assert await _run_count(maker, policy_set_id) == before == 1

    @pytest.mark.parametrize(
        "path,scope",
        [
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality", "published"),
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality", "candidates"),
        ],
    )
    async def test_a_read_never_reaches_the_model(self, client, path, scope) -> None:
        """Cost, not just correctness: this call took ~2 minutes on 273 rules."""

        http, maker, policy_set_id, chat_calls = client
        await _seed_run(maker, policy_set_id, scope)
        # Something for a review to review, so an evaluating GET would visibly
        # call out rather than returning early with nothing to do.
        await _seed_candidate(maker, policy_set_id)

        assert (await http.get(path)).status_code == 200

        assert chat_calls == []

    @pytest.mark.parametrize(
        "path,scope",
        [
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality", "published"),
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality", "candidates"),
        ],
    )
    async def test_a_read_returns_the_run_that_was_recorded(self, client, path, scope) -> None:
        """Not merely "some report" -- the stored one, unchanged."""

        http, maker, policy_set_id, _ = client
        run_id = await _seed_run(maker, policy_set_id, scope)

        body = (await http.get(path)).json()

        assert body["evaluated"] is True
        assert body["quality_run_id"] == str(run_id)
        assert body["scope"] == scope
        assert body["findings"] == [STORED_FINDING]
        assert body["finding_count"] == 1

    async def test_the_latest_run_is_the_one_returned(self, client) -> None:
        http, maker, policy_set_id, _ = client
        await _seed_run(maker, policy_set_id, "published")
        newest = await _seed_run(maker, policy_set_id, "published")

        body = (await http.get(f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality")).json()

        assert body["quality_run_id"] == str(newest)

    async def test_each_scope_reads_its_own_runs(self, client) -> None:
        """A candidate run must not be served as the published version's result."""

        http, maker, policy_set_id, _ = client
        await _seed_run(maker, policy_set_id, "candidates")

        published = (await http.get(f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality")).json()

        assert published["evaluated"] is False


class TestNotEvaluatedIsNotTheSameAsClean:
    """The distinction has to survive the API boundary, not just the service."""

    @pytest.mark.parametrize(
        "path,scope",
        [
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality", "published"),
            (f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality", "candidates"),
        ],
    )
    async def test_an_unevaluated_scope_says_so_explicitly(self, client, path, scope) -> None:
        http, _, _, _ = client

        response = await http.get(path)

        assert response.status_code == 200
        body = response.json()
        assert body["evaluated"] is False
        assert body["scope"] == scope
        assert body["detail"]

    @pytest.mark.parametrize(
        "path",
        [
            f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality",
            f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality",
        ],
    )
    async def test_findings_are_null_rather_than_an_empty_list(self, client, path) -> None:
        """`[]` is what a completed evaluation of a sound policy set returns.

        Serving it for "never evaluated" would let a reader conclude the policy
        set had been examined and found clean.
        """

        http, _, _, _ = client

        body = (await http.get(path)).json()

        assert body["findings"] is None
        assert body["finding_count"] is None
        assert body["rule_count"] is None
        assert body["run_at"] is None

    async def test_a_completed_evaluation_that_found_nothing_is_distinguishable(
        self, client
    ) -> None:
        """The other side of the same distinction, so the check above means something."""

        http, maker, policy_set_id, _ = client
        run_id = uuid.uuid4()
        async with maker() as session:
            session.add(
                QualityRun(
                    id=run_id,
                    policy_set_id=policy_set_id,
                    scope="published",
                    version_number=2,
                    rule_count=12,
                    high_count=0,
                    medium_count=0,
                    low_count=0,
                    ai_review_used=True,
                    methodology_version="2",
                    findings_json=[],
                    triggered_by="",
                    run_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        body = (await http.get(f"/api/ai/policy-sets/{POLICY_SET_KEY}/quality")).json()

        assert body["evaluated"] is True
        assert body["findings"] == []
        assert body["finding_count"] == 0
        assert body["rule_count"] == 12

    async def test_an_unknown_policy_set_is_still_a_404(self, client) -> None:
        """"Not evaluated" must not absorb "does not exist"."""

        http, _, _, _ = client

        assert (await http.get("/api/ai/policy-sets/no-such-set/quality")).status_code == 404


class TestEvaluatingIsAnExplicitRequest:
    """The POST is what costs money and writes history."""

    async def test_posting_records_exactly_one_run(self, client) -> None:
        http, maker, policy_set_id, _ = client

        response = await http.post(
            f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality/runs"
        )

        assert response.status_code == 200
        assert response.json()["evaluated"] is True
        assert await _run_count(maker, policy_set_id) == 1

    async def test_the_recorded_run_is_what_the_read_then_returns(self, client) -> None:
        """The two halves have to be halves of the same thing."""

        http, _, _, _ = client

        posted = (
            await http.post(f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality/runs")
        ).json()
        read = (
            await http.get(f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality")
        ).json()

        assert posted["quality_run_id"] == read["quality_run_id"]
        assert posted["findings"] == read["findings"]

    async def test_posting_reaches_the_model(self, client) -> None:
        """Guards the read-side assertion: silence there has to mean something."""

        http, maker, policy_set_id, chat_calls = client
        await _seed_candidate(maker, policy_set_id)

        await http.post(f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality/runs")

        assert len(chat_calls) == 1

    async def test_the_review_call_carries_a_fixed_seed(self, client) -> None:
        """The only determinism control this deployment accepts.

        Probed live: `gpt-5.6-sol` rejects `temperature` and `top_p` outright, so
        passing either would turn every review into a caught exception and a
        "review did not complete" finding.
        """

        http, maker, policy_set_id, chat_calls = client
        await _seed_candidate(maker, policy_set_id)

        await http.post(f"/api/ai/policy-sets/{POLICY_SET_KEY}/candidates/quality/runs")

        assert chat_calls[0]["seed"] == ai_quality._AI_REVIEW_SEED
        assert "temperature" not in chat_calls[0]

    async def test_an_unknown_policy_set_is_a_404(self, client) -> None:
        http, _, _, _ = client

        response = await http.post("/api/ai/policy-sets/no-such-set/candidates/quality/runs")

        assert response.status_code == 404
