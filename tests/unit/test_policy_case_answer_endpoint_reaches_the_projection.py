"""The policy-case endpoint reaches the lean projection and grounds to it.

Thin by design -- the projection and the gather are each tested directly
elsewhere -- so what this pins is the *wiring at the HTTP boundary*. A case put
to a provision is projected server-side by ``case_payload_for_provision`` (the
same lean ``grounding_projection_v1`` seam the JSON tab renders), that projected
record is the closed universe the answer may cite, and the states a caller must
tell apart -- an answer, a fabrication refused, a determination the caller must
run, no such provision, a malformed id -- stay distinct rather than collapsing
into one.

WHY THIS TEST EXISTS

Section 4.1 of the handover -- "a capability that works and reaches nobody" --
is this repository's most-logged failure. A gather that grounds perfectly but is
never actually handed the record built from the database would pass every unit
test in ``test_case_intent_is_read_from_the_question`` and still be wired to
nothing. These tests are the end-to-end evidence that the endpoint at
``routers/ai.py`` really calls the seam: the id the answer cites is one the
projection could only have obtained from a *seeded database row*, and an id that
was never seeded is refused by code. So the grounding universe at the HTTP layer
is provably the seam's projection of what is in the database, not a set the
endpoint invented or a bag of rules a client supplied.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest

# `api.app` builds an application at import time, and `Settings` needs a URL. Set
# before the import so collection does not depend on a local .env; the URL is
# never connected to, because the session dependency is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import ai as ai_router  # noqa: E402
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
from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
_VERSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f2")
_RUN_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f3")
_DOC_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f4")
_PROVISION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f5")
#: Both ids are seeded into the database below, so "the answer cited a real rule"
#: is provable: the id it names is one the projection could only have got from a
#: row that exists. Synthetic ids -- nothing here is tuned to any real document.
_RULE_IDS = ("AI-case-endpoint01", "AI-case-endpoint02")
#: An id deliberately never seeded. If the model cites it, the grounding check
#: must refuse it -- a citation to a rule the projection never carried.
_GHOST_ID = "AI-case-endpoint-ghost"

#: The classify call and the informational gather are told apart by the system
#: prompt each is handed; the classifier's opens with this phrase.
_CLASSIFY_MARKER = "sort one question"

_ANSWERING_INFO_REPLY = {
    "bears": True,
    "answer": "The policy states the cap in its own words.",
    "cited_rule_ids": [_RULE_IDS[0]],
    "declined": False,
    "note": "",
}


class _Settings:
    """AI switched on, so the route's gate opens and the gather builds a client
    -- which is the stub below, never a real deployment."""

    ai_enabled = True
    azure_openai_deployment = "slow"


class _StubClient:
    """Stands in for the model at the app boundary. Serves the classify call and
    the informational gather apart by reading which system prompt it was handed,
    so one request can drive both halves without a real deployment."""

    classify_reply: dict[str, Any] = {"intent": "informational", "reasoning": "asks what the policy provides"}
    info_reply: dict[str, Any] = dict(_ANSWERING_INFO_REPLY)

    def __init__(self, settings: Any) -> None:  # noqa: D107 - shape only
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system = messages[0]["content"]
        is_classify = _CLASSIFY_MARKER in system
        reply = type(self).classify_reply if is_classify else type(self).info_reply
        return json.dumps(reply, ensure_ascii=False)


@pytest.fixture
async def client(monkeypatch):
    """A real app over in-memory SQLite, one provision with two rules seeded, and
    the model replaced by a stub. The request travels the real route, the real
    projection seam, and the real gather -- only the model call is stubbed."""

    # The route's gate and the gather's client both read settings; open AI on
    # both so the request reaches the projection rather than the 503.
    monkeypatch.setattr(ai_router, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubClient)
    _StubClient.classify_reply = {"intent": "informational", "reasoning": "asks what the policy provides"}
    _StubClient.info_reply = dict(_ANSWERING_INFO_REPLY)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(PolicySet(id=_SET_ID, key="case-ep", name="case-ep", owner="guard"))
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
                provision_key="case-ep-key",
                heading_path_json=["A Heading The Document Wrote"],
                heading_element_ids_json=["E000050"],
                first_sequence=0,
            )
        )
        for index, rule_id in enumerate(_RULE_IDS, start=1):
            session.add(
                CandidateRule(
                    id=uuid.UUID(int=0xF00 + index),
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


async def test_a_case_reaches_the_projection_and_cites_a_seeded_rule(client) -> None:
    """The endpoint projects the provision server-side and grounds the answer to
    it: the id the answer cites is one the projection built from a seeded row, so
    the record the model was tested against is provably the seam's -- not a bag of
    client-supplied rules, and not the full 495 KB record."""

    response = await client.post(
        "/api/ai/policy-case/answer",
        json={"provision_id": str(_PROVISION_ID), "scenario": "How many hours may a part-timer work?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "informational"

    info = body["informational"]
    assert info["status"] == "answered"
    # The citation is an id and nothing but an id -- the payload never carried a
    # generated name, so a name could not come back as a citation (constraint 8).
    assert info["citations"] == [{"rule_id": _RULE_IDS[0]}]
    assert set(info["citations"][0]) == {"rule_id"}
    # And the id is one that was seeded: reachable back to a rule that exists.
    assert info["citations"][0]["rule_id"] in _RULE_IDS
    # The grounding line reports the universe it checked against -- the two seeded
    # rules, the whole provision, not a subset and not something wider.
    assert info["grounding"]["rules_available"] == len(_RULE_IDS)
    assert info["grounding"]["oversize"] is False


async def test_a_fabricated_citation_is_refused_at_the_http_boundary(client) -> None:
    """A model that cites a rule the projection never carried is refused by code,
    end to end. The grounding universe is the payload actually sent -- the seam's
    projection of the seeded rows -- so an id that names no seeded rule cannot pass
    as a citation, and it is named rather than silently dropped.

    A grounding check never shown to reject anything is the "validator that could
    not fail" this repository documents; this is that rejection, over the wire.
    """

    _StubClient.info_reply = {
        "bears": True,
        "answer": "An answer resting on a rule that was never in this policy.",
        "cited_rule_ids": [_GHOST_ID],
        "declined": False,
        "note": "",
    }

    response = await client.post(
        "/api/ai/policy-case/answer",
        json={"provision_id": str(_PROVISION_ID), "scenario": "How many hours may a part-timer work?"},
    )

    assert response.status_code == 200
    info = response.json()["informational"]
    # Nothing valid is left to ground on, so the answer does not stand as answered.
    assert info["status"] != "answered"
    assert info["citations"] == []
    # The fabrication is reported, not swallowed: the check is seen to have refused.
    assert info["grounding"]["fabricated_citations"] == [_GHOST_ID]
    assert info["grounding"]["rules_cited"] == 0


async def test_a_determination_returns_only_the_classification(client) -> None:
    """When the case is a determination, the endpoint never runs it. It returns
    the classification and a null informational answer, so the caller runs the
    per-rule deciders it already has and this endpoint cannot become a second,
    drifting decider."""

    _StubClient.classify_reply = {"intent": "decision", "reasoning": "states facts and asks for a ruling"}

    response = await client.post(
        "/api/ai/policy-case/answer",
        json={
            "provision_id": str(_PROVISION_ID),
            "scenario": "I am part time working thirty hours a week; am I over the cap?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "decision"
    # No informational answer is synthesised for a determination.
    assert body["informational"] is None


async def test_an_unknown_provision_is_a_404_not_an_empty_answer(client) -> None:
    """No such provision is not a policy that holds nothing on the subject: it is
    a 404, kept apart from an empty-bearing 200 so "the id resolves to nothing"
    is never read as "the policy has no rule on this" (constraint 5)."""

    missing = uuid.UUID("00000000-0000-4000-8000-0000000000fe")

    response = await client.post(
        "/api/ai/policy-case/answer",
        json={"provision_id": str(missing), "scenario": "How many hours may a part-timer work?"},
    )

    assert response.status_code == 404


async def test_a_malformed_provision_id_is_a_422(client) -> None:
    """A provision id that is not a well-formed identifier is the caller's
    malformed input -- a 422, told apart from an unknown-but-valid id's 404."""

    response = await client.post(
        "/api/ai/policy-case/answer",
        json={"provision_id": "not-a-uuid", "scenario": "How many hours may a part-timer work?"},
    )

    assert response.status_code == 422
