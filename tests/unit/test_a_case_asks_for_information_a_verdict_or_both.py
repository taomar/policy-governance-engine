"""A case asks for information, a verdict, or both — and gets what it asked for.

WHAT WENT WRONG BEFORE

The first classifier sorted a case into one of two kinds and ran one branch. For
a question that asks both — "what is the overtime limit, and was Tuesday within
it?" — half the answer was produced and nothing on the response said the other
half had been dropped. Worse: a caller whose verdict was blocked on a missing
fact received a status, a list of bare strings, and *no* information at all,
even when they had explicitly asked what the policies say.

WHAT THIS FILE HOLDS

The gather-level half of the redesign, below the receipt:

  * one classifier call returns two independent booleans, and takes no caller
    guidance;
  * an unreadable classification runs both tracks rather than guessing;
  * both requested gathers run over the *same* retained records, concurrently,
    and never trigger a second retrieval;
  * a blocked verdict carries structured missing information — the fact, a label,
    why it is needed, and the rules that need it — beside the flat list a client
    already reads, with fabricated rule ids refused there exactly as they are in
    a citation.

The receipt-level half is in `test_a_project_case_decision_carries_its_own_receipt`.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Settings:
    ai_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"


#: The one phrase that tells the needs classifier's prompt apart from a gather's.
#: Taken from the prompt's own return contract rather than from prose, so a
#: reworded explanation cannot silently make this stub route calls wrongly.
_NEEDS_MARKER = "information_requested"

#: The multi-policy verdict prompt's own distinguishing clause.
_VERDICT_MARKER = "asked for a judgement"


class _StubClient:
    """Stands in for the model, serving three prompts apart by what each says.

    Every call is recorded, so a test can assert not only what came back but what
    was sent — which is how "the classifier was never handed the caller's
    guidance" is checked as a property of the request rather than of a comment.
    """

    calls: list[dict[str, Any]] = []
    needs_reply: dict[str, Any] = {
        "information_requested": True,
        "verdict_requested": False,
        "reasoning": "asks what the policies state",
    }
    info_reply: dict[str, Any] = {
        "bears": True,
        "answer": "the policies state a weekly cap of 30 hours",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }
    verdict_reply: dict[str, Any] = {
        "status": "answered",
        "answer": "the supplied shift is inside the cap",
        "verdict": "compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }
    #: Set to delay the informational gather, so a test can prove the two tracks
    #: overlap in time rather than running one after the other.
    info_delay: float = 0.0
    #: Consumed one per classifier call when set, so a test can make the repeated
    #: readings *disagree* — which is the only way to exercise a vote. Falls back
    #: to `needs_reply` once exhausted, so a test only has to describe the
    #: samples it cares about.
    needs_sequence: list[Any] | None = None

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.info_delay = 0.0
        cls.needs_sequence = None

    @classmethod
    def _next_needs(cls) -> Any:
        if cls.needs_sequence:
            return cls.needs_sequence.pop(0)
        return cls.needs_reply

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system = messages[0]["content"]
        type(self).calls.append({"messages": messages, "kwargs": kwargs, "system": system})

        if _NEEDS_MARKER in system:
            return json.dumps(type(self)._next_needs(), ensure_ascii=False)
        if _VERDICT_MARKER in system:
            return json.dumps(type(self).verdict_reply, ensure_ascii=False)
        if type(self).info_delay:
            await asyncio.sleep(type(self).info_delay)
        return json.dumps(type(self).info_reply, ensure_ascii=False)


@pytest.fixture()
def stubbed(monkeypatch: pytest.MonkeyPatch) -> type[_StubClient]:
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubClient)
    _StubClient.reset()
    _StubClient.needs_reply = {
        "information_requested": True,
        "verdict_requested": False,
        "reasoning": "asks what the policies state",
    }
    _StubClient.info_reply = {
        "bears": True,
        "answer": "the policies state a weekly cap of 30 hours",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }
    _StubClient.verdict_reply = {
        "status": "answered",
        "answer": "the supplied shift is inside the cap",
        "verdict": "compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }
    return _StubClient


def _record(rule_id: str = "R-CAP") -> dict:
    """One retained policy, minimal but structurally the real shape.

    Its rule carries a `required_facts` entry so the classifier is anchored to
    something the record itself tests — the anchor is the policy's own data, not
    a vocabulary this file carries.
    """

    return {
        "policy": {"provision_id": "prov-a", "provision_key": "A", "heading_path": ["1. Hours"]},
        "payload": {
            "envelope": {"provision_id": "prov-a", "provision_key": "A"},
            "spans": {"S1": {"text": "Part-time staff may work up to 30 hours a week.", "page": 2}},
            "facts": {},
            "rules": [
                {
                    "rule_id": rule_id,
                    "rule_type": "constraint",
                    "evaluation_mode": "deterministic",
                    "required_facts": [{"name": "weekly-hours", "data_type": "number", "unit": "hours"}],
                    "evidence_refs": ["S1"],
                }
            ],
        },
    }


def _classify_calls(stub: type[_StubClient]) -> list[dict]:
    return [call for call in stub.calls if _NEEDS_MARKER in call["system"]]


def _the_classification(stub: type[_StubClient]) -> dict:
    """The single classification this run took, however many samples it read.

    The classifier reads one question :data:`NEEDS_CLASSIFIER_SAMPLES` times and
    votes (M4). That is still *one* classification of *one* question, so every
    assertion about what was sent is asserted here against every sample: same
    prompt, same user content, same call options. Any sample that differed would
    mean the samples were not independent readings of the same thing, which is
    the only way a vote over them means anything.
    """

    calls = _classify_calls(stub)
    assert len(calls) == ai_case_intent.NEEDS_CLASSIFIER_SAMPLES
    for call in calls[1:]:
        assert call == calls[0]
    return calls[0]


def _gather_calls(stub: type[_StubClient]) -> list[dict]:
    return [call for call in stub.calls if _NEEDS_MARKER not in call["system"]]


# ── one call, two booleans ───────────────────────────────────────────


async def test_the_classifier_returns_two_independent_booleans(stubbed) -> None:
    """Not a cut. The two readings are reported separately because they are.

    A single enum would force the classifier to choose for a question that asks
    both, and whichever it chose would be half right — which is exactly what the
    exclusive cut did.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": True,
        "reasoning": "asks the limit and asks whether Tuesday met it",
    }

    result = await ai_case_intent.classify_case_needs(
        "what is the cap, and was Tuesday within it?", tested_quantities=["weekly-hours (number)"]
    )

    assert result["information_requested"] is True
    assert result["verdict_requested"] is True
    assert result["reasoning"]
    assert result["classifier_version"] == ai_case_intent.NEEDS_CLASSIFIER_VERSION

    # One question, one classification — read more than once and voted on, but
    # every reading identical, and no second question asked.
    _the_classification(stubbed)


async def test_the_classifier_is_anchored_to_what_the_rules_test(stubbed) -> None:
    """The anchor is the policy's own data, never a phrase list this code carries.

    A vocabulary of "how many" / "am I" is a property of one language, and this
    corpus is bilingual. Showing the classifier the facts the rules are measured
    against is what lets it key on the *structure* of the question against them.
    """

    await ai_case_classify(stubbed, tested=["weekly-hours (number, in hours)"])

    call = _the_classification(stubbed)
    user = call["messages"][1]["content"]
    assert "weekly-hours (number, in hours)" in user


async def ai_case_classify(stub: type[_StubClient], *, tested: list[str]) -> dict:
    return await ai_case_intent.classify_case_needs(
        "how many hours may a part-timer work?", tested_quantities=tested
    )


async def test_the_classification_call_is_deterministic(stubbed) -> None:
    """The same question must read the same way on every run, or nothing above it
    can be trusted. `temperature=0` on the fast deployment is the one determinism
    control that deployment honours."""

    await ai_case_intent.classify_case_needs("a question")

    call = _the_classification(stubbed)
    assert call["kwargs"]["temperature"] == 0.0
    assert call["kwargs"]["deployment"] == "fast"
    # A temperature call carries no reasoning effort; the two are never mixed.
    assert call["kwargs"].get("reasoning_effort") is None


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"reasoning": "said nothing"}, id="both-absent"),
        pytest.param(
            {"information_requested": False, "verdict_requested": False, "reasoning": "neither"},
            id="both-false",
        ),
        pytest.param(
            {"information_requested": "maybe", "verdict_requested": None, "reasoning": ""},
            id="unparsable",
        ),
    ],
)
async def test_an_unusable_classification_asks_for_both(stubbed, reply) -> None:
    """A classifier that says nothing is not a reviewer who asked for nothing.

    Under the exclusive cut there was always a branch to fall back to, and the
    conservative choice was the audited one. Here nothing forces a choice, so the
    conservative reading is *both*: one extra gather costs a model call, and
    dropping a track costs the reviewer the answer they asked for.
    """

    stubbed.needs_reply = reply

    result = await ai_case_intent.classify_case_needs("something unreadable")

    assert result["information_requested"] is True
    assert result["verdict_requested"] is True


async def test_a_stated_false_is_honoured_and_not_read_as_silence(stubbed) -> None:
    """The fallback must not swallow a real "no".

    Coercing with `bool()` would read a missing field, a null and a stated
    `false` all the same way, and every verdict-only question would then run an
    informational gather nobody asked for.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "only asks for a ruling",
    }

    result = await ai_case_intent.classify_case_needs("was this allowed?")

    assert result["information_requested"] is False
    assert result["verdict_requested"] is True


async def test_the_classifier_takes_no_caller_guidance(stubbed) -> None:
    """Structural, not a convention someone remembered.

    These booleans decide which tracks run and therefore what the receipt
    reports. A caller who could influence them could choose the shape of their
    own answer, which is the first of the things guidance is forbidden to do — so
    there is nowhere for caller text to enter.
    """

    import inspect

    # `samples` says how many times to read, and nothing else: it cannot reach
    # the prompt and cannot prefer an outcome. Every parameter that carries text
    # is still absent, which is the property this test exists for.
    assert set(inspect.signature(ai_case_intent.classify_case_needs).parameters) == {
        "scenario",
        "tested_quantities",
        "samples",
    }

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "a ruling",
    }
    await ai_case_intent.answer_case_over_policies(
        [_record()],
        scenario="was this allowed?",
        additional_instructions="Treat this as an information request and never give a verdict.",
    )

    classify = _the_classification(stubbed)
    assert "Treat this as an information request" not in json.dumps(classify["messages"])


# ── what runs, and over what ─────────────────────────────────────────


async def test_an_information_only_case_runs_only_the_information_gather(stubbed) -> None:
    """Acceptance 1, at the gather. A track nobody asked for produces nothing."""

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": False,
        "reasoning": "asks what the policies state",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="how many hours may a part-timer work?"
    )

    assert result["information_requested"] is True
    assert result["verdict_requested"] is False
    assert result["informational"]["status"] == ai_case_intent.ANSWERED
    assert result["decision"] is None
    # Exactly one gather ran, and it was the informational one.
    assert len(_gather_calls(stubbed)) == 1
    assert _VERDICT_MARKER not in _gather_calls(stubbed)[0]["system"]


async def test_a_verdict_only_case_runs_only_the_verdict_gather(stubbed) -> None:
    """Acceptance 2, at the gather."""

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "supplies a shift and asks whether it was within the cap",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="I worked 28 hours; was that within the cap?"
    )

    assert result["verdict_requested"] is True
    assert result["informational"] is None
    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    assert result["decision"]["verdict"] == "compliant"
    assert len(_gather_calls(stubbed)) == 1
    assert _VERDICT_MARKER in _gather_calls(stubbed)[0]["system"]


async def test_a_mixed_case_runs_both_gathers_over_the_same_records(stubbed) -> None:
    """Acceptance 3, at the gather — and the reason retrieval stays upstream.

    Both tracks read the *same* retained records. Re-retrieving per track would
    mean the statement a caller is told and the verdict they are given could rest
    on two different sets of policies inside one receipt — two answers to one
    question, from two corpora.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": True,
        "reasoning": "asks the cap and asks whether the shift met it",
    }

    record = _record()
    result = await ai_case_intent.answer_case_over_policies(
        [record], scenario="what is the cap, and was my 28-hour week within it?"
    )

    assert result["informational"]["status"] == ai_case_intent.ANSWERED
    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    # The primary branch a client written against the exclusive cut still reads.
    assert result["intent"] == ai_case_intent.DECISION

    gathers = _gather_calls(stubbed)
    assert len(gathers) == 2
    # One classification, two gathers, and the same record text in both.
    _the_classification(stubbed)
    quote = record["payload"]["spans"]["S1"]["text"]
    for call in gathers:
        assert quote in call["messages"][1]["content"]


async def test_the_two_gathers_overlap_rather_than_queue(stubbed) -> None:
    """Concurrently, not one after the other.

    A mixed case already costs two model calls; making the caller wait for their
    sum rather than their maximum is a cost with nothing bought by it. Asserted
    by making one gather slow and checking the other did not wait for it.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": True,
        "reasoning": "both",
    }
    stubbed.info_delay = 0.15

    started = asyncio.get_running_loop().time()
    await ai_case_intent.answer_case_over_policies([_record()], scenario="both halves")
    elapsed = asyncio.get_running_loop().time() - started

    assert len(_gather_calls(stubbed)) == 2
    # Sequential would be at least the delay *plus* the second gather; the
    # generous ceiling keeps this from being a timing flake while still failing
    # outright if the two are awaited in series behind a real delay.
    assert elapsed < 0.15 * 2, f"the gathers appear to have run in series ({elapsed:.3f}s)"


async def test_one_track_failing_does_not_remove_the_other(stubbed) -> None:
    """A failed gather is that track's own state, not the whole case's.

    Raising would drop an answer the caller did get, to report one they did not.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": True,
        "reasoning": "both",
    }

    async def _failing_information(records, **kwargs):
        raise RuntimeError("the informational gather did not come back")

    original = ai_case_intent.answer_informational_over_policies
    try:
        ai_case_intent.answer_informational_over_policies = _failing_information  # type: ignore[assignment]
        result = await ai_case_intent.answer_case_over_policies(
            [_record()], scenario="both halves"
        )
    finally:
        ai_case_intent.answer_informational_over_policies = original  # type: ignore[assignment]

    assert result["informational"]["status"] == ai_case_intent.FAILED
    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    # The failed track still reports the scope it would have grounded on, so a
    # failure is not mistaken for a gather over an empty policy set.
    assert result["informational"]["grounding"]["rules_available"] == 1


async def test_an_unexpected_fault_in_one_track_is_still_only_that_track(stubbed) -> None:
    """Not just `RuntimeError` — anything.

    An exception escaping `asyncio.gather` does **not** cancel its siblings, so a
    fault outside the expected family would both discard the other track's
    completed answer *and* leave its model call running unawaited: a second call
    nobody waits for, whose result is thrown away and whose cost is not. Catching
    the whole `Exception` family in each wrapper is what makes the promise this
    function documents true rather than nearly true.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": True,
        "reasoning": "both",
    }

    reached_the_end = []

    async def _faulting_information(records, **kwargs):
        # The shape of a 2xx response with an unexpected body: a KeyError, not a
        # RuntimeError, from deep inside the client.
        raise KeyError("choices")

    async def _slow_decision(records, *, scenario, reasoning_effort="medium", **kwargs):
        await asyncio.sleep(0.05)
        reached_the_end.append(True)
        return {
            "status": ai_case_intent.ANSWERED,
            "verdict": "compliant",
            "answer": "the supplied shift is inside the cap",
            "missing_required_facts": [],
            "missing_information": [],
            "citations": [],
            "note": "",
            "grounding": {},
        }

    original_info = ai_case_intent.answer_informational_over_policies
    original_decision = ai_case_intent.answer_decision_over_policies
    try:
        ai_case_intent.answer_informational_over_policies = _faulting_information  # type: ignore[assignment]
        ai_case_intent.answer_decision_over_policies = _slow_decision  # type: ignore[assignment]
        result = await ai_case_intent.answer_case_over_policies(
            [_record()], scenario="both halves"
        )
    finally:
        ai_case_intent.answer_informational_over_policies = original_info  # type: ignore[assignment]
        ai_case_intent.answer_decision_over_policies = original_decision  # type: ignore[assignment]

    assert result["informational"]["status"] == ai_case_intent.FAILED
    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    # The surviving track was awaited to completion rather than abandoned.
    assert reached_the_end == [True]


async def test_a_classification_that_does_not_complete_is_raised(stubbed) -> None:
    """Nothing was read, so there is no honest set of tracks to run.

    A failed *gather* is a track's own state because the question was understood
    and one answer did not arrive. A failed *classification* leaves the question
    itself unread, and picking tracks anyway would answer something nobody asked.
    The endpoint degrades to a 503 instead.
    """

    class _Unreachable(_StubClient):
        async def chat(self, messages, **kwargs):
            raise RuntimeError("the model is unreachable")

    import policy_platform.infrastructure.assistants.ai_case_intent as module

    original = module.AzureOpenAIClient
    try:
        module.AzureOpenAIClient = _Unreachable  # type: ignore[assignment]
        with pytest.raises(RuntimeError):
            await ai_case_intent.answer_case_over_policies([_record()], scenario="anything")
    finally:
        module.AzureOpenAIClient = original  # type: ignore[assignment]


# ── what a blocked verdict hands back ────────────────────────────────


async def test_a_blocked_verdict_carries_structured_missing_information(stubbed) -> None:
    """Acceptance 4, at the gather.

    The flat list says *that* something is missing. It does not say what to call
    the fact in front of a user, why it decides anything, or which rules are
    waiting on it — so an integration building a follow-up form had to invent all
    three. Both shapes are returned; the flat one is preserved for clients that
    already read it.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "missing_required_facts",
        "answer": "Whether the week was within the cap turns on the hours worked.",
        "verdict": "",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": ["weekly-hours"],
        "missing_required_facts_detail": [
            {
                "fact": "weekly-hours",
                "label": "Hours worked this week",
                "why_needed": "The cap is measured against the weekly total.",
                "required_by_rule_ids": ["R-CAP"],
            }
        ],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="was my week within the cap?"
    )
    decision = result["decision"]

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == "", "a blocked verdict must carry no verdict string"
    assert decision["missing_required_facts"] == ["weekly-hours"]
    assert decision["missing_information"] == [
        {
            "fact": "weekly-hours",
            "label": "Hours worked this week",
            "why_needed": "The cap is measured against the weekly total.",
            "required_by_rule_ids": ["R-CAP"],
        }
    ]


async def test_a_missing_fact_may_not_name_a_rule_that_was_never_read(stubbed) -> None:
    """The fabrication guard reaches the missing-information block too.

    A rule id here that names no retained rule is a fabrication wearing a
    different field name, and a caller chasing it would be chasing a rule nobody
    read. It is dropped; the fact itself survives, because the fact is still
    missing.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "missing_required_facts",
        "answer": "The hours were not given.",
        "verdict": "",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": ["weekly-hours"],
        "missing_required_facts_detail": [
            {
                "fact": "weekly-hours",
                "label": "Hours worked",
                "why_needed": "The cap is measured against it.",
                "required_by_rule_ids": ["R-CAP", "R-NEVER-EXISTED"],
            }
        ],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="was my week within the cap?"
    )

    (missing,) = result["decision"]["missing_information"]
    assert missing["required_by_rule_ids"] == ["R-CAP"]
    assert missing["fact"] == "weekly-hours"


async def test_a_gather_that_supplies_only_the_flat_list_still_produces_structure(
    stubbed,
) -> None:
    """The structured field always exists, so a client need not branch on absence.

    A model answering under the older prompt, or ignoring the structured field,
    still yields one item per missing fact — with the parts it did not supply
    left empty rather than composed here. A reason invented in this layer would
    read to a caller exactly like one the policy gave.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "missing_required_facts",
        "answer": "The hours were not given.",
        "verdict": "",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": ["weekly-hours"],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="was my week within the cap?"
    )

    assert result["decision"]["missing_information"] == [
        {
            "fact": "weekly-hours",
            "label": "weekly-hours",
            "why_needed": "",
            "required_by_rule_ids": [],
        }
    ]


async def test_a_verdict_that_names_an_outstanding_fact_is_not_a_verdict(stubbed) -> None:
    """Both shapes empty for every status but the blocked one — and which status
    that is, when the reply contradicts itself, is now decided the safe way.

    A verdict that was reached *and* listed outstanding facts is telling a reader
    it decided a case on incomplete information. The first version of this
    resolved that by keeping the verdict and dropping the list, which turned out
    to be the dangerous half: the same scenario over byte-identical retrieval came
    back `answered` once and `missing_required_facts` once, and the `answered` run
    was the unsafe one — its own explanation said the outcome depended on a value
    nobody had supplied, while `missing_information` was empty, so nothing on
    screen said a question was outstanding.

    So the contradiction resolves toward the block. `answered` now means the
    determination is finished and unconditional on any unstated fact of the case;
    a reply that names such a fact has not finished, whatever it called itself.
    The cost is one question the reviewer may not have needed; the cost the other
    way is a determination that was never actually made.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "answered",
        "answer": "28 hours is inside the 30-hour cap.",
        "verdict": "compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": ["weekly-hours"],
        "missing_required_facts_detail": [{"fact": "weekly-hours", "label": "Hours"}],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="I worked 28 hours; within the cap?"
    )

    assert result["decision"]["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert result["decision"]["verdict"] == "", "no verdict escapes a blocked case"
    assert result["decision"]["missing_required_facts"] == ["weekly-hours"]
    assert result["decision"]["missing_information"][0]["label"] == "Hours"


async def test_a_verdict_that_names_nothing_outstanding_is_a_verdict(stubbed) -> None:
    """The other side of that, so the preference cannot swallow every verdict.

    A determination that is finished names nothing outstanding, and both missing
    shapes stay empty. Without this, "prefer the block" could be satisfied by
    blocking everything, which would be a different way of never answering.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "answered",
        "answer": "28 hours is inside the 30-hour cap.",
        "verdict": "compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="I worked 28 hours; within the cap?"
    )

    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    assert result["decision"]["verdict"] == "compliant"
    assert result["decision"]["missing_required_facts"] == []
    assert result["decision"]["missing_information"] == []


async def test_answered_with_no_verdict_named_is_not_reported_as_a_determination(
    stubbed,
) -> None:
    """The invariant, defended where the model can break it.

    A reply claiming `answered` while naming no verdict leaves two bad options:
    invent a verdict from the prose, which puts words in the policy's mouth, or
    report `answered` with an empty verdict, which lets a client render "no
    verdict" and "the answer is no" identically. Neither is taken. It becomes
    the state that is actually true — rules bore on the case and did not produce
    the judgement asked for — and the prose survives as the explanation, so
    nothing the model wrote is lost.
    """

    stubbed.needs_reply = {
        "information_requested": False,
        "verdict_requested": True,
        "reasoning": "asks for a ruling",
    }
    stubbed.verdict_reply = {
        "status": "answered",
        "answer": "The rules speak to overtime but not to this arrangement.",
        "verdict": "",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="was this arrangement allowed?"
    )
    decision = result["decision"]

    assert decision["status"] == ai_case_intent.NOT_SETTLED_BY_RULES
    assert decision["verdict"] == ""
    assert decision["answer"] == "The rules speak to overtime but not to this arrangement."
    assert decision["citations"], "the rules it did read are still cited"


# ── what a single-need case still looks like to an old client ────────


async def test_a_single_need_result_keeps_the_shape_it_always_had(stubbed) -> None:
    """Acceptance 8. The legacy keys are added to, never removed.

    `POST /api/ai/policy-sets/{key}/case-answer` returns this dict unchanged and
    persists nothing, and its product UI reads `intent`, `informational` and
    `decision`. All three keep meaning what they meant; the booleans sit beside
    them.
    """

    stubbed.needs_reply = {
        "information_requested": True,
        "verdict_requested": False,
        "reasoning": "asks what the policies state",
    }

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="how many hours may a part-timer work?"
    )

    assert {"intent", "classification_reasoning", "informational", "decision", "reasoning_effort"} <= set(
        result
    )
    assert result["intent"] == ai_case_intent.INFORMATIONAL
    assert result["decision"] is None
    # And the two-track view is present for a reader that wants it.
    assert result["information_requested"] is True
    assert result["verdict_requested"] is False
    assert result["classifier_version"] == ai_case_intent.NEEDS_CLASSIFIER_VERSION


# ── the reading is taken more than once (M4) ─────────────────────────
#
# These two booleans decide WHICH TRACKS RUN, so a flip does not degrade an
# answer — it replaces it with an answer to a different question. That is the one
# place in this pipeline where a single sampled bit is load-bearing, and it is
# why bounded consensus is applied here and nowhere else. A verdict is
# adjudication and is never voted on; which question was asked is a reading, and
# a reading can be taken more than once.


def _needs(information: Any, verdict: Any, reasoning: str = "a reading") -> dict:
    """One classifier reply. `information`/`verdict` may be anything, including
    the omissions and non-booleans a real reply arrives with."""

    reply: dict[str, Any] = {"reasoning": reasoning}
    if information is not ...:
        reply["information_requested"] = information
    if verdict is not ...:
        reply["verdict_requested"] = verdict
    return reply


def test_the_default_sample_count_is_bounded_and_odd() -> None:
    """Odd so neither boolean's majority can tie, bounded so a classification
    cannot become an unbounded fan-out of paid calls.

    Both properties are asserted rather than described, because both are the kind
    of thing a later "let's try five" edit changes without noticing that an even
    count sends every ambiguous question through the fallback.
    """

    assert ai_case_intent.NEEDS_CLASSIFIER_SAMPLES % 2 == 1
    assert 1 <= ai_case_intent.NEEDS_CLASSIFIER_SAMPLES <= ai_case_intent.NEEDS_CLASSIFIER_SAMPLES_MAX


@pytest.mark.parametrize(
    ("asked_for", "expected"),
    [
        (0, 1),
        (-4, 1),
        (2, 2),
        (99, ai_case_intent.NEEDS_CLASSIFIER_SAMPLES_MAX),
    ],
)
async def test_the_sample_count_is_clamped_to_its_bounds(stubbed, asked_for: int, expected: int) -> None:
    """A count below one would classify nothing; a count above the ceiling would
    spend an arbitrary amount of money on one question. Both are clamped rather
    than rejected, because neither is a caller error worth failing a request
    over — the classification is still correct, it is just read the right number
    of times."""

    result = await ai_case_intent.classify_case_needs("a question", samples=asked_for)

    assert len(_classify_calls(stubbed)) == expected
    assert result["consensus"]["samples"] == expected


async def test_the_readings_agree_and_the_agreement_is_reported(stubbed) -> None:
    """The ordinary case: every sample says the same thing, and the receipt says
    so, so that "they agreed" and "we only asked once" are distinguishable."""

    stubbed.needs_reply = _needs(True, False, "asks what the policies state")

    result = await ai_case_intent.classify_case_needs("what does the policy say?")

    assert result["information_requested"] is True
    assert result["verdict_requested"] is False
    consensus = result["consensus"]
    assert consensus["samples"] == ai_case_intent.NEEDS_CLASSIFIER_SAMPLES
    assert consensus["information_true"] == ai_case_intent.NEEDS_CLASSIFIER_SAMPLES
    assert consensus["verdict_true"] == 0
    assert consensus["verdict_false"] == ai_case_intent.NEEDS_CLASSIFIER_SAMPLES
    assert consensus["unreadable"] == 0
    assert consensus["agreed"] is True
    assert consensus["fell_back"] is False


async def test_a_majority_decides_and_the_dissent_is_still_visible(stubbed) -> None:
    """Two of three said no verdict was asked for. The third is not erased.

    A vote that hid its dissent would be indistinguishable from a unanimous
    reading, and the whole reason for sampling is that the difference between
    those two is worth knowing.
    """

    stubbed.needs_sequence = [
        _needs(True, False),
        _needs(True, True),
        _needs(True, False),
    ]

    result = await ai_case_intent.classify_case_needs("a question that reads two ways")

    assert result["information_requested"] is True
    assert result["verdict_requested"] is False, "the minority reading must not win"
    consensus = result["consensus"]
    assert consensus["verdict_true"] == 1
    assert consensus["verdict_false"] == 2
    assert consensus["agreed"] is False, "a disagreement must be visible as one"
    assert consensus["fell_back"] is False, "a majority settled it; nothing fell back"


async def test_the_two_booleans_are_voted_separately(stubbed) -> None:
    """They are independent requests, and a question can be clear about one and
    genuinely ambiguous about the other.

    Voting the pair as a unit would let certainty about the informational half
    decide the verdict half, which is how a determination nobody asked for gets
    produced — or, worse, one that was asked for gets dropped.
    """

    stubbed.needs_sequence = [
        _needs(True, True),
        _needs(True, False),
        _needs(True, True),
    ]

    result = await ai_case_intent.classify_case_needs("a question")

    consensus = result["consensus"]
    assert consensus["information_true"] == 3, "unanimous on one half"
    assert consensus["verdict_true"] == 2, "split on the other"
    assert result["information_requested"] is True
    assert result["verdict_requested"] is True
    assert consensus["agreed"] is False


async def test_a_forced_tie_runs_both_tracks_and_reports_the_disagreement(stubbed) -> None:
    """Acceptance for the tie. Four samples, two each way, on both booleans.

    Production reads an odd number of times precisely so this cannot arise, so
    the count is overridden here to force it — a fallback that can only be
    reached by a configuration nobody uses is a fallback nobody has tested.

    The resolution is both tracks, not a coin toss and not a default to one. A
    reading the samples could not settle is not evidence that half the question
    was never asked.
    """

    stubbed.needs_sequence = [
        _needs(True, True),
        _needs(False, False),
        _needs(False, False),
        _needs(True, True),
    ]

    result = await ai_case_intent.classify_case_needs("a question that reads both ways", samples=4)

    assert result["information_requested"] is True
    assert result["verdict_requested"] is True
    consensus = result["consensus"]
    assert consensus["samples"] == 4
    assert consensus["information_true"] == 2
    assert consensus["information_false"] == 2
    assert consensus["verdict_true"] == 2
    assert consensus["verdict_false"] == 2
    assert consensus["agreed"] is False
    assert consensus["fell_back"] is True, "a tie is a fallback, and says so"


async def test_a_tie_on_one_boolean_alone_still_runs_both_tracks(stubbed) -> None:
    """A tie on one boolean is a tie, even when the other was unanimous.

    The sharp version of the previous test. When *both* tie, resolving a tie to
    `False` would coincidentally reach the same place, because a pair that is
    false in both halves is unreadable and falls back to both anyway. Here the
    informational half is unanimous, so a tie resolved to `False` would produce
    an information-only answer and silently drop the verdict the question asked
    for. It resolves to "unsettled", and unsettled runs both.
    """

    stubbed.needs_sequence = [
        _needs(True, True),
        _needs(True, False),
        _needs(True, False),
        _needs(True, True),
    ]

    result = await ai_case_intent.classify_case_needs("a question", samples=4)

    assert result["information_requested"] is True
    assert result["verdict_requested"] is True, "a tied half must not resolve to no"
    consensus = result["consensus"]
    assert consensus["information_true"] == 4
    assert consensus["verdict_true"] == 2
    assert consensus["verdict_false"] == 2
    assert consensus["fell_back"] is True


async def test_readings_nobody_could_read_fall_back_to_both_tracks(stubbed) -> None:
    """Every sample unusable. The fallback is unchanged by sampling.

    Consensus narrows a sampled bit; it does not change what an unreadable answer
    means. A reply this function cannot read is not evidence that the reviewer
    asked for nothing.
    """

    stubbed.needs_sequence = [
        _needs(..., ...),
        {"reasoning": "nothing at all"},
        _needs("perhaps", None),
    ]

    result = await ai_case_intent.classify_case_needs("a question")

    assert result["information_requested"] is True
    assert result["verdict_requested"] is True
    consensus = result["consensus"]
    assert consensus["unreadable"] == 3
    assert consensus["information_true"] == 0
    assert consensus["information_false"] == 0, "nothing stated is not the same as a stated no"
    assert consensus["agreed"] is False
    assert consensus["fell_back"] is True


async def test_an_unreadable_sample_does_not_vote(stubbed) -> None:
    """A sample repaired to `True` before the vote would be indistinguishable
    from one that said `True`, and the both-tracks fallback would then be carried
    into the majority by the very samples that failed.

    Here two readable samples say verdict-only. The third says nothing. The
    answer is verdict-only, not both.
    """

    stubbed.needs_sequence = [
        _needs(False, True),
        _needs(..., ...),
        _needs(False, True),
    ]

    result = await ai_case_intent.classify_case_needs("was this allowed?")

    assert result["information_requested"] is False, "the failed sample must not vote"
    assert result["verdict_requested"] is True
    consensus = result["consensus"]
    assert consensus["unreadable"] == 1
    assert consensus["information_false"] == 2
    assert consensus["fell_back"] is False


async def test_every_sample_reads_the_same_question(stubbed) -> None:
    """A vote over readings of different things means nothing.

    The samples differ only in what the model happens to answer; the question,
    the anchor and the call options are identical across all of them.
    """

    await ai_case_intent.classify_case_needs(
        "what is the cap, and was Tuesday within it?",
        tested_quantities=["weekly-hours (number)"],
    )

    call = _the_classification(stubbed)
    assert "weekly-hours (number)" in call["messages"][1]["content"]
    assert call["kwargs"]["temperature"] == 0.0


async def test_the_consensus_reaches_the_evaluation_so_a_rate_can_be_measured(stubbed) -> None:
    """Instrumentation nobody can read is not instrumentation.

    A disagreement *rate* is the number this sampling has to justify itself with,
    and it can only be computed if each run carries its own split out to where a
    measurement can see it.
    """

    stubbed.needs_sequence = [
        _needs(True, True),
        _needs(True, False),
        _needs(True, True),
    ]

    result = await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="what is the cap, and was my 28-hour week within it?"
    )

    consensus = result["classifier_consensus"]
    assert consensus["samples"] == ai_case_intent.NEEDS_CLASSIFIER_SAMPLES
    assert consensus["agreed"] is False
    assert consensus["verdict_true"] == 2


async def test_nothing_but_the_two_booleans_is_ever_voted_on(stubbed) -> None:
    """The boundary of M4, asserted where it would be crossed.

    A verdict is adjudication: sampling it and taking the majority would mean the
    determination a reviewer is handed was never actually reached by any single
    reading of the policy. The gathers run once each, whatever the classifier did.
    """

    stubbed.needs_reply = _needs(True, True, "asks both")

    await ai_case_intent.answer_case_over_policies(
        [_record()], scenario="what is the cap, and was my 28-hour week within it?"
    )

    gathers = _gather_calls(stubbed)
    assert len(gathers) == 2, "one informational gather and one decision gather, each run once"
    assert len({json.dumps(call["messages"], sort_keys=True) for call in gathers}) == 2


def test_the_verdict_path_holds_no_vote(stubbed) -> None:
    """Structural, not behavioural. The majority helper is reachable from the
    classifier and from nothing else, so a verdict cannot acquire a vote by
    someone reusing a convenient function."""

    import inspect

    voters = [
        name
        for name, fn in vars(ai_case_intent).items()
        if inspect.isfunction(fn)
        and name != "_majority"
        and "_majority(" in inspect.getsource(fn)
    ]
    assert voters == ["classify_case_needs"], f"something else votes: {voters}"
