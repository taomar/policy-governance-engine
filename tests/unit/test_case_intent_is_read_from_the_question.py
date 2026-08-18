"""What a case *is* is read by the model — from the question against the facts
the policy's rules test — and never from a list of words, and the answer is
grounded in one lean policy record.

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

WHY THE CLASSIFIER IS ANCHORED, AND WHY THE CALL IS DETERMINISTIC

The cut between the two kinds is whether the question *supplies* a fact the rules
test or *asks after* one, so the classifier is handed those tested quantities
alongside the question — the policy's own facts, in the document's own words, not
its identity. That anchor is data, not a vocabulary, so the no-phrase-list guard
above still holds. And because a reviewer asking twice must get the same kind of
answer, the classify call runs on the fast deployment at ``temperature=0`` — the
one determinism control it honours — which the tests below assert directly.

WHY THE ANSWER IS GROUNDED IN A LEAN RECORD

The gather is one pass over one policy's lean ``grounding_projection_v1``
record — the same projection the JSON tab renders — not one call per rule. The
record is the closed set the answer may draw on. The document's own words ride
in that record's ``spans``, uncut and untranslated, so the quantity a reviewer
asks after reaches the model as the document wrote it. A citation names a rule by
``rule_id`` and carries, resolved server-side from that record's ``spans``, the
rule's own verbatim source sentence — never a name this app authored, which stays
off the wire for the reader's surface to resolve from the id (constraint 8). So
these backend tests assert that the record's own words are what is *sent* to the
model, that the citation carries the document's verbatim sentence back *exactly*
(constraint 4), that no app-authored name leaks with it, and that the four states
a source can be in — quoted, uncited, unresolved, unstored — are told apart
(constraint 5).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation
from policy_platform.contracts.policy import EvidenceReference, RequiredFact
from policy_platform.infrastructure.assistants import ai_case_intent
from policy_platform.infrastructure.projection.policy_case_payload import build_case_payload
from tests.fixtures.factories import make_rule

pytestmark = pytest.mark.anyio


#: A synthetic cap, in the document's own words. Not any real policy's sentence:
#: the behaviour under test must hold for any corpus, so the fixture states a
#: rule no document in this repository contains.
VERBATIM_EN = "Part-time staff are engaged to work no more than twenty-four hours in any week."
#: The same kind of clause in Arabic, to prove a quote survives the projection as
#: characters rather than as \\uXXXX escapes and is never translated on its way
#: to the model.
VERBATIM_AR = "لا يعمل الموظفون بدوام جزئي أكثر من أربع وعشرين ساعة في الأسبوع."

#: A stand-in document version id. The projection needs each rule to point at a
#: source span for its verbatim to be carried; a rule with no evidence would have
#: no words in the record, which is a different fixture than the one under test.
_DOC_VERSION_ID = "11111111-1111-1111-1111-111111111111"


class _Settings:
    ai_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"


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
    decision_reply: dict[str, Any] = {
        "status": "answered",
        "answer": "The supplied facts are outside the policy limit.",
        "verdict": "not compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
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
        is_decision = "asked for a judgement" in system
        reply = (
            type(self).classify_reply
            if is_classify
            else type(self).decision_reply
            if is_decision
            else type(self).info_reply
        )
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
    _StubClient.decision_reply = {
        "status": "answered",
        "answer": "The supplied facts are outside the policy limit.",
        "verdict": "not compliant",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }
    _StubClient.fail = False
    _StubClient.fail_info = False
    return _StubClient


def _evidence(clause_id: str) -> EvidenceReference:
    """One source reference, so the projection carries the rule's verbatim.

    The lean record stores a rule's words in ``spans`` and points a rule at them
    through ``evidence_refs``; a rule's own sentence attaches to its first such
    reference. Without one the document's words never enter the payload, so every
    fixture here carries evidence — the way extraction writes rules in production.
    """

    return EvidenceReference(
        document_version_id=_DOC_VERSION_ID,
        source_hash="h" * 16,
        page=7,
        section="3. Conditions of Work",
        clause_id=clause_id,
        start_offset=3,
        end_offset=99,
    )


def _payload(*rules) -> dict:
    """Project the given rules into one lean ``grounding_projection_v1`` record.

    This is the payload the endpoint builds from a provision and hands to the
    gather. The envelope values are the fixture's own — no corpus id, no policy
    name — so nothing here is tuned to any real document.
    """

    return build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading the document wrote"],
        rules=list(rules),
    )


def _gather_call(stubbed: type[_StubClient]) -> dict[str, Any]:
    """The one call that carried the policy record — the informational gather,
    told apart from the classify call by its system prompt."""

    gathers = [c for c in stubbed.calls if "sort one question" not in c["messages"][0]["content"]]
    assert len(gathers) == 1, "expected exactly one gather call"
    return gathers[0]


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
            "evidence": [_evidence("C-CAP")],
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
            "evidence": [_evidence("C-OTHER")],
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


async def test_the_classifier_is_anchored_to_what_the_rules_test(stubbed):
    """The cut — did the question supply a tested fact or ask after one — needs to
    know what the rules test, so the classifier is handed those quantities with
    the question. It is still not handed rule ids or the heavy record: the anchor
    is the facts the rules are measured against, in the document's own words, not
    the document's identity, so nothing here tunes the sort to one policy."""

    await ai_case_intent.classify_case_intent(
        "How many hours may a part-timer work?",
        tested_quantities=["weekly-hours (number, in hrs per week)", "Part-time regular employees"],
    )

    assert len(stubbed.calls) == 1
    system, user = stubbed.calls[0]["messages"]
    assert "sort one question" in system["content"]
    assert "How many hours" in user["content"]
    # The quantities the rules test reach the classifier: that is the anchor the
    # supplied-vs-asked cut turns on.
    assert "weekly-hours (number, in hrs per week)" in user["content"]
    # But no rule id and none of the heavy record's fields: the classifier is
    # anchored to what the rules test, never tuned to one document's identity.
    for leaked in ("rule_id", "R-CAP", "policy_set_id", "evidence_refs"):
        assert leaked not in user["content"]


async def test_the_classification_call_is_deterministic(stubbed):
    """A reviewer asking the same question twice must get the same kind of answer.
    Stability is the fast deployment's to give, so the classifier calls it at
    temperature=0 — the one determinism control it honours — and spends no
    reasoning budget. The reasoning deployment, which rejects temperature and does
    not honour seed, is never the classifier's."""

    await ai_case_intent.classify_case_intent("How many days of leave may I take?")

    assert len(stubbed.calls) == 1
    kwargs = stubbed.calls[0]["kwargs"]
    assert kwargs["deployment"] == "fast"
    assert kwargs["temperature"] == 0.0
    assert kwargs.get("reasoning_effort") is None


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
    """A rule with an unmet required fact, asked informationally, is answered
    from the sentence it states — and never with a demand for the fact.

    This is the whole repair. Run as a determination the same rule asks the case
    to supply "weekly-hours"; run as an information request the record's own
    sentence — carrying the ceiling — is what the model is shown, and the answer
    cites that rule by id rather than asking the reviewer to fill a blank."""

    stubbed.classify_reply = {"intent": "informational", "reasoning": "Asks what the policy provides."}
    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time staff are capped at twenty-four hours per week.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    out = await ai_case_intent.answer_policy_case(
        _payload(_cap_rule(), _bystander_rule()),
        scenario="How many hours may a part-timer work?",
    )

    assert out["intent"] == "informational"
    info = out["informational"]
    assert info["status"] == "answered"

    # The answer rests on the rule that states the ceiling, cited by id — and the
    # citation now carries that rule's own verbatim sentence, resolved server-side
    # from the record's spans. Only the display name is left for the reader's
    # surface to resolve from the id.
    assert [c["rule_id"] for c in info["citations"]] == ["R-CAP"]
    cap_citation = info["citations"][0]
    assert cap_citation["source"]["state"] == "quoted"
    assert cap_citation["source"]["text"] == VERBATIM_EN
    # The page and section the span recorded ride along, so a reader can find it.
    assert cap_citation["source"]["page"] == 7
    assert cap_citation["source"]["section"] == "3. Conditions of Work"
    # No app-authored name crosses the wire with the citation (constraint 8).
    assert "Weekly hours for part-time staff" not in json.dumps(info, ensure_ascii=False)

    # And the record's own words — the ceiling the reviewer asked after — are what
    # the model was shown, so it could report the answer rather than demand it.
    sent = _gather_call(stubbed)["messages"][1]["content"]
    assert VERBATIM_EN in sent

    # Nowhere is the fact demanded. The required-fact name does not surface in the
    # answer, and none of the determination path's "you must state X" wording does.
    blob = json.dumps(info, ensure_ascii=False).lower()
    assert "weekly-hours" not in blob
    assert "would have to state" not in blob
    assert "missing" not in blob


async def test_a_determination_gets_a_grounded_decision_answer(stubbed):
    """A decision case is answered from the same lean record, with citations.

    The decision branch is not a second ungrounded decider: the model sees only
    the policy payload, cites by rule id, and the backend resolves the citation to
    the document's verbatim sentence exactly as the informational path does."""

    stubbed.classify_reply = {"intent": "decision", "reasoning": "Describes a situation."}

    out = await ai_case_intent.answer_policy_case(
        _payload(_cap_rule()),
        scenario="Someone works thirty hours a week; are they within the cap?",
    )

    assert out["intent"] == "decision"
    assert out["informational"] is None
    decision = out["decision"]
    assert decision["status"] == "answered"
    assert decision["verdict"] == "not compliant"
    assert decision["citations"][0]["rule_id"] == "R-CAP"
    assert decision["citations"][0]["source"]["text"] == VERBATIM_EN
    assert decision["grounding"]["rules_available"] == 1
    assert decision["grounding"]["rules_cited"] == 1
    # The classify and decision calls ran; the informational gatherer did not.
    systems = [call["messages"][0]["content"] for call in stubbed.calls]
    assert any("sort one question" in system for system in systems)
    assert any("asked for a judgement" in system for system in systems)
    assert not any("asked what a governance policy provides" in system for system in systems)


async def test_a_decision_with_a_missing_required_fact_is_its_own_state(stubbed):
    """Bearing rules that need a fact the scenario did not supply are not guessed.

    The response cites the rule that bears on the case and names the missing fact,
    so a compliance reader sees why no verdict was made."""

    stubbed.decision_reply = {
        "status": "missing_required_facts",
        "answer": "I cannot decide this from the policy until the weekly hours are supplied.",
        "verdict": "",
        "cited_rule_ids": ["R-CAP"],
        "missing_required_facts": ["weekly-hours"],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_decision(
        _payload(_cap_rule()),
        scenario="A part-time employee asks whether their schedule is compliant.",
    )

    assert result["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert result["verdict"] == ""
    assert result["missing_required_facts"] == ["weekly-hours"]
    assert result["citations"][0]["rule_id"] == "R-CAP"


async def test_a_decision_with_no_bearing_rule_is_not_a_hedged_verdict(stubbed):
    """No retained rule bears is a non-answer state, not a cautious-sounding
    compliance verdict."""

    stubbed.decision_reply = {
        "status": "no_rule_bears",
        "answer": "",
        "verdict": "",
        "cited_rule_ids": [],
        "missing_required_facts": [],
        "declined": False,
        "note": "No rule in this policy speaks to the situation.",
    }

    result = await ai_case_intent.answer_decision(
        _payload(_bystander_rule()),
        scenario="Was the travel reimbursement compliant?",
    )

    assert result["status"] == ai_case_intent.NO_RULE_BEARS
    assert result["verdict"] == ""
    assert result["answer"] == ""
    assert result["citations"] == []


# --------------------------------------------------------------------------- #
# Four states, kept apart.
# --------------------------------------------------------------------------- #


async def test_a_policy_that_holds_nothing_on_the_subject_says_so(stubbed):
    """Absent: no rule bears. Not a refusal and not a failure."""

    stubbed.info_reply = {"bears": False, "answer": "", "cited_rule_ids": [], "declined": False, "note": ""}

    info = await ai_case_intent.answer_informational(
        _payload(_bystander_rule()), scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "no_rule_bears"
    assert info["citations"] == []


async def test_a_model_that_stands_back_is_not_a_policy_that_holds_nothing(stubbed):
    """Refused: the model declined. Distinct from absent."""

    stubbed.info_reply = {"bears": True, "answer": "", "cited_rule_ids": ["R-CAP"], "declined": True, "note": ""}

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule()), scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "declined"


async def test_rules_bearing_but_no_answer_composed_is_also_a_standing_back(stubbed):
    """Refused by absence of an answer rather than by the flag: rules bear, but
    the model wrote nothing. Still not 'the policy holds nothing'."""

    stubbed.info_reply = {"bears": True, "answer": "", "cited_rule_ids": ["R-CAP"], "declined": False, "note": ""}

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule()), scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "declined"


async def test_a_failed_request_is_raised_not_reported_as_absent(stubbed):
    """Failed: the request never completed. It must not be reducible to any of
    the three content states, so it is raised for the endpoint to turn into its
    own reply rather than returned as 'no rule bears'."""

    stubbed.fail = True

    with pytest.raises(RuntimeError):
        await ai_case_intent.answer_informational(
            _payload(_cap_rule()), scenario="How many hours may a part-timer work?"
        )


# --------------------------------------------------------------------------- #
# The document's words reach the model unchanged.
#
# The reader is shown a rule's verbatim sentence resolved from its id by the
# surface, so these tests pin the backend half of that promise: the words the
# model grounds on are the record's own, carried into the payload uncut, and
# what comes back is a bare id — never a phrase this app authored.
# --------------------------------------------------------------------------- #


async def test_the_records_own_words_are_what_the_model_is_shown(stubbed):
    """The answer is the app's; the words it rests on are the document's. The
    model could return any wording for the answer, but what the citation carries
    back is the record's verbatim sentence — resolved server-side from the payload's
    spans, exactly as stored — and never a name this app authored."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "A paraphrase the model invented.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule(source_text=VERBATIM_EN)), scenario="How many hours may a part-timer work?"
    )

    assert [c["rule_id"] for c in info["citations"]] == ["R-CAP"]
    # What crosses back is the id and the document's own verbatim sentence — nothing
    # more. The keys are exactly these two; no app-authored title rides along.
    citation = info["citations"][0]
    assert set(citation) == {"rule_id", "source"}
    assert citation["source"]["state"] == "quoted"
    assert citation["source"]["text"] == VERBATIM_EN
    assert "Weekly hours for part-time staff" not in json.dumps(info, ensure_ascii=False)
    # The document's own sentence is also what the model was shown.
    sent = _gather_call(stubbed)["messages"][1]["content"]
    assert VERBATIM_EN in sent


async def test_an_arabic_source_reaches_the_model_as_characters_and_untranslated(stubbed):
    """A clause in Arabic reaches the model in Arabic, as characters, exactly —
    the projection does not escape it to \\uXXXX and does not translate it — and
    the citation carries that same Arabic sentence back, exactly (constraint 4)."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time staff have a weekly ceiling.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule(source_text=VERBATIM_AR)), scenario="كم ساعة يعمل الموظف بدوام جزئي؟"
    )

    sent = _gather_call(stubbed)["messages"][1]["content"]
    assert VERBATIM_AR in sent
    assert "\\u" not in sent
    # The citation carries the Arabic sentence back untranslated and unescaped.
    assert info["citations"][0]["source"]["text"] == VERBATIM_AR


# --------------------------------------------------------------------------- #
# The grounding is reported, and is shown refusing something.
#
# A grounding check that is only ever performed and never seen to reject anything
# is the "validator that could not fail" this repository documents. These tests
# watch it refuse a citation to a rule that was never in the payload, and prove
# the refusal is *reported* on the answer rather than only performed in silence.
# --------------------------------------------------------------------------- #


async def test_a_citation_to_a_rule_not_in_the_policy_is_dropped(stubbed):
    """The model may only cite rules in the record it was shown. An id that names
    no rule there is not a citation, and if nothing valid is left the answer is
    not 'answered' — it cannot be grounded."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "An answer citing a rule that is not here.",
        "cited_rule_ids": ["R-GHOST"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule()), scenario="How many hours may a part-timer work?"
    )

    assert info["status"] == "no_rule_bears"
    assert info["citations"] == []


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
        _payload(_cap_rule(), _bystander_rule()), scenario="How many hours may a part-timer work?"
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
        _payload(_cap_rule()), scenario="How many hours may a part-timer work?"
    )

    assert info["status"] != "answered"
    assert info["citations"] == []
    assert info["grounding"]["fabricated_citations"] == ["R-GHOST"]
    assert info["grounding"]["rules_cited"] == 0


async def test_a_policy_too_large_to_ground_is_declined_not_truncated(stubbed):
    """When the whole policy's record will not fit one grounded pass, the gather
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
            _payload(_cap_rule(), _bystander_rule()), scenario="How many hours may a part-timer work?"
        )

    assert info["status"] == "declined"
    assert info["citations"] == []
    assert info["grounding"]["oversize"] is True
    # The whole policy is still counted, and no rule was quietly dropped to fit.
    assert info["grounding"]["rules_available"] == 2
    # The refusal happened before any model call — nothing was sent to be answered.
    assert stubbed.calls == []


async def test_the_record_shown_carries_the_number_the_rule_states_in_its_words(stubbed):
    """Generalisation beyond the witness. The quantity an informational answer
    reports reaches the model through the rule's verbatim source sentence — the
    lean record's grounding surface — because that is where the document names
    its limit. The projection deliberately does not carry a rule's compiled
    condition tree, so a number that lived *only* in that tree, absent from the
    rule's own words, would not reach the model; the honest reading is that the
    number rides in the source the reviewer can check, and this pins that.

    Asserted on what is *sent*, so it holds for any rule whose sentence names its
    own limit rather than for one document's phrasing.
    """

    stated = "Casual staff are engaged to work no more than 16 hours in any week."
    rule = make_rule("R-CASUAL", condition=AllCondition(all=[]), machine_executable=True).model_copy(
        update={
            "title": "Weekly ceiling for casual staff",
            "required_facts": [RequiredFact(name="weekly-hours", data_type="number", unit="hours")],
            "formulation": RuleFormulation(canonical=CanonicalPolicy(source_text=stated)),
            "evidence": [_evidence("C-CASUAL")],
        }
    )

    await ai_case_intent.answer_informational(
        _payload(rule), scenario="How many hours may a casual worker work?"
    )

    # Exactly one call — the gather — and the record it carried holds the number
    # the reviewer asked after, taken from the rule's own sentence.
    assert len(stubbed.calls) == 1
    sent = stubbed.calls[0]["messages"][1]["content"]
    assert stated in sent
    assert "16" in sent


async def test_a_gather_that_fails_on_a_known_informational_case_is_its_own_state(stubbed):
    """The case was read as informational and the gather did not complete. That
    is the fourth state, `failed`, and it must reach the reviewer as itself —
    never as `no_rule_bears` (a true answer), and never by quietly dropping to
    the determination path, which would answer a different question. Here the
    classify call succeeds and only the informational call fails."""

    stubbed.classify_reply = {"intent": "informational", "reasoning": "Asks what the policy provides."}
    stubbed.fail_info = True

    out = await ai_case_intent.answer_policy_case(
        _payload(_cap_rule()),
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
            _payload(_cap_rule()),
            scenario="How many hours may a part-timer work?",
        )


# --------------------------------------------------------------------------- #
# A citation carries the document's verbatim source, resolved from the record's
# spans — and the four states that resolution can land in are told apart.
# --------------------------------------------------------------------------- #


async def test_a_long_source_sentence_is_carried_back_uncut(stubbed):
    """A quotation is never truncated to fit (constraint 4). However long the
    rule's sentence, the citation carries it back exactly, character for
    character, the same as the record stored it."""

    long_source = (
        "Part-time regular employees are employees typically hired to work on an "
        "hourly basis for no more than twenty-four hours in any given week, and "
        "such employees are not entitled to the benefits, allowances, gratuities "
        "or other emoluments that accrue to full-time regular employees, save "
        "where this handbook or the employee's own letter of appointment expressly "
        "provides otherwise in writing and with the prior approval of the Vice "
        "Chancellor or a person to whom that authority has been duly delegated."
    )
    assert len(long_source) > 300  # genuinely longer than a card would want to show

    stubbed.info_reply = {
        "bears": True,
        "answer": "Part-time regular staff are capped at twenty-four hours a week.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule(source_text=long_source)),
        scenario="How many hours may a part-timer work?",
    )

    source = info["citations"][0]["source"]
    assert source["state"] == "quoted"
    # Exactly as stored: no clip, no ellipsis, no re-wrap.
    assert source["text"] == long_source


def test_a_resolved_citation_quotes_the_span_with_its_page_and_section():
    """The happy path of resolution, unit-tested on the resolver itself: a rule
    that points at a span carrying the sentence is quoted from it, and the span's
    page and section ride along so a reader can find it in the document."""

    rule = {"rule_id": "R-1", "evidence_refs": ["s1"]}
    spans = {
        "s1": {"text": VERBATIM_EN, "page": 19, "section": "2. Employee Classification"},
    }

    source = ai_case_intent._citation_source(rule, spans)

    assert source == {
        "state": "quoted",
        "text": VERBATIM_EN,
        "page": 19,
        "section": "2. Employee Classification",
    }


def test_page_and_section_are_omitted_when_the_span_did_not_record_them():
    """Page and section are carried only when the span has them. A span that
    recorded neither yields a quote with neither key, rather than a null the
    reader's surface would have to special-case."""

    rule = {"rule_id": "R-1", "evidence_refs": ["s1"]}
    spans = {"s1": {"text": VERBATIM_EN, "page": None, "section": None}}

    source = ai_case_intent._citation_source(rule, spans)

    assert source == {"state": "quoted", "text": VERBATIM_EN}


def test_the_rules_own_sentence_is_found_past_identity_only_supporting_refs():
    """A rule may point at several spans; only the one carrying the sentence has a
    ``text``. The resolver walks past the supporting references that carry
    identity without words and quotes the span that holds the sentence."""

    rule = {"rule_id": "R-1", "evidence_refs": ["support", "s-words"]}
    spans = {
        # A supporting clause: identity, but the sentence is not on it.
        "support": {"clause_id": "c-1", "page": 4},
        "s-words": {"text": VERBATIM_EN, "page": 7, "section": "3. Conditions of Work"},
    }

    source = ai_case_intent._citation_source(rule, spans)

    assert source["state"] == "quoted"
    assert source["text"] == VERBATIM_EN


def test_a_rule_that_points_at_no_clause_is_uncited_not_an_empty_quote():
    """A rule with no ``evidence_refs`` points at no clause at all. That is its
    own state — ``no_citation`` — never an empty-string quote (constraint 5)."""

    source = ai_case_intent._citation_source({"rule_id": "R-1", "evidence_refs": []}, {})

    assert source == {"state": "no_citation"}
    assert "text" not in source


def test_a_missing_rule_is_uncited_rather_than_erroring():
    """A cited id that resolves to no rule at all (``None`` handed in) is treated
    as pointing at no clause, not an error — the citation still names its id, and
    the source simply says there is nothing to quote."""

    source = ai_case_intent._citation_source(None, {"s1": {"text": VERBATIM_EN}})

    assert source == {"state": "no_citation"}


def test_a_reference_that_resolves_to_nothing_is_unresolved_not_uncited():
    """A rule that *does* point at a clause, but whose reference finds no span
    carrying the sentence, is ``unresolved`` — kept apart from a rule that points
    at no clause at all, because the two are different facts about the record."""

    rule = {"rule_id": "R-1", "evidence_refs": ["ghost"]}

    # The ref names a span that is not in the dictionary at all.
    assert ai_case_intent._citation_source(rule, {}) == {"state": "unresolved"}
    # And a ref whose span carries identity but never a ``text`` key is the same
    # state: the sentence was not found on any referenced span.
    identity_only = {"ghost": {"clause_id": "c-9", "page": 3}}
    assert ai_case_intent._citation_source(rule, identity_only) == {"state": "unresolved"}


def test_a_span_whose_text_was_never_stored_is_not_stored_not_an_empty_quote():
    """A span that resolved but whose ``text`` is empty is the app's "source text
    was not stored with its rules" case — ``not_stored`` — and is never emitted as
    an empty-string quote a reader would read as the document saying nothing."""

    rule = {"rule_id": "R-1", "evidence_refs": ["s1"]}
    spans = {"s1": {"text": "", "page": 5, "section": "1. Preamble"}}

    source = ai_case_intent._citation_source(rule, spans)

    assert source == {"state": "not_stored"}
    assert "text" not in source


async def test_a_rule_whose_text_was_not_stored_reports_not_stored_end_to_end(stubbed):
    """The unstored case, through the whole gather rather than the resolver alone:
    a rule projected with an empty source sentence still cites, but its source
    reports ``not_stored`` — distinct from a rule whose sentence is present."""

    stubbed.info_reply = {
        "bears": True,
        "answer": "The policy speaks to this, though its sentence was not stored.",
        "cited_rule_ids": ["R-CAP"],
        "declined": False,
        "note": "",
    }

    info = await ai_case_intent.answer_informational(
        _payload(_cap_rule(source_text="")), scenario="How many hours may a part-timer work?"
    )

    citation = info["citations"][0]
    assert citation["rule_id"] == "R-CAP"
    assert citation["source"]["state"] == "not_stored"
    # No empty quote is emitted anywhere on the citation.
    assert "text" not in citation["source"]
