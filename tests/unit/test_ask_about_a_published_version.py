"""ASKING ABOUT A RECORD THAT HAS ALREADY BEEN PUBLISHED.

The Policies page shows sealed records: the rules a version promised, not the
draft rows a reviewer is still working on. Both carry the same `rule_id`, and
that shared id is the whole hazard. Resolving a published rule's id against
`candidate_rules` finds either a draft that has been revised since — a different
record, saying something else — or nothing at all, after which the answer falls
through to general retrieval and arrives looking exactly like a grounded one.

A reviewer cannot see the difference. They asked about the record in front of
them and were answered about another, under the same heading, with the same
confidence. So the version is named in the request and the lookup moves with it,
and every grounded reply says which table it read.

Nothing here asserts a wording. It asserts which record was read, that a
mismatch refuses rather than substitutes, and that a refusal is still reported
as a coverage of zero rather than as silence.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from policy_platform.infrastructure.assistants import ai_chat

pytestmark = pytest.mark.anyio


PUBLISHED_CLAUSE = "An employee may not approve the appointment of a relative."
DRAFT_CLAUSE = "An employee may approve the appointment of a relative."
ARABIC_CLAUSE = "لا يجوز للموظف اعتماد تعيين أحد أقاربه."

SET_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()
OTHER_SET_ID = uuid.uuid4()


class _Settings:
    ai_enabled = True
    search_enabled = False
    azure_openai_fast_deployment = "fast"
    azure_openai_deployment = "slow"
    azure_search_authoring_index = "index"


class _RecordingClient:
    last_messages: list[dict[str, str]] = []

    def __init__(self, settings: Any) -> None:  # noqa: D107 - shape only
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).last_messages = messages
        return json.dumps({"groups": [], "reflection": "."})


class _Rule:
    """A published rule, in the shape `CanonicalRule` dumps to."""

    def __init__(self, rule_id: str, source_text: str) -> None:
        self.rule_id = rule_id
        self._source_text = source_text

    def model_dump(self, mode: str = "python") -> dict:
        return {
            "rule_id": self.rule_id,
            "title": f"Rule {self.rule_id}",
            "evaluation_mode": "ai_ready",
            "formulation": {"canonical": {"source_text": self._source_text}},
        }


class _Package:
    def __init__(self, rules: list[_Rule]) -> None:
        self.rules = rules


class _Version:
    def __init__(self, policy_set_id: uuid.UUID) -> None:
        self.policy_set_id = policy_set_id
        self.version_number = 3
        self.is_active = True


class _PolicySet:
    id = SET_ID
    key = "set-1"


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version_owner: uuid.UUID | None,
    published: list[_Rule],
    drafts: list[dict],
) -> None:
    """Wires the three lookups `_policy_rule_payloads` reaches for."""

    class _Sets:
        def __init__(self, _session: Any) -> None:
            pass

        async def get_by_key(self, key: str) -> Any:
            return _PolicySet() if key == "set-1" else None

    class _Versions:
        def __init__(self, _session: Any) -> None:
            pass

        async def get_by_id(self, version_uuid: uuid.UUID) -> Any:
            if version_owner is None or version_uuid != VERSION_ID:
                return None
            return _Version(version_owner)

    class _Candidates:
        def __init__(self, _session: Any) -> None:
            pass

        async def list_by_policy_set(self, _set_id: uuid.UUID) -> list[Any]:
            return [type("Row", (), {"payload_json": payload})() for payload in drafts]

    monkeypatch.setattr(ai_chat, "PolicySetRepository", _Sets)
    monkeypatch.setattr(ai_chat, "ApprovedPolicyVersionRepository", _Versions)
    monkeypatch.setattr(ai_chat, "CandidateRuleRepository", _Candidates)
    monkeypatch.setattr(
        ai_chat, "approved_policy_version_to_package", lambda _version: _Package(published)
    )


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingClient]:
    monkeypatch.setattr(ai_chat, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_chat, "AzureOpenAIClient", _RecordingClient)
    _RecordingClient.last_messages = []
    return _RecordingClient


def _draft(rule_id: str, source_text: str) -> dict:
    return {
        "rule_id": rule_id,
        "title": f"Draft {rule_id}",
        "evaluation_mode": "ai_ready",
        "formulation": {"canonical": {"source_text": source_text}},
    }


# --------------------------------------------------------------------------
# Which record was read


async def test_a_named_version_is_read_instead_of_the_draft_that_produced_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same id, opposite meanings — the pair this whole file exists for. The
    # draft here says "may", the published rule says "may not".
    _install(
        monkeypatch,
        version_owner=SET_ID,
        published=[_Rule("AI-1", PUBLISHED_CLAUSE)],
        drafts=[_draft("AI-1", DRAFT_CLAUSE)],
    )

    payloads, source = await ai_chat._policy_rule_payloads(
        None, "set-1", ["AI-1"], policy_version_id=str(VERSION_ID)
    )

    assert source == ai_chat.RECORDS_FROM_PUBLISHED_VERSION
    assert [p["formulation"]["canonical"]["source_text"] for p in payloads] == [PUBLISHED_CLAUSE]


async def test_asking_without_a_version_still_reads_the_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The review queue is showing the draft row, so the draft is the record it
    # must be answered about. The published arm is an addition, not a move.
    _install(
        monkeypatch,
        version_owner=SET_ID,
        published=[_Rule("AI-1", PUBLISHED_CLAUSE)],
        drafts=[_draft("AI-1", DRAFT_CLAUSE)],
    )

    payloads, source = await ai_chat._policy_rule_payloads(None, "set-1", ["AI-1"])

    assert source == ai_chat.RECORDS_FROM_DRAFT_ROWS
    assert [p["formulation"]["canonical"]["source_text"] for p in payloads] == [DRAFT_CLAUSE]


async def test_a_version_of_another_policy_set_grounds_nothing_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A wrong version id must not quietly become "the drafts, then". Refusing
    # to ground is recoverable; grounding on the wrong record is not.
    _install(
        monkeypatch,
        version_owner=OTHER_SET_ID,
        published=[_Rule("AI-1", PUBLISHED_CLAUSE)],
        drafts=[_draft("AI-1", DRAFT_CLAUSE)],
    )

    payloads, source = await ai_chat._policy_rule_payloads(
        None, "set-1", ["AI-1"], policy_version_id=str(VERSION_ID)
    )

    assert payloads == []
    assert source == ai_chat.RECORDS_FROM_PUBLISHED_VERSION


async def test_a_version_id_that_is_not_a_version_grounds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        version_owner=None,
        published=[_Rule("AI-1", PUBLISHED_CLAUSE)],
        drafts=[_draft("AI-1", DRAFT_CLAUSE)],
    )

    for bad in ("not-a-uuid", str(uuid.uuid4())):
        payloads, source = await ai_chat._policy_rule_payloads(
            None, "set-1", ["AI-1"], policy_version_id=bad
        )
        assert payloads == [], bad
        assert source == ai_chat.RECORDS_FROM_PUBLISHED_VERSION, bad


async def test_the_published_order_is_the_order_that_was_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The caller's order is the order the card shows. A coverage statement about
    # "the first N" only names a prefix a reader can point at if that holds.
    _install(
        monkeypatch,
        version_owner=SET_ID,
        published=[_Rule("AI-1", PUBLISHED_CLAUSE), _Rule("AI-2", ARABIC_CLAUSE)],
        drafts=[],
    )

    payloads, _ = await ai_chat._policy_rule_payloads(
        None, "set-1", ["AI-2", "AI-1"], policy_version_id=str(VERSION_ID)
    )

    assert [p["rule_id"] for p in payloads] == ["AI-2", "AI-1"]


# --------------------------------------------------------------------------
# What comes back when it could not be read


async def test_a_published_ask_that_resolved_nothing_still_reports_coverage(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Zero coverage is a fact about the answer, not an absence of one. Reported
    # so the dialog can say "grounded in none of them" rather than showing a
    # confident answer with no statement attached to it.
    async def _empty(*_args: Any, **_kwargs: Any) -> tuple[list[dict], str]:
        return [], ai_chat.RECORDS_FROM_PUBLISHED_VERSION

    monkeypatch.setattr(ai_chat, "_policy_rule_payloads", _empty)

    reply = await ai_chat.ask(
        None,
        question="what does this require?",
        policy_set_key="set-1",
        focus_rule_ids=["AI-1", "AI-2"],
        policy_version_id=str(VERSION_ID),
    )

    assert reply["grounding"] == {
        "rule_count": 2,
        "covered_rule_count": 0,
        "covers_every_rule": False,
        "record_source": ai_chat.RECORDS_FROM_PUBLISHED_VERSION,
    }


async def test_a_lookup_that_raised_reports_zero_rather_than_no_grounding_at_all(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    # An exception used to leave `grounding` absent, which the dialog reads as
    # "this answer was not scoped" — indistinguishable from an ordinary
    # unscoped ask. A failed grounding is a grounding of zero, and says so.
    async def _boom(*_args: Any, **_kwargs: Any) -> tuple[list[dict], str]:
        raise RuntimeError("database gone")

    monkeypatch.setattr(ai_chat, "_policy_rule_payloads", _boom)

    reply = await ai_chat.ask(
        None,
        question="what does this require?",
        policy_set_key="set-1",
        focus_rule_ids=["AI-1"],
        policy_version_id=str(VERSION_ID),
    )

    assert reply["grounding"]["covered_rule_count"] == 0
    assert reply["grounding"]["covers_every_rule"] is False
    assert reply["grounding"]["record_source"] == ai_chat.RECORDS_FROM_PUBLISHED_VERSION


# --------------------------------------------------------------------------
# The constraint that outranks the feature, at this scope


async def test_the_language_asked_for_changes_nothing_the_published_record_says(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A published answer quotes more source text than a rule-scoped one, so the
    # rule that the document's words are never restated matters more here, not
    # less. Both scripts are checked: an English clause inside an Arabic answer
    # and an Arabic clause inside an English one.
    sent: dict[str, str] = {}

    async def _served(*_args: Any, **_kwargs: Any) -> tuple[list[dict], str]:
        return (
            [
                _draft("AI-1", PUBLISHED_CLAUSE),
                _draft("AI-2", ARABIC_CLAUSE),
            ],
            ai_chat.RECORDS_FROM_PUBLISHED_VERSION,
        )

    monkeypatch.setattr(ai_chat, "_policy_rule_payloads", _served)

    for language in ("en", "ar"):
        await ai_chat.ask(
            None,
            question="what does this require?",
            policy_set_key="set-1",
            focus_rule_ids=["AI-1", "AI-2"],
            policy_version_id=str(VERSION_ID),
            answer_language=language,
        )
        sent[language] = "\n".join(m["content"] for m in _RecordingClient.last_messages)

    for language, context in sent.items():
        # Characters, not `\uXXXX` escapes: a model told to copy a fact
        # character-for-character out of an escaped context copies the escapes.
        assert PUBLISHED_CLAUSE in context, language
        assert ARABIC_CLAUSE in context, language

    # And byte-for-byte the same in both, so no part of the record moved when
    # the reader changed which language the answer should come back in.
    def _record_block(context: str) -> str:
        start = context.index(PUBLISHED_CLAUSE)
        end = context.index(ARABIC_CLAUSE) + len(ARABIC_CLAUSE)
        return context[start:end]

    assert _record_block(sent["en"]) == _record_block(sent["ar"])
