"""One module owns the case decider, and the reviewer route still writes nothing.

TWO CLAIMS, AND WHY BOTH HAVE TO BE HELD IN CODE

The project-case decider now has two callers with opposite consequences: the
reviewer surface answers and persists nothing, and the external contract answers
and writes an audited receipt. That arrangement fails in two specific ways, and
prose in a docstring prevents neither.

**A third caller.** The next endpoint that wants a case answer will reach for
`ai_case_project.answer_project_case` directly, because it is right there and it
works. What it would skip is the receipt — quietly reintroducing exactly the gap
the external contract was built to close. So the call sites are counted, and
there is exactly one.

**A changed reviewer route.** The delegation was supposed to be
behaviour-preserving. "Supposed to be" is not a property; it is an intention,
and the whole risk of routing an existing endpoint through new code is that its
response or its side effects change by a little. So the legacy route's top-level
shape is pinned, and so is the fact that it writes no receipt row — because a
reviewer clicking "Test a Case" is exploring, not producing a governed decision
record, and turning every such click into one would misfile the exploration and
inflate the audit log with it.
"""
from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import ai as ai_router  # noqa: E402
from policy_platform.application import policy_case_decision  # noqa: E402
from policy_platform.domain.models import Base, PolicyCaseDecision, PolicySet  # noqa: E402
from policy_platform.infrastructure.assistants import ai_case_intent, ai_case_project  # noqa: E402
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from tests.fixtures.language_boundary import install_language_boundary  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SRC = Path(__file__).resolve().parents[2] / "src" / "policy_platform"

#: The only module permitted to invoke the decider. Named as a path rather than
#: as an import so the guard reads the source tree rather than trusting an
#: import graph that a lazy import could hide from it.
DECIDER_OWNER = SRC / "application" / "policy_case_decision.py"

DECIDER_FUNCTION = "answer_project_case"
DECIDER_MODULE = "ai_case_project"


def _call_sites(path: Path) -> list[int]:
    """Line numbers where `ai_case_project.answer_project_case(...)` is called.

    Matched on the attribute call rather than on the text `answer_project_case`,
    so a docstring mentioning the name — several do, deliberately — is not
    counted, and neither is the identically named *route handler* in `ai.py` or
    the identically named delegating function in the application module.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == DECIDER_FUNCTION
            and isinstance(func.value, ast.Name)
            and func.value.id == DECIDER_MODULE
        ):
            lines.append(node.lineno)
    return lines


def test_exactly_one_module_calls_the_project_case_decider() -> None:
    """The invariant that keeps "one decider" true of the source, not the prose.

    A second call site is not a style problem: it is a path to a verdict that
    was never recorded, which is the defect the audited contract exists to fix.
    """

    offenders: dict[str, list[int]] = {}
    total = 0
    scanned = 0

    for path in sorted(SRC.rglob("*.py")):
        scanned += 1
        sites = _call_sites(path)
        if not sites:
            continue
        total += len(sites)
        if path != DECIDER_OWNER:
            offenders[str(path.relative_to(SRC))] = sites

    assert scanned > 50, f"only scanned {scanned} modules; the walk is broken"
    assert not offenders, (
        f"{DECIDER_MODULE}.{DECIDER_FUNCTION} may only be called from "
        f"{DECIDER_OWNER.name}, which reserves and finalises the decision receipt. "
        f"Found other call sites: {offenders}"
    )
    assert total == 1, (
        f"expected exactly one call site in {DECIDER_OWNER.name}, found {total}. "
        "Two calls inside the owner is not a correctness problem, but it is how the "
        "count stops meaning anything — funnel them through one helper."
    )


def test_the_guard_would_notice_a_second_call_site(tmp_path: Path) -> None:
    """A detector that has never been shown to fire is not a detector.

    The assertion above passes on an empty scan and on a broken parser alike, so
    the matcher is exercised directly against source it must and must not flag.
    """

    offending = tmp_path / "offender.py"
    offending.write_text(
        "from policy_platform.infrastructure.assistants import ai_case_project\n"
        "async def go(s, p):\n"
        "    return await ai_case_project.answer_project_case(s, policy_set=p, scenario='x')\n",
        encoding="utf-8",
    )
    assert _call_sites(offending) == [3]

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        '"""Mentions ai_case_project.answer_project_case in prose only."""\n'
        "async def answer_project_case(session, **kw):\n"
        "    return {}\n",
        encoding="utf-8",
    )
    assert _call_sites(innocent) == []


# ── the reviewer route, unchanged ────────────────────────────────────

#: The exact top-level keys the project-scope reviewer response has always
#: carried. Pinned as a set: an added key would break a consumer that iterates,
#: and a removed one breaks every consumer.
#:
#: `language` joined it when the reviewer route began crossing the same language
#: boundary the audited contract does. It is the one addition, it is additive,
#: and it is pinned here rather than tolerated so a second one cannot arrive
#: unnoticed.
LEGACY_PROJECT_KEYS = {
    "scope",
    "policy_set_key",
    "retrieval",
    "considered",
    "excluded",
    "evaluation",
    "size",
    "language",
}

_SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000d0001")
_LEGACY_KEY = "legacy-reviewer"


class _Settings:
    """Only the two flags the legacy route and the decider read on this path."""

    ai_enabled = True
    search_enabled = False
    azure_openai_deployment = "unused"


@pytest.fixture
async def legacy_client(monkeypatch):
    """The real legacy route over a real database, with retrieval switched off.

    `search_enabled = False` puts the decider on its `unavailable` branch, which
    reaches no network at all and still exercises the full route → application →
    decider path this test is about.
    """

    settings = _Settings()
    monkeypatch.setattr(ai_router, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_case_project, "get_settings", lambda: settings)
    # The reviewer route crosses the language boundary too. Left at its identity
    # default so every assertion below means what it meant before, and so this
    # fixture reaches no network.
    install_language_boundary(monkeypatch)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(PolicySet(id=_SET_ID, key=_LEGACY_KEY, name="Legacy Reviewer", owner="policy"))
        await session.commit()

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, maker
    await engine.dispose()


async def test_the_reviewer_route_keeps_its_exact_response_shape(legacy_client) -> None:
    """The delegation changed where the code lives, not what the route returns."""

    client, _ = legacy_client
    response = await client.post(
        f"/api/ai/policy-sets/{_LEGACY_KEY}/case-answer",
        json={"scenario": "what does the project provide on this?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == LEGACY_PROJECT_KEYS
    assert body["scope"] == ai_case_project.SCOPE_PROJECT
    assert body["policy_set_key"] == _LEGACY_KEY
    # No receipt fields leaked back into the reviewer's response.
    for added in ("decision_id", "decision_hash", "receipt_url", "schema_version", "correlation_id"):
        assert added not in body


async def test_the_reviewer_route_writes_no_decision_receipt(legacy_client) -> None:
    """A reviewer testing a case is not an external system asking for a decision.

    Recording one would misfile exploration as a governed decision record, and
    would fill the audit log with every click of "Test a Case".
    """

    client, maker = legacy_client

    for _ in range(3):
        response = await client.post(
            f"/api/ai/policy-sets/{_LEGACY_KEY}/case-answer",
            json={"scenario": "asked three times over"},
        )
        assert response.status_code == 200

    async with maker() as session:
        rows = list((await session.execute(select(PolicyCaseDecision))).scalars().all())
    assert rows == [], "the reviewer route wrote a decision receipt"


async def test_the_reviewer_route_still_maps_an_unknown_project_to_404(legacy_client) -> None:
    """The error contract is part of the shape, and it did not move either."""

    client, _ = legacy_client
    response = await client.post(
        "/api/ai/policy-sets/no-such-project/case-answer", json={"scenario": "anything"}
    )
    assert response.status_code == 404


async def test_the_decider_default_return_is_still_a_bare_dict(monkeypatch) -> None:
    """The additive context is opt-in, so nothing existing sees a new type.

    `with_context=True` returns a result object carrying the version the decider
    loaded; every caller that does not ask keeps receiving the same dict, which
    is what lets the reviewer route delegate without changing.
    """

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return {
            "has_published_version": False,
            "active_version_id": None,
            "active_version_number": None,
            "candidates": [],
            "excluded": [],
        }

    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)

    class _Project:
        id = "set-1"
        key = "k"

    plain = await ai_case_project.answer_project_case(
        object(), policy_set=_Project(), scenario="a question"
    )
    assert isinstance(plain, dict)
    assert plain["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_PUBLISHED_VERSION

    with_context = await ai_case_project.answer_project_case(
        object(), policy_set=_Project(), scenario="a question", with_context=True
    )
    assert isinstance(with_context, ai_case_project.ProjectCaseAnswer)
    assert with_context.response == plain
    # A project with nothing published has no version, and the context says so
    # rather than omitting the fact.
    assert with_context.context["policy_version_id"] is None
    assert with_context.context["version_source"] == "project_scope_no_published_version"


async def test_the_application_module_answers_the_reviewer_path_without_persisting(monkeypatch) -> None:
    """The delegating function is the decider's dict, plus the language block.

    Held directly, not only through the route, so a future change that starts
    persisting here would fail with a message about *this* function rather than
    about an endpoint three layers away.

    The one addition to the dict is `language`, and it is asserted rather than
    tolerated: the reviewer route crosses the same boundary the audited contract
    does, and a reviewer must be able to see which text was actually adjudicated.
    """

    seen: dict[str, Any] = {}

    async def _decider(session, **kwargs):
        seen.update(kwargs)
        return {"scope": "project", "evaluation": None}

    monkeypatch.setattr(ai_case_project, "answer_project_case", _decider)
    install_language_boundary(monkeypatch)

    class _Project:
        id = "set-1"
        key = "k"

    result = await policy_case_decision.answer_project_case(
        object(), policy_set=_Project(), scenario="a question", reasoning_effort="low"
    )

    assert {key: value for key, value in result.items() if key != "language"} == {
        "scope": "project",
        "evaluation": None,
    }
    assert result["language"]["processing_language"] == "en"
    assert result["language"]["processing_scenario"] == "a question"
    assert seen["with_context"] is False, "the reviewer path must not ask for the audited context"
    assert seen["additional_instructions"] == "", (
        "the reviewer route must pass empty caller guidance: none of the machinery that makes "
        "guidance safe on the external contract — normalisation, the length bound, the idempotency "
        "binding, the seal, the receipt — exists on this route"
    )
    assert seen["scenario"] == "a question"
    assert seen["reasoning_effort"] == "low"


async def test_the_reviewer_route_takes_no_guidance_parameter() -> None:
    """The absence is the design, so it is asserted rather than assumed.

    A future edit that adds `additional_instructions` to this function would
    give the reviewer route an unbounded, unrecorded influence on an answer
    nobody can reconstruct afterwards. That is a decision someone should have to
    make on purpose, and this is what makes them.
    """

    import inspect

    parameters = inspect.signature(policy_case_decision.answer_project_case).parameters
    assert "additional_instructions" not in parameters


def test_the_track_statuses_named_by_the_contract_are_the_gathers_own() -> None:
    """Each track's vocabulary is the gather's, and the two are not the same set.

    If `ai_case_intent` grew a status the envelope did not know, the projection
    would silently record it as `failed` — a real answer reported as a fault.
    This fails instead, at the moment the vocabularies diverge.

    The two sets are asserted apart because they genuinely differ: only a verdict
    can be blocked on missing facts or left unsettled by the rules, and an
    information track that could report `missing_required_facts` would be asking
    the reviewer to supply the very thing they asked the policy to state — the
    original defect the informational branch was written to fix.
    """

    from policy_platform.application.policy_case_decision import (
        _KNOWN_INFORMATION_STATUSES,
        _KNOWN_VERDICT_STATUSES,
    )

    assert _KNOWN_INFORMATION_STATUSES == {
        ai_case_intent.ANSWERED,
        ai_case_intent.NO_RULE_BEARS,
        ai_case_intent.DECLINED,
        ai_case_intent.FAILED,
    }
    assert _KNOWN_VERDICT_STATUSES == {
        ai_case_intent.ANSWERED,
        ai_case_intent.MISSING_REQUIRED_FACTS,
        ai_case_intent.NOT_SETTLED_BY_RULES,
        ai_case_intent.NO_RULE_BEARS,
        ai_case_intent.DECLINED,
        ai_case_intent.FAILED,
    }
    # The information vocabulary is a strict subset, never a separate invention.
    assert _KNOWN_INFORMATION_STATUSES < _KNOWN_VERDICT_STATUSES
