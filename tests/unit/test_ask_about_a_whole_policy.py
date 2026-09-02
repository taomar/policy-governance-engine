"""ASKING ABOUT A WHOLE POLICY, AND SAYING HOW MUCH OF IT WAS READ.

A policy in this corpus can hold seventy-odd rules. One request cannot carry all
of them, and the failure this file exists to prevent is the quiet one: an answer
grounded in the first part of a policy that reads exactly like an answer grounded
in all of it. A reviewer cannot tell those apart by looking, so the counts are
returned and the dialog states them.

The second thing held here is the one that outranks the feature. The reader may
ask for the answer in their own language; the document's words are not the
answer's to restate. So the text that reaches the model is asserted identical
whichever language was asked for, in both scripts, and asserted to arrive as
characters rather than as `\\uXXXX` escapes — a model told to copy a fact
character-for-character from an escaped context copies the escapes.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from policy_platform.infrastructure.assistants import ai_chat

pytestmark = pytest.mark.anyio


class _Settings:
    ai_enabled = True
    search_enabled = False
    azure_openai_secondary_deployment = "fast"
    azure_openai_deployment = "slow"
    azure_search_authoring_index = "index"


class _RecordingClient:
    """Stands in for the model, and keeps what it was told."""

    last_messages: list[dict[str, str]] = []
    last_kwargs: dict[str, Any] = {}

    def __init__(self, settings: Any) -> None:  # noqa: D107 - shape only
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).last_messages = messages
        type(self).last_kwargs = kwargs
        return json.dumps({"groups": [], "reflection": "."})


#: An English clause and an Arabic one, as a document would hold them. Both are
#: quoted back at the assertions below character-for-character.
ENGLISH_CLAUSE = "It may not be disclosed in whole or in part without the express written authorization."
ARABIC_CLAUSE = "لا يجوز إفشاؤه كليًا أو جزئيًا دون إذن كتابي صريح."


def _record(rule_id: str, source_text: str, padding: int = 0) -> dict:
    # Padding rides on the title rather than on a field of its own, because the
    # block sends a projection of the record and a field nothing reads would not
    # reach the budget it is here to exercise.
    return {
        "rule_id": rule_id,
        "title": f"Rule {rule_id}" + "x" * padding,
        "evaluation_mode": "ai_ready",
        "formulation": {"canonical": {"source_text": source_text}},
        "xacml_view": {"never": "sent"},
    }


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingClient]:
    monkeypatch.setattr(ai_chat, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_chat, "AzureOpenAIClient", _RecordingClient)
    _RecordingClient.last_messages = []
    _RecordingClient.last_kwargs = {}
    return _RecordingClient


def _serve(monkeypatch: pytest.MonkeyPatch, records: list[dict]) -> None:
    """Answers the lookup with `records`, in the order the caller asked for."""

    by_id = {record["rule_id"]: record for record in records}

    async def _lookup(
        _session: Any,
        _key: str | None,
        rule_ids: list[str],
        *,
        policy_version_id: str | None = None,
    ) -> tuple[list[dict], str]:
        found = [by_id[rule_id] for rule_id in rule_ids if rule_id in by_id]
        source = (
            ai_chat.RECORDS_FROM_PUBLISHED_VERSION
            if policy_version_id
            else ai_chat.RECORDS_FROM_DRAFT_ROWS
        )
        return found, source

    monkeypatch.setattr(ai_chat, "_policy_rule_payloads", _lookup)


def _context_of(client: type[_RecordingClient]) -> str:
    return client.last_messages[-1]["content"]


# --------------------------------------------------------------------------
# What is sent, and in what order


def test_the_records_go_in_the_order_the_card_shows_them() -> None:
    """Document order, so "the first N" names a prefix a reader can point at.

    Any other order would make the coverage sentence true and useless: a reader
    told twelve of seventy-two rules were read cannot check which twelve unless
    they are the twelve at the top of the card.
    """

    block, covered = ai_chat._policy_context_block(
        [_record("AI-3", "third"), _record("AI-1", "first"), _record("AI-2", "second")]
    )

    assert covered == 3
    assert block.index("AI-3") < block.index("AI-1") < block.index("AI-2")


def test_a_record_is_carried_whole_or_not_at_all() -> None:
    """Half a record is a different record.

    Truncating mid-record would leave the model answering about a rule whose
    condition it read and whose effect it did not, with nothing on screen saying
    so.
    """

    big = ai_chat.MAX_POLICY_RECORD_CHARS // 2
    block, covered = ai_chat._policy_context_block(
        [_record(f"AI-{i}", ENGLISH_CLAUSE, padding=big) for i in range(6)]
    )

    assert covered < 6, "the budget was not reached, so this proves nothing"
    for i in range(covered):
        # Every record that went in is parseable on its own, which it would not
        # be if the budget had cut one in half.
        assert f'"rule_id": "AI-{i}"' in block
        assert f'"AI-{i}"' in block
    assert f'"rule_id": "AI-{covered}"' not in block
    assert len(block) <= ai_chat.MAX_POLICY_RECORD_CHARS + len(ai_chat._POLICY_BLOCK_PREAMBLE) + 8


def test_one_record_larger_than_the_whole_budget_is_still_sent() -> None:
    """An answer grounded in nothing is worse than one bounded request."""

    _block, covered = ai_chat._policy_context_block(
        [_record("AI-1", ENGLISH_CLAUSE, padding=ai_chat.MAX_POLICY_RECORD_CHARS * 2)]
    )

    assert covered == 1


def test_the_documents_words_arrive_as_characters_not_as_escapes() -> None:
    """`\\u0627\\u0644…` is not what the document wrote.

    The answer contract asks the model to copy quoted facts character-for-
    character from what it was given. Given escapes, that is what it would copy,
    and the quotation on screen would be a rendering of the document rather than
    the document.
    """

    block, _ = ai_chat._policy_context_block([_record("AI-1", ARABIC_CLAUSE)])

    assert ARABIC_CLAUSE in block
    assert "\\u06" not in block
    assert "\\u0627" not in block


def test_the_two_halves_of_a_record_are_named_as_two_claims() -> None:
    """The explainer's rule, inherited as its reason rather than as its rule.

    The explainer withholds the document's words from the model because a model
    shown both silently reconciles them and hides extraction defects. An ask
    surface has to show both — its answers quote. So the two are named as
    separate claims and a disagreement is asked for as a finding, which is the
    defect the explainer was protecting, reported rather than merely not hidden.
    """

    preamble = ai_chat._POLICY_BLOCK_PREAMBLE.lower()

    assert "two separate claims" in preamble
    assert "what_this_app_extracted" in preamble
    assert "the_documents_own_words" in preamble
    assert "disagree" in preamble
    assert "do not reconcile them" in preamble


# --------------------------------------------------------------------------
# What comes back about coverage


async def test_reading_every_rule_says_so_with_the_counts(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, [_record("AI-1", ENGLISH_CLAUSE), _record("AI-2", ENGLISH_CLAUSE)])

    reply = await ai_chat.ask(
        None, question="what does this require?", policy_set_key="set-1", focus_rule_ids=["AI-1", "AI-2"]
    )

    assert reply["grounding"] == {
        "rule_count": 2,
        "covered_rule_count": 2,
        "covers_every_rule": True,
        # Named on every grounded answer, not only on the unusual one. A note
        # that appears only when something is odd teaches a reader that its
        # absence means "ordinary", and here "ordinary" is the draft row.
        "record_source": ai_chat.RECORDS_FROM_DRAFT_ROWS,
    }


async def test_reading_part_of_a_policy_says_which_part_rather_than_truncating_quietly(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The single failure this scope introduces, and the thing that catches it."""

    big = ai_chat.MAX_POLICY_RECORD_CHARS // 2
    ids = [f"AI-{i}" for i in range(8)]
    _serve(monkeypatch, [_record(rule_id, ENGLISH_CLAUSE, padding=big) for rule_id in ids])

    reply = await ai_chat.ask(
        None, question="what does this require?", policy_set_key="set-1", focus_rule_ids=ids
    )

    grounding = reply["grounding"]
    assert grounding["rule_count"] == 8
    assert 0 < grounding["covered_rule_count"] < 8
    assert grounding["covers_every_rule"] is False


async def test_a_question_about_one_rule_reports_no_coverage_at_all(
    recorded: type[_RecordingClient],
) -> None:
    """Absent is not the same as complete.

    A rule-scoped ask has no coverage question to answer, so it says nothing
    rather than saying "all of it" — which would be a claim about a set that was
    never assembled, and would put a sentence on screen with nothing behind it.
    """

    reply = await ai_chat.ask(None, question="explain this")

    assert "grounding" not in reply


async def test_ids_that_are_not_found_are_skipped_rather_than_guessed_at(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, [_record("AI-1", ENGLISH_CLAUSE)])

    reply = await ai_chat.ask(
        None,
        question="what does this require?",
        policy_set_key="set-1",
        focus_rule_ids=["AI-1", "AI-missing"],
    )

    assert reply["grounding"]["rule_count"] == 2
    assert reply["grounding"]["covered_rule_count"] == 1
    assert reply["grounding"]["covers_every_rule"] is False
    assert "AI-missing" not in _context_of(recorded)


# --------------------------------------------------------------------------
# The constraint that outranks the feature, at this scope


@pytest.mark.parametrize("clause", [ENGLISH_CLAUSE, ARABIC_CLAUSE])
async def test_the_language_choice_changes_nothing_the_document_wrote(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, clause: str
) -> None:
    """The whole feature, held to the one thing it must not do.

    A policy-wide answer quotes more of the document than a rule-wide one, so
    there is more here to get wrong. The context the model is given must be the
    same characters whichever language the reader asked for; only what is asked
    *of* the model changes.
    """

    _serve(monkeypatch, [_record("AI-1", clause), _record("AI-2", clause)])
    contexts: dict[str, str] = {}

    for tag in ("en", "ar", "fr", None):
        await ai_chat.ask(
            None,
            question="what does this require?",
            policy_set_key="set-1",
            focus_rule_ids=["AI-1", "AI-2"],
            answer_language=tag,
        )
        contexts[str(tag)] = _context_of(recorded)
        assert clause in contexts[str(tag)]

    assert len(set(contexts.values())) == 1, "the language choice reached the document's words"


async def test_the_policy_the_question_is_about_leads_the_context(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, [_record("AI-1", ENGLISH_CLAUSE)])

    await ai_chat.ask(
        None, question="what does this require?", policy_set_key="set-1", focus_rule_ids=["AI-1"]
    )

    context = _context_of(recorded)
    assert context.index(ai_chat._POLICY_BLOCK_PREAMBLE[:40]) < context.index("QUESTION:")


def test_the_two_halves_of_a_record_reach_the_model_as_two_halves() -> None:
    """A projection, and the split is in the data rather than only described.

    `policy_explainer` withholds the document's words from the model because a
    model shown both silently reconciles them, and that choice caught this app's
    own extraction inverting a prohibition. An ask surface cannot withhold them —
    it is contracted to quote — so it names them apart instead. Flattened into
    one object they would read as one fact stated twice, and a disagreement
    between them would have nowhere to be reported from.
    """

    payload = {
        "rule_id": "AI-1",
        "title": "Hiring relatives",
        "condition": {"all": []},
        "effect": {"type": "deny", "action": "supervise the other"},
        "evaluation_mode": "deterministic",
        "formulation": {"canonical": {"source_text": ENGLISH_CLAUSE, "rule": {"modality": "may not"}}},
        "evidence": [{"section": "7.11. HIRING RELATIVES & NEPOTISM", "page": 11}],
        "xacml_view": {"machinery": "x" * 4000},
        "lineage": {"machinery": "y" * 4000},
        "candidate_relationships": ["z" * 4000],
    }

    record = ai_chat._policy_rule_record(payload)

    assert record["the_documents_own_words"]["source_text"] == ENGLISH_CLAUSE
    assert record["what_this_app_extracted"]["effect"] == {
        "type": "deny",
        "action": "supervise the other",
    }
    # The document's words are not repeated inside this app's reading of them,
    # and this app's reading is not repeated inside the document's words.
    assert ENGLISH_CLAUSE not in json.dumps(record["what_this_app_extracted"], ensure_ascii=False)
    assert "effect" not in record["the_documents_own_words"]


def test_the_machinery_of_a_record_is_not_what_the_reviewer_asked_about() -> None:
    """Sent whole, a budget that fits a policy fits two of its rules.

    Most of a stored record is projections, mappings, hashes and lineage, none
    of which answers "what does this policy require?". Spending the budget on
    them buys a coverage statement where a covered policy would do.
    """

    payload = {
        "rule_id": "AI-1",
        "title": "Hiring relatives",
        "formulation": {"canonical": {"source_text": ENGLISH_CLAUSE}},
        "xacml_view": {"machinery": "x" * 4000},
        "lineage": {"machinery": "y" * 4000},
        "candidate_relationships": ["z" * 4000],
        "policy_set_id": "set-1",
        "schema_version": "9",
    }

    block, covered = ai_chat._policy_context_block([payload])

    assert covered == 1
    assert ENGLISH_CLAUSE in block
    for machinery in ("xacml_view", "lineage", "candidate_relationships", "schema_version"):
        assert machinery not in block


async def test_a_wider_question_is_given_room_to_answer_in(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reply cut off mid-JSON parses as reflection-only.

    Which on screen is a thin answer, not a truncated one — the reviewer is given
    no reason to distrust it. Cheaper to pay for the tokens than to ship an
    answer that lost its quotations silently.
    """

    _serve(monkeypatch, [_record("AI-1", ENGLISH_CLAUSE)])

    await ai_chat.ask(None, question="explain this")
    rule_budget = _RecordingClient.last_kwargs["max_tokens"]
    await ai_chat.ask(
        None, question="what does this require?", policy_set_key="set-1", focus_rule_ids=["AI-1"]
    )
    policy_budget = _RecordingClient.last_kwargs["max_tokens"]

    assert policy_budget > rule_budget
