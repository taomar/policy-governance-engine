"""What a case *is* is read from the question, by the model, and never from a
list of words.

WHY THIS FILE EXISTS

A case put to a policy is either a request for what the policy provides or a
description of a situation awaiting a determination. Getting that wrong is the
defect this feature repairs: an informational request run as a determination
reports the rule that *states* the answer as unsettled, because as a
determination that rule needs the very quantity the reviewer was asking about.

WHY THE GUARD IS BEHAVIOURAL

The one thing this must never become is a vocabulary of trigger phrases —
"how many", "can I", "am I". Such a list is a property of one language, and this
corpus is bilingual; it would sort the English clause and be blind to the Arabic
one that asks the same thing. So the intent is the model's to decide.

A test that mocks the model and asserts the model's verdict is what comes back
is exactly a test that fails the moment someone adds a phrase list. If a fast
path read "how many" and returned "informational", the first test below — whose
question contains "how many" while the model is told to answer "decision" —
would get "informational" and fail. The same holds for a phrase list used to
override the model or to break a tie. There is deliberately no scan of this
module's own source for the banned words: the module's docstring names them in
order to forbid them, and a source scan would catch the prohibition as if it
were the crime.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation
from policy_platform.contracts.policy import RequiredFact
from policy_platform.infrastructure.assistants import ai_case_intent
from tests.fixtures.factories import make_rule

pytestmark = pytest.mark.anyio


#: A synthetic cap, in the document's own words. Not any real policy's sentence:
#: the behaviour under test must hold for any corpus, so the fixture states a
#: rule no document in this repository contains.
VERBATIM_EN = "Part-time staff are engaged to work no more than twenty-four hours in any week."
#: The same kind of clause in Arabic, to prove a quote is returned as characters
#: rather than as \\uXXXX escapes and is never translated on its way back.
VERBATIM_AR = "لا يعمل الموظفون بدوام جزئي أكثر من أربع وعشرين ساعة في الأسبوع."


class _Settings:
    ai_enabled = True
    azure_openai_deployment = "slow"


class _StubClient:
    """Stands in for the model. Serves the classify call and the informational
    call apart, by reading which system prompt it was handed, and keeps every
    message so a test can prove what was and was not sent."""

    calls: list[dict[str, Any]] = []
    classify_reply: dict[str, Any] = {"intent": "decision", "reasoning": "a reason"}
    info_reply: dict[str, Any] = {
        "bears": False,
        "answer": "",
        "cited_rule_ids": [],
        "declined": False,
        "note": "",
    }
    fail: bool = False
    #: Fail only the informational gather, letting classification succeed. This
    #: is the shape that proves a *known* informational request whose answer did
    #: not come back is its own state, not the determination fallback.
    fail_info: bool = False

    def __init__(self, settings: Any) -> None:  # noqa: D107 - shape only
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).calls.append({"messages": messages, "kwargs": kwargs})
        system = messages[0]["content"]
        is_classify = "sort one question" in system
        if type(self).fail or (type(self).fail_info and not is_classify):
            raise RuntimeError("the model call failed")
        reply = type(self).classify_reply if is_classify else type(self).info_reply
        return json.dumps(reply, ensure_ascii=False)


@pytest.fixture()
def stubbed(monkeypatch: pytest.MonkeyPatch) -> type[_StubClient]:
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubClient)
    _StubClient.calls = []
    _StubClient.classify_reply = {"intent": "decision", "reasoning": "a reason"}
    _StubClient.info_reply = {
        "bears": False,
        "answer": "",
        "cited_rule_ids": [],
        "declined": False,
        "note": "",
    }
    _StubClient.fail = False
    _StubClient.fail_info = False
    return _StubClient


def _cap_rule(source_text: str = VERBATIM_EN):
    """A rule that names a weekly-hours quantity and states its own answer.

    It carries an unmet required fact on purpose: this is the shape that, run as
    a determination, demands the number the reviewer is asking for. The point of
    the informational path is that it reports what the rule *states* instead.
    """

    rule = make_rule("R-CAP", condition=AllCondition(all=[]), machine_executable=True)
    return rule.model_copy(
        update={
            "title": "Weekly hours for part-time staff",
            "description": "Part-time staff have a weekly ceiling on their hours.",
            "required_facts": [RequiredFact(name="weekly-hours", data_type="number")],
            "formulation": RuleFormulation(canonical=CanonicalPolicy(source_text=source_text)),
        }
    )


def _bystander_rule():
    """A rule on another subject entirely, present so 'lead with what bears'
    has something it must not lead with."""

    rule = make_rule("R-OTHER", condition=AllCondition(all=[]), machine_executable=False)
    return rule.model_copy(
        update={
            "title": "Notice of resignation",
            "description": "An employee gives notice before leaving.",
            "required_facts": [],
            "formulation": RuleFormulation(
                canonical=CanonicalPolicy(source_text="An employee gives one month of notice.")
            ),
        }
    )


# --------------------------------------------------------------------------- #
# The intent is the model's, not a phrase list's.
# --------------------------------------------------------------------------- #


async def test_a_question_worded_as_a_request_still_follows_the_model(stubbed):
    """The question reads like an information request — it contains "how many" —
    and the model is told to call it a determination. The model wins. A phrase
    list keyed on "how many" would return "informational" here and fail."""

    stubbed.classify_reply = {"intent": "decision", "reasoning": "It describes a case."}

    result = await ai_case_intent.classify_case_intent(
        "How many hours may a part-time employee work per week?"
    )

    assert result["intent"] == "decision"


async def test_a_question_worded_as_a_statement_still_follows_the_model(stubbed):
    """The converse. The question states facts and names a number, which a
    "states facts, therefore a determination" heuristic would seize on. The
    model calls it informational, and that is what comes back."""

    stubbed.classify_reply = {"intent": "informational", "reasoning": "It asks what the policy provides."}

    result = await ai_case_intent.classify_case_intent(
        "A part-time employee worked thirty hours last week."
    )

    assert result["intent"] == "informational"


async def test_the_classifier_is_handed_the_question_and_nothing_else(stubbed):
    """Intent is a property of the question, so the classifier is given the
    question alone — no policy, no rule ids, no digests. If a rule ever reached
    it, the intent could be tuned to one document's wording."""

    await ai_case_intent.classify_case_intent("How many hours may a part-timer work?")

    assert len(stubbed.calls) == 1
    system, user = stubbed.calls[0]["messages"]
    assert "sort one question" in system["content"]
    assert "How many hours" in user["content"]
    # None of the digest a rule would arrive as.
    for leaked in ("rule_id", "statement", "concerns", "R-CAP"):
        assert leaked not in user["content"]


async def test_an_unreadable_verdict_falls_back_to_a_determination(stubbed):
    """A verdict the app cannot read routes the case to the deciders that
    already exist, never to a composed answer. The question again contains
    "how many", so a phrase list used only as a tie-breaker is caught here too."""

    stubbed.classify_reply = {"intent": "banana", "reasoning": "?"}

    result = await ai_case_intent.classify_case_intent("How many days of leave can I take?")

    assert result["intent"] == "decision"


# --------------------------------------------------------------------------- #
# The acceptance test: informational + an unmet required fact -> stated content.
# --------------------------------------------------------------------------- #


async def test_an_informational_request_reports_what_a_rule_states_not_a_demand(stubbed):
    """A rule with an unmet required fact, asked informationally, yields the
    sentence it states — verbatim — and never a demand for the fact.

    This is the whole repair. Run as a determination the same rule asks the case
    to supply "weekly-hours"; run as an information request it hands back the
    ceiling it already names."""

    stubbed.classify_reply = {"intent": "informational", "reasoning": "Asks what the policy provides."}
    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time staff are capped at twenty-four hours per week.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    out = await ai_case_intent.answer_policy_case(
        [_cap_rule().model_dump(mode="json"), _bystander_rule().model_dump(mode="json")],
        scenario="How many hours may a part-timer work?",
    )

    assert out["intent"] == "informational"
    info = out["informational"]
    assert info["status"] == "answered"

    # The rule's own sentence, returned exactly.
    assert info["citations"][0]["rule_id"] == "R-CAP"
    assert info["citations"][0]["quote"] == VERBATIM_EN

    # Nowhere is the fact demanded. The required-fact name does not surface, and
    # none of the determination path's "you must state X" wording appears.
    blob = json.dumps(info, ensure_ascii=False).lower()
    assert "weekly-hours" not in blob
    assert "would have to state" not in blob
    assert "missing" not in blob


async def test_a_determination_is_left_to_the_deciders_that_already_exist(stubbed):
    """The server never turns a determination into a composed answer. For a
    decision case it classifies and stops, so the per-rule deciders — the ones
    that correctly demand an unmet fact — run unchanged on the caller's side."""

    stubbed.classify_reply = {"intent": "decision", "reasoning": "Describes a situation."}

    out = await ai_case_intent.answer_policy_case(
        [_cap_rule().model_dump(mode="json")],
        scenario="Someone works thirty hours a week; are they within the cap?",
    )

    assert out["intent"] == "decision"
    assert out["informational"] is None
    # Only the classify call was made; the informational gatherer never ran.
    systems = [call["messages"][0]["content"] for call in stubbed.calls]
    assert systems and all("sort one question" in system for system in systems)


# --------------------------------------------------------------------------- #
# Four states, kept apart.
# --------------------------------------------------------------------------- #


async def test_a_policy_that_holds_nothing_on_the_subject_says_so(stubbed):
    """Absent: no rule bears. Not a refusal and not a failure."""

    stubbed.info_reply = {"bears": False, "answer": "", "cited_rule_ids": [], "declined": False, "note": ""}

    info = await ai_case_intent.answer_informational(
        [_bystander_rule()], scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "no_rule_bears"
    assert info["citations"] == []


async def test_a_model_that_stands_back_is_not_a_policy_that_holds_nothing(stubbed):
    """Refused: the model declined. Distinct from absent."""

    stubbed.info_reply = {"bears": True, "answer": "", "cited_rule_ids": ["R-CAP"], "declined": True, "note": ""}

    info = await ai_case_intent.answer_informational(
        [_cap_rule()], scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "declined"


async def test_rules_bearing_but_no_answer_composed_is_also_a_standing_back(stubbed):
    """Refused by absence of an answer rather than by the flag: rules bear, but
    the model wrote nothing. Still not 'the policy holds nothing'."""

    stubbed.info_reply = {"bears": True, "answer": "", "cited_rule_ids": ["R-CAP"], "declined": False, "note": ""}

    info = await ai_case_intent.answer_informational(
        [_cap_rule()], scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "declined"


async def test_a_failed_request_is_raised_not_reported_as_absent(stubbed):
    """Failed: the request never completed. It must not be reducible to any of
    the three content states, so it is raised for the endpoint to turn into its
    own reply rather than returned as 'no rule bears'."""

    stubbed.fail = True

    with pytest.raises(RuntimeError):
        await ai_case_intent.answer_informational(
            [_cap_rule()], scenario="How many hours may a part-timer work?"
        )


# --------------------------------------------------------------------------- #
# The document's words reach the reader unchanged.
# --------------------------------------------------------------------------- #


async def test_a_cited_quote_is_the_records_own_words_not_the_models(stubbed):
    """The answer is the app's; the quote is the document's. The model could
    return any wording for the answer, but the citation is taken from the record
    here, so a model that paraphrased could not alter what is quoted."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "A paraphrase the model invented.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        [_cap_rule(source_text=VERBATIM_EN)], scenario="How many hours may a part-timer work?"
    )

    assert info["citations"][0]["quote"] == VERBATIM_EN


async def test_an_arabic_quote_is_returned_as_characters_and_untranslated(stubbed):
    """A quote in Arabic comes back in Arabic, as characters, exactly."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time staff have a weekly ceiling.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        [_cap_rule(source_text=VERBATIM_AR)], scenario="كم ساعة يعمل الموظف بدوام جزئي؟"
    )

    assert info["citations"][0]["quote"] == VERBATIM_AR
    assert "\\u" not in json.dumps(info["citations"][0]["quote"], ensure_ascii=False)


async def test_a_citation_to_a_rule_not_in_the_policy_is_dropped(stubbed):
    """The model may only cite rules in front of the reader. An id that names no
    rule here is not a citation, and if nothing valid is left the answer is not
    'answered' — it cannot be grounded."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "An answer citing a rule that is not here.",
        "cited_rule_ids": ["R-GHOST"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        [_cap_rule()], scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "no_rule_bears"
    assert info["citations"] == []


# --------------------------------------------------------------------------- #
# The grounding is reported, and is shown refusing something.
#
# A grounding check that is only ever performed and never seen to reject anything
# is the "validator that could not fail" this repository documents. These tests
# watch it refuse a citation to a rule that was never in the payload, and prove
# the refusal is *reported* on the answer rather than only performed in silence.
# --------------------------------------------------------------------------- #


async def test_a_fabricated_citation_is_caught_and_reported(stubbed):
    """The model cites one rule that exists and one that does not. The real one
    is kept; the invented one is dropped from the citations *and* named in the
    grounding, so the check is seen to have refused something rather than merely
    asserting it stayed grounded."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time staff are capped at twenty-four hours per week.",
        "cited_rule_ids": ["R-CAP", "R-GHOST"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        [_cap_rule(), _bystander_rule()], scenario="How many hours may a part-timer work?"
    )

    # The answer stands, resting only on the rule that is actually present.
    assert info["status"] == "answered"
    assert [c["rule_id"] for c in info["citations"]] == ["R-CAP"]

    # The fabrication is not silently gone: it is reported, and the counts add up.
    grounding = info["grounding"]
    assert grounding["fabricated_citations"] == ["R-GHOST"]
    assert grounding["citations_requested"] == 2
    assert grounding["rules_cited"] == 1
    assert grounding["rules_available"] == 2
    assert grounding["oversize"] is False


async def test_an_answer_resting_only_on_a_fabrication_is_not_presented_as_answered(stubbed):
    """When every id the model offered names no rule in the payload, there is
    nothing to ground an answer on. It cannot be `answered`, and the fabrication
    is still reported so a reader can see why the answer did not stand."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "An answer resting entirely on a rule that is not here.",
        "cited_rule_ids": ["R-GHOST"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        [_cap_rule()], scenario="How many hours may a part-timer work?"
    )

    assert info["status"] != "answered"
    assert info["citations"] == []
    assert info["grounding"]["fabricated_citations"] == ["R-GHOST"]
    assert info["grounding"]["rules_cited"] == 0


async def test_a_policy_too_large_to_ground_is_declined_not_truncated(stubbed):
    """When the whole policy's records will not fit one grounded pass, the gather
    is refused, not trimmed. No model call is made, the refusal is reported as its
    own grounding fact, and the count is the *whole* policy's — an answer over a
    silently dropped subset would be the narrowing a reviewer could not see."""

    # Shrink the ceiling so even a two-rule policy exceeds it, rather than build a
    # giant fixture; the behaviour under test is the size decision, not the size.
    stubbed.info_reply = {
        "bears": True,
        "answer": "An answer that must never be composed from a partial policy.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ai_case_intent, "_MAX_RECORD_CHARS", 10)
        info = await ai_case_intent.answer_informational(
            [_cap_rule(), _bystander_rule()], scenario="How many hours may a part-timer work?"
        )

    assert info["status"] == "declined"
    assert info["citations"] == []
    assert info["grounding"]["oversize"] is True
    # The whole policy is still counted, and no rule was quietly dropped to fit.
    assert info["grounding"]["rules_available"] == 2
    # The refusal happened before any model call — nothing was sent to be answered.
    assert stubbed.calls == []


async def test_the_record_shown_carries_a_threshold_that_lives_in_the_condition(stubbed):
    """Generalisation beyond the witness. A rule may state its limit only in its
    compiled condition — the sentence says "within the weekly ceiling" while the
    number sits in the fact-comparison. The record shown to the model must carry
    that number, or an informational answer could never report it. Asserted on
    what is *sent*, so it holds for any rule whose threshold lives in the tree."""

    threshold_rule = make_rule(
        "R-THRESHOLD",
        condition=FactComparisonCondition(
            fact="weekly-hours",
            operator=ConditionOperator.LESS_THAN_OR_EQUAL,
            value=24,
        ),
        machine_executable=True,
    ).model_copy(
        update={
            "title": "Weekly ceiling for part-time staff",
            "required_facts": [RequiredFact(name="weekly-hours", data_type="number", unit="hours")],
            # The sentence names no number — the limit lives only in the condition.
            "formulation": RuleFormulation(
                canonical=CanonicalPolicy(source_text="Part-time staff work within the weekly ceiling.")
            ),
        }
    )

    await ai_case_intent.answer_informational(
        [threshold_rule], scenario="How many hours may a part-timer work?"
    )

    # Exactly one call — the gather — and the payload it carried holds the number
    # and the fact it is compared against, taken from the condition rather than
    # the sentence.
    assert len(stubbed.calls) == 1
    sent = stubbed.calls[0]["messages"][1]["content"]
    assert "24" in sent
    assert "weekly-hours" in sent
    assert "lessThanOrEqual" in sent
    # And the sentence really did not carry the number, so the payload's "24" can
    # only have come from the condition.
    assert "24" not in "Part-time staff work within the weekly ceiling."


async def test_a_gather_that_fails_on_a_known_informational_case_is_its_own_state(stubbed):
    """The case was read as informational and the gather did not complete. That
    is the fourth state, `failed`, and it must reach the reviewer as itself —
    never as `no_rule_bears` (a true answer), and never by quietly dropping to
    the determination path, which would answer a different question. Here the
    classify call succeeds and only the informational call fails."""

    stubbed.classify_reply = {"intent": "informational", "reasoning": "Asks what the policy provides."}
    stubbed.fail_info = True

    out = await ai_case_intent.answer_policy_case(
        [_cap_rule().model_dump(mode="json")],
        scenario="How many hours may a part-timer work?",
    )

    assert out["intent"] == "informational"
    assert out["informational"] is not None
    assert out["informational"]["status"] == "failed"
    # Not dressed as the absence of a bearing rule.
    assert out["informational"]["status"] != "no_rule_bears"


async def test_a_classification_that_fails_is_raised_because_the_intent_is_unknown(stubbed):
    """The other failure. When classification itself does not complete the intent
    is unknown, so there is no honest answer to compose and none is invented: it
    is raised for the endpoint to turn into a 503 the product degrades on, rather
    than guessed into informational or decision."""

    stubbed.fail = True

    with pytest.raises(RuntimeError):
        await ai_case_intent.answer_policy_case(
            [_cap_rule().model_dump(mode="json")],
            scenario="How many hours may a part-timer work?",
        )
