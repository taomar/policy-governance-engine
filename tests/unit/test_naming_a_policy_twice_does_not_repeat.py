"""Naming a policy a second time must not repeat a handle it already carries.

WHAT IS AT STAKE

Rules arrive in waves. An extraction runs, a reviewer works the queue, the
extraction runs again and adds three more rules to a passage that already had
nine. Naming is incremental by design — it skips rules that already have a
handle, because re-asking for them would spend a model call to produce the
words already on screen.

That skip is also the trap. The run that names only the three new rules has no
memory of the nine names beside them unless it goes and reads them. Without
that, the tenth rule can be handed the ninth rule's handle, and two rules on
one card read the same — which is the one failure this feature exists to avoid.

The same holds for the writing system. A policy that settled on one language in
its first run must stay in it, or the card ends up bilingual by accident of
scheduling.

Both were observed on the live corpus: five pairs of rules under one passage
wore identical handles, generated eighty minutes apart.

WHAT IS ASSERTED

That a second run reads what the policy already carries before it asks for
anything, and that both the handles and their writing system are carried into
the request. Every record below is invented; nothing here is a phrase from any
document, and no number in it is a measurement of one.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.domain.models import (
    CandidateRule,
    CandidateRuleName,
    DocumentProvision,
    PolicySet,
)
from policy_platform.infrastructure.assistants import rule_namer
from policy_platform.infrastructure.assistants.rule_namer import (
    UNAVAILABLE_NOT_DISTINCT,
    name_rules,
)


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# tables be created, so the real columns are exercised rather than a stand-in.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


POLICY_SET = uuid.UUID(int=11)
VERSION = uuid.UUID(int=12)
RUN = uuid.UUID(int=13)

#: A handle already stored for the first rule. Two words of invented subject,
#: so nothing here can pass by resembling a document.
CARRIED = "Kestrel mooring turns"


class _Settings:
    ai_enabled = True
    # rule_namer now runs on the primary deployment, so the stub must offer it.
    azure_openai_deployment = "a-deployment"
    azure_openai_secondary_deployment = "a-secondary-deployment"


class _Replies:
    """Answers with what it was told to, and keeps what it was asked."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.asks = 0
        self.sent: list[str] = []

    def __init_subclass__(cls) -> None:  # pragma: no cover - not subclassed
        raise TypeError

    async def chat(self, messages, **_kwargs) -> str:
        self.asks += 1
        self.sent.append(json.dumps(messages, ensure_ascii=False))
        return self._replies[min(self.asks - 1, len(self._replies) - 1)]


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (PolicySet, DocumentProvision, CandidateRule, CandidateRuleName):
            await connection.run_sync(
                lambda sync, table=table: table.__table__.create(sync, checkfirst=True)
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


def _payload(what: str) -> dict:
    """A record shaped like the ones the namer is shown, and nothing more."""

    return {
        "rule_id": f"AI-{uuid.uuid4().hex[:10]}",
        "title": "Kestrel Bay mooring turns",
        "description": what,
        "effect": "obligation",
        "rule_type": "obligation",
        "condition": {},
        "attributes": [],
    }


async def _populate(
    session, *, named: str | None, heading: list[str] | None = None
) -> list[uuid.UUID]:
    """One passage, two rules. The first may already carry a handle."""

    session.add(
        PolicySet(
            id=POLICY_SET, key="a-policy-set", name="A set", owner="someone", description=""
        )
    )
    provision = DocumentProvision(
        id=uuid.uuid4(),
        policy_set_id=POLICY_SET,
        document_version_id=VERSION,
        provision_key="a-provision-key",
        heading_path_json=heading or ["An outer heading", "A heading"],
        heading_element_ids_json=["E1"],
        first_sequence=1,
    )
    session.add(provision)
    ids: list[uuid.UUID] = []
    for what in ("records the turn", "countersigns the turn"):
        rule = CandidateRule(
            id=uuid.uuid4(),
            policy_set_id=POLICY_SET,
            provision_id=provision.id,
            extraction_run_id=RUN,
            rule_type="obligation",
            payload_json=_payload(what),
            review_status="candidate",
        )
        session.add(rule)
        ids.append(rule.id)
    if named is not None:
        session.add(
            CandidateRuleName(
                id=uuid.uuid4(),
                candidate_rule_id=ids[0],
                name_text=named,
                model_deployment="a-deployment",
                prompt_version=rule_namer.PROMPT_VERSION,
                source_digest="a-digest",
                generated_at=datetime.now(timezone.utc),
            )
        )
    await session.commit()
    return ids


async def _stored(session, rule_id: uuid.UUID) -> CandidateRuleName | None:
    return (
        await session.execute(
            CandidateRuleName.__table__.select().where(
                CandidateRuleName.candidate_rule_id == rule_id
            )
        )
    ).first()


class TestASecondRunReadsWhatTheFirstWrote:
    async def test_it_will_not_hand_a_new_rule_a_handle_a_sibling_wears(
        self, session, monkeypatch
    ) -> None:
        """The whole point of a handle is that it picks one rule out."""

        ids = await _populate(session, named=CARRIED)
        client = _Replies(json.dumps({"names": {"1": CARRIED}}))
        monkeypatch.setattr(rule_namer, "get_settings", lambda: _Settings())
        monkeypatch.setattr(rule_namer, "AzureOpenAIClient", lambda _settings: client)

        result = await name_rules(session, policy_set_id=POLICY_SET, limit=10)

        assert result["named"] == 0
        row = await _stored(session, ids[1])
        assert row is not None
        assert row.name_text is None
        assert row.unavailable_code == UNAVAILABLE_NOT_DISTINCT

    async def test_the_handle_it_already_carries_is_left_alone(
        self, session, monkeypatch
    ) -> None:
        """Re-asking for a rule already named would spend a call to reproduce
        the words on screen, and risk replacing them with different ones."""

        ids = await _populate(session, named=CARRIED)
        client = _Replies(json.dumps({"names": {"1": "Deputy countersigning"}}))
        monkeypatch.setattr(rule_namer, "get_settings", lambda: _Settings())
        monkeypatch.setattr(rule_namer, "AzureOpenAIClient", lambda _settings: client)

        await name_rules(session, policy_set_id=POLICY_SET, limit=10)

        first = await _stored(session, ids[0])
        assert first is not None and first.name_text == CARRIED
        second = await _stored(session, ids[1])
        assert second is not None and second.name_text == "Deputy countersigning"
        # One request, covering only the rule that had no handle.
        assert client.asks == 1

    async def test_a_policy_stays_in_the_language_it_already_answered_in(
        self, session, monkeypatch
    ) -> None:
        """A card that gains its tenth handle in another script reads as two
        cards. On a bilingual passage either script is permitted, so which one
        this policy uses is settled by what it already wrote — not by which
        request happened to run first."""

        arabic = "\u0645\u0631\u0633\u0649 \u0643\u0633\u062a\u0631\u064a\u0644"
        await _populate(
            session,
            named=arabic,
            heading=["\u0645\u0631\u0633\u0649 \u0627\u0644\u0645\u064a\u0646\u0627\u0621", "A heading"],
        )
        client = _Replies(json.dumps({"names": {"1": "Deputy countersigning"}}))
        monkeypatch.setattr(rule_namer, "get_settings", lambda: _Settings())
        monkeypatch.setattr(rule_namer, "AzureOpenAIClient", lambda _settings: client)

        result = await name_rules(session, policy_set_id=POLICY_SET, limit=10)

        # The passage permits either script. Only the handle already stored can
        # have ruled the Latin one out.
        assert result["named"] == 0
