"""WHEN THE POLICY SET A DRAFT ASK NAMES DOES NOT RESOLVE.

The per-rule "Ask AI about this rule" action on a draft row grounds its answer on
two things: the exact draft rule the reviewer is looking at, and — so the answer
can speak to "does this conflict with what is already approved?" — the policy
set's currently-approved rules. The second is loaded by key. The server resolves
it with `PolicySetRepository.get_by_key`, which matches on the set's `key` and
nothing else.

A key that resolves to no set used to skip the whole approved-rules block in
silence. The reviewer got a confident answer grounded on less than it should
have been, with nothing in the reply or the log saying the set could not be
found. That collapses *failed* (the server could not find the set you named)
into *absent* (you named no set) — two states this system keeps apart everywhere.

These tests hold the four states apart at this one site:

  present  a set that resolves loads its rules into CONTEXT;
  failed   a key that resolves to nothing is a warning, not a silence;
  empty    a set that resolves but has no approved version (or a version with no
           rules) is a debug, expressly not a warning, because it is empty
           rather than failed;
  absent   naming no set at all stays silent — there was nothing to look up.

The ask still answers from the rule alone whenever the context degrades: that
degrade is deliberate (see the sibling `except` in `ask`, "chat should still
answer from rules alone"). Degrading is fine. Degrading *silently* was the bug.
"""
from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from policy_platform.infrastructure.assistants import ai_chat

pytestmark = pytest.mark.anyio

AI_CHAT_LOGGER = "policy_platform.infrastructure.assistants.ai_chat"

SET_ID = uuid.uuid4()
# The key the review queue threads in — what the server resolves a set by. A
# real set's uuid would never match a key, which is the whole client-side bug
# this backend change makes audible rather than silent.
RESOLVING_KEY = "staff-handbook-2024"
APPROVED_TITLE = "No approval of a relative's appointment"


class _Settings:
    ai_enabled = True
    search_enabled = False
    azure_openai_secondary_deployment = "fast"
    azure_openai_deployment = "slow"
    azure_search_authoring_index = "index"


class _RecordingClient:
    """Records the messages `ask` built, so a test can read what reached the
    model rather than trusting that the block ran."""

    last_messages: list[dict[str, str]] = []

    def __init__(self, settings: Any) -> None:  # noqa: D107 - shape only
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).last_messages = messages
        return json.dumps({"groups": [], "reflection": "."})


def _approved_rule(rule_id: str = "AI-1") -> SimpleNamespace:
    """A rule in the shape `ask` reads: `.rule_id`, `.rule_type.value`,
    `.effect.type.value`, `.title`, `.description`."""

    return SimpleNamespace(
        rule_id=rule_id,
        title=APPROVED_TITLE,
        description="An employee may not approve the appointment of a relative.",
        rule_type=SimpleNamespace(value="obligation"),
        effect=SimpleNamespace(type=SimpleNamespace(value="prohibited")),
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolves: bool,
    has_version: bool,
    rules: list[SimpleNamespace] | None = None,
) -> None:
    """Wire the two lookups the approved-rules block reaches for, plus the
    package conversion, parameterised by which of the four states to produce."""

    package_rules = rules if rules is not None else [_approved_rule()]

    class _Sets:
        def __init__(self, _session: Any) -> None:
            pass

        async def get_by_key(self, key: str) -> Any:
            if resolves and key == RESOLVING_KEY:
                return SimpleNamespace(id=SET_ID, key=RESOLVING_KEY)
            return None

    class _Versions:
        def __init__(self, _session: Any) -> None:
            pass

        async def get_active_version(self, set_id: uuid.UUID) -> Any:
            if has_version and set_id == SET_ID:
                return SimpleNamespace(policy_set_id=SET_ID, version_number=3, is_active=True)
            return None

        async def get_by_id(self, _version_uuid: uuid.UUID) -> Any:
            return None

    monkeypatch.setattr(ai_chat, "PolicySetRepository", _Sets)
    monkeypatch.setattr(ai_chat, "ApprovedPolicyVersionRepository", _Versions)
    monkeypatch.setattr(
        ai_chat, "approved_policy_version_to_package", lambda _version: SimpleNamespace(rules=package_rules)
    )


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingClient]:
    monkeypatch.setattr(ai_chat, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_chat, "AzureOpenAIClient", _RecordingClient)
    _RecordingClient.last_messages = []
    return _RecordingClient


def _context(client: type[_RecordingClient]) -> str:
    return "\n".join(m["content"] for m in client.last_messages)


def _ai_chat_records(caplog: pytest.LogCaptureFixture, level: int) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == AI_CHAT_LOGGER and r.levelno == level]


# --------------------------------------------------------------------------
# present — a set that resolves loads its rules (also: the client fix's payoff)


async def test_a_named_set_that_resolves_loads_its_approved_rules_in_silence(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # This is what the draft ask was missing: once the modal sends the set's key
    # (not its uuid), the server resolves it and the set's currently-approved
    # rules reach the model. Observed on the recorded context, not inferred from
    # the request — "the answer is grounded on more than before" is a fact about
    # what reached the model, checked here.
    _install(monkeypatch, resolves=True, has_version=True)
    caplog.set_level(logging.DEBUG, logger=AI_CHAT_LOGGER)

    await ai_chat.ask(
        None,
        question="does this draft conflict with anything already approved?",
        policy_set_key=RESOLVING_KEY,
    )

    context = _context(recorded)
    assert f"Rules of policy set '{RESOLVING_KEY}' version 3 (currently approved):" in context
    assert APPROVED_TITLE in context
    # A load that worked is not a state anyone needs told about.
    assert _ai_chat_records(caplog, logging.WARNING) == []
    assert _ai_chat_records(caplog, logging.DEBUG) == []


# --------------------------------------------------------------------------
# failed — a key that resolves to nothing is a warning, not a silence


async def test_a_key_that_resolves_to_nothing_is_a_warning_not_a_silence(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The defect, at the server. A key that matches no set skipped the whole
    # block without a word. The ask still answers from the rule alone — so the
    # block is genuinely absent from CONTEXT — but the skip is now audible.
    _install(monkeypatch, resolves=False, has_version=False)
    caplog.set_level(logging.DEBUG, logger=AI_CHAT_LOGGER)

    await ai_chat.ask(
        None,
        question="does this draft conflict with anything already approved?",
        policy_set_key=RESOLVING_KEY,
    )

    assert "Rules of policy set" not in _context(recorded)
    warnings = _ai_chat_records(caplog, logging.WARNING)
    assert len(warnings) == 1
    # The key is named, so the line points at what could not be found rather than
    # reporting a bare "lookup failed" a reader cannot act on.
    assert RESOLVING_KEY in warnings[0].getMessage()
    # Failed is not empty: a failed lookup does not also emit the empty-state note.
    assert _ai_chat_records(caplog, logging.DEBUG) == []


# --------------------------------------------------------------------------
# empty — a set with nothing approved is a debug, not a warning


async def test_a_set_with_no_approved_version_is_a_debug_not_a_warning(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The set resolves; it simply has no version in force yet. That is empty, not
    # failed. A set mid-drafting must not cry the same wolf as a key that names
    # no set — so this is a debug, and expressly not a warning.
    _install(monkeypatch, resolves=True, has_version=False)
    caplog.set_level(logging.DEBUG, logger=AI_CHAT_LOGGER)

    await ai_chat.ask(
        None,
        question="what else does this policy already approve?",
        policy_set_key=RESOLVING_KEY,
    )

    assert "Rules of policy set" not in _context(recorded)
    assert _ai_chat_records(caplog, logging.WARNING) == []
    debugs = _ai_chat_records(caplog, logging.DEBUG)
    assert len(debugs) == 1
    assert RESOLVING_KEY in debugs[0].getMessage()


async def test_a_version_that_lists_no_rules_is_a_debug_not_a_warning(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The rarer empty: a version in force that yields no rule lines. Still empty,
    # not failed, and still kept out of the warning channel.
    _install(monkeypatch, resolves=True, has_version=True, rules=[])
    caplog.set_level(logging.DEBUG, logger=AI_CHAT_LOGGER)

    await ai_chat.ask(
        None,
        question="what else does this policy already approve?",
        policy_set_key=RESOLVING_KEY,
    )

    assert "Rules of policy set" not in _context(recorded)
    assert _ai_chat_records(caplog, logging.WARNING) == []
    assert len(_ai_chat_records(caplog, logging.DEBUG)) == 1


# --------------------------------------------------------------------------
# absent — naming no set stays silent


async def test_naming_no_policy_set_stays_silent(
    recorded: type[_RecordingClient], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Absent is not failed. No key was named, so the block never runs and there
    # is nothing to warn or note. This guards the fix against turning an ordinary
    # unscoped ask into noise.
    _install(monkeypatch, resolves=False, has_version=False)
    caplog.set_level(logging.DEBUG, logger=AI_CHAT_LOGGER)

    await ai_chat.ask(None, question="a general question about the handbook", policy_set_key=None)

    assert [r for r in caplog.records if r.name == AI_CHAT_LOGGER] == []
