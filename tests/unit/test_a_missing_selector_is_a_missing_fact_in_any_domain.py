"""A case blocked on *which* alternative applies is blocked on a fact, not on the policy.

THE DISTINCTION THIS FILE PINS

A determination that produces no verdict is in one of two situations, and they
are not alike:

  * **`missing_required_facts`** — the record sets out explicit alternative
    outcomes, and the scenario has not supplied the fact that chooses between
    them. The reviewer can act: they name the value and get their judgement.
  * **`not_settled_by_rules`** — the record itself lacks or delegates the
    criteria. Even with every fact of the case in hand the rules would not
    decide it. The reviewer cannot act: no value they add changes the reply.

Reporting the first as the second tells someone their question has no answer in
the policy when they were one sentence away from one, and — because only the
blocked state carries missing information out of the gather — it drops the
question that would have unblocked them.

WHY THIS FILE IS DELIBERATELY MULTI-DOMAIN

The defect was found once, in one document, on one rule, about one subject. A
repair that recognised *that* subject would pass the case that produced it and
fail the next one, undetectably, because the next one has not been filed yet. So
none of the behaviour may key on subject matter, on any word, or on any rule id.

The way to hold a claim like that is to make the tests unable to pass a
subject-scoped fix. Every acceptance below runs over five unrelated policies:

  1. a graduated schedule of sanctions selected by which time something happened;
  2. a subscription price selected by the subscriber's tier;
  3. an approval authority selected by the value of a request;
  4. an inspection interval selected by a vessel's class;
  5. a policy written in invented vocabulary that appears in no language, no
     lexicon, and no list anyone could ship — the case that no keyword rule can
     pass by accident.

Each carries its own delegated-discretion control, so the boundary is shown to
cut both ways in every domain rather than collapsing into "always ask for more".

WHY THE REPAIR IS NOT A PROSE READER

The model can still return a reply whose status contradicts its own structured
fields — that is exactly what the live defect was. The correction compares two
returned *fields*: a reply labelled unsettled that lists the facts it waits on
has described a blocked case, whatever it called itself. Nothing here reads an
explanation, and nothing here invents a fact that was not named — the two
"invents nothing" tests pin that from the other side.
"""
from __future__ import annotations

import inspect
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Settings:
    ai_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"


#: The decision prompt's own distinguishing clause, shared by the single-policy
#: and the project gather. Both are served the same reply here, because both are
#: meant to be under one contract and a stub that could only reach one of them
#: would let the two drift apart unnoticed.
_VERDICT_MARKER = "asked for a judgement"


@dataclass(frozen=True)
class _Domain:
    """One policy, unrelated to the others, in the shape the boundary is about.

    ``schedule_text`` is a rule that sets out *explicit alternative outcomes* and
    keys them to an attribute of the case. ``delegated_text`` is a rule from the
    same policy area that hands the judgement to someone's discretion — the
    control that keeps the boundary a boundary.
    """

    key: str
    rule_id: str
    schedule_text: str
    delegated_rule_id: str
    delegated_text: str
    selector_fact: str
    selector_label: str
    why_needed: str
    settled_part: str
    blocked_scenario: str
    supplied_scenario: str
    supplied_answer: str
    supplied_verdict: str
    delegated_scenario: str
    delegated_answer: str


#: Five policies with nothing in common but the shape. None is any real
#: document's text; all are written here.
DOMAINS = (
    _Domain(
        key="sanction-schedule",
        rule_id="R-CONDUCT",
        schedule_text=(
            "Where a member of staff breaches the code of conduct, the panel imposes a written "
            "warning on the first breach, a final written warning on the second breach, suspension "
            "on the third breach, and dismissal on the fourth breach."
        ),
        delegated_rule_id="R-CONDUCT-OTHER",
        delegated_text=(
            "Conduct not described in the code is dealt with as the panel considers appropriate in "
            "the circumstances."
        ),
        selector_fact="breach-number",
        selector_label="Which breach this is",
        why_needed="The schedule imposes a different measure at each breach.",
        settled_part=(
            "Your conduct falls under the code, and the panel's schedule runs from a written "
            "warning through to dismissal. Which of those applies depends on which breach this is."
        ),
        blocked_scenario="I breached the code of conduct. What will happen to me?",
        supplied_scenario="I breached the code of conduct for the second time. What happens to me?",
        supplied_answer="This is the second breach, so a final written warning applies.",
        supplied_verdict="a final written warning",
        delegated_scenario="I did something the code does not describe at all. What happens?",
        delegated_answer=(
            "The record leaves conduct outside the code to the panel's judgement and states no "
            "criteria for it, so no measure follows from the rules."
        ),
    ),
    _Domain(
        key="pricing-tier",
        rule_id="R-RATE",
        schedule_text=(
            "A subscriber's monthly rate is forty units on the bronze tier, thirty units on the "
            "silver tier, twenty-two units on the gold tier, and fifteen units on the platinum tier."
        ),
        delegated_rule_id="R-RATE-BESPOKE",
        delegated_text=(
            "Rates for arrangements outside the published tiers are agreed case by case between the "
            "subscriber and the provider."
        ),
        selector_fact="subscriber-tier",
        selector_label="Which tier the subscription is on",
        why_needed="The monthly rate is set separately for each tier.",
        settled_part=(
            "Your subscription is priced from the published table, which runs from forty units down "
            "to fifteen. Which figure applies depends on the tier you are on."
        ),
        blocked_scenario="I have a subscription. What is my monthly rate?",
        supplied_scenario="I have a gold tier subscription. What is my monthly rate?",
        supplied_answer="The gold tier rate is twenty-two units a month.",
        supplied_verdict="twenty-two units a month",
        delegated_scenario="My arrangement is not on any of the published tiers. What is my rate?",
        delegated_answer=(
            "The record says arrangements outside the published tiers are agreed case by case and "
            "sets no figure for them, so no rate follows from the rules."
        ),
    ),
    _Domain(
        key="approval-level",
        rule_id="R-APPROVAL",
        schedule_text=(
            "A purchase request is approved by the team lead where its value is below five thousand, "
            "by the department head where its value is between five thousand and fifty thousand, and "
            "by the finance committee where its value exceeds fifty thousand."
        ),
        delegated_rule_id="R-APPROVAL-EXCEPTION",
        delegated_text=(
            "A request that the chief executive designates as exceptional is approved by whoever the "
            "board decides is best placed to consider it."
        ),
        selector_fact="request-value",
        selector_label="The value of the request",
        why_needed="The approving authority is set by which value band the request falls in.",
        settled_part=(
            "Your request is approved under the published authority table, whose levels run from the "
            "team lead to the finance committee. Which level applies depends on the request's value."
        ),
        blocked_scenario="I need to raise a purchase request. Who approves it?",
        supplied_scenario="I need to raise a purchase request for twelve thousand. Who approves it?",
        supplied_answer="Twelve thousand falls in the middle band, so the department head approves it.",
        supplied_verdict="the department head approves it",
        delegated_scenario="My request has been designated exceptional. Who approves it?",
        delegated_answer=(
            "The record leaves an exceptional request to whoever the board decides, and states no "
            "criteria for that decision, so no approver follows from the rules."
        ),
    ),
    _Domain(
        key="inspection-interval",
        rule_id="R-INSPECTION",
        schedule_text=(
            "A vessel is inspected every year where it is registered in class A, every three years "
            "where it is registered in class B, and every five years where it is registered in "
            "class C."
        ),
        delegated_rule_id="R-INSPECTION-UNREGISTERED",
        delegated_text=(
            "An unregistered vessel is inspected on whatever schedule the harbour master thinks fit."
        ),
        selector_fact="vessel-class",
        selector_label="The vessel's registered class",
        why_needed="The inspection interval is set separately for each registered class.",
        settled_part=(
            "Your vessel is inspected under the published intervals, which run from every year to "
            "every five years. Which interval applies depends on its registered class."
        ),
        blocked_scenario="I operate a registered vessel. How often is it inspected?",
        supplied_scenario="I operate a vessel registered in class B. How often is it inspected?",
        supplied_answer="A class B vessel is inspected every three years.",
        supplied_verdict="every three years",
        delegated_scenario="My vessel is not registered at all. How often is it inspected?",
        delegated_answer=(
            "The record leaves an unregistered vessel to the harbour master's judgement and states "
            "no interval for it, so no schedule follows from the rules."
        ),
    ),
    _Domain(
        # Every content word here is invented. It belongs to no language and can
        # appear in no list of trigger phrases, so a fix that recognised subjects
        # rather than structure has nothing at all to recognise.
        key="invented-vocabulary",
        rule_id="R-GLOMMAGE",
        schedule_text=(
            "A quandle's glommage is set at seven fremmits where the quandle is zorbic, at four "
            "fremmits where it is plerric, and at one fremmit where it is durnaceous."
        ),
        delegated_rule_id="R-GLOMMAGE-OTHER",
        delegated_text=(
            "A quandle of no recognised habitus takes whatever glommage the vorrender deems suitable."
        ),
        selector_fact="quandle-habitus",
        selector_label="Which habitus the quandle has",
        why_needed="A separate glommage is set for each habitus.",
        settled_part=(
            "Your quandle takes a glommage from the published figures, which run from seven fremmits "
            "down to one. Which figure applies depends on its habitus."
        ),
        blocked_scenario="I hold a quandle. What glommage does it take?",
        supplied_scenario="I hold a plerric quandle. What glommage does it take?",
        supplied_answer="A plerric quandle takes four fremmits.",
        supplied_verdict="four fremmits",
        delegated_scenario="My quandle has no recognised habitus. What glommage does it take?",
        delegated_answer=(
            "The record leaves a quandle of no recognised habitus to the vorrender and states no "
            "figure for it, so no glommage follows from the rules."
        ),
    ),
)

_DOMAIN_IDS = [domain.key for domain in DOMAINS]


class _StubClient:
    """Stands in for the model, serving whatever reply a test sets.

    Every call is kept, so a test can assert what the gather was *told* as well as
    what it returned — which is how the prompt half of this contract is checked as
    a property of the request rather than of a comment.
    """

    calls: list[dict[str, Any]] = []
    verdict_reply: dict[str, Any] = {}

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system = messages[0]["content"]
        type(self).calls.append({"messages": messages, "kwargs": kwargs, "system": system})
        assert _VERDICT_MARKER in system, "these tests exercise the decision gather only"
        return json.dumps(type(self).verdict_reply, ensure_ascii=False)


@pytest.fixture()
def stubbed(monkeypatch: pytest.MonkeyPatch) -> type[_StubClient]:
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubClient)
    _StubClient.calls = []
    _StubClient.verdict_reply = {}
    return _StubClient


def _payload(domain: _Domain, *, delegated: bool = False) -> dict:
    """One lean record whose rule sets out its alternatives in its own sentence.

    ``required_facts`` is empty in every fixture, deliberately. That is the
    production shape the defect was found in — the selector lived in the rule's
    words and never reached the persisted list — and it is what gives the
    "not in `required_facts`" acceptance something to bite on.
    """

    rule_id = domain.delegated_rule_id if delegated else domain.rule_id
    text = domain.delegated_text if delegated else domain.schedule_text
    return {
        "envelope": {"provision_id": f"prov-{domain.key}", "provision_key": domain.key},
        "spans": {"S1": {"text": text, "page": 4, "section": "2. Application"}},
        "facts": {},
        "rules": [
            {
                "rule_id": rule_id,
                "rule_type": "obligation",
                "evaluation_mode": "ai_ready",
                "effect": "apply the published outcome for this case",
                "required_facts": [],
                "evidence_refs": ["S1"],
            }
        ],
    }


def _record(domain: _Domain, *, delegated: bool = False) -> dict:
    """The same policy in the shape the project gather takes."""

    return {
        "policy": {
            "provision_id": f"prov-{domain.key}",
            "provision_key": domain.key,
            "heading_path": ["2. Application"],
        },
        "payload": _payload(domain, delegated=delegated),
    }


def _detail(domain: _Domain, *, rule_ids: list[str] | None = None) -> list[dict]:
    return [
        {
            "fact": domain.selector_fact,
            "label": domain.selector_label,
            "why_needed": domain.why_needed,
            "required_by_rule_ids": rule_ids if rule_ids is not None else [domain.rule_id],
        }
    ]


def _blocked_reply(domain: _Domain, *, status: str, unsettled_reason: str = "") -> dict:
    """A reply that names the selector it is waiting on, under a given status.

    The two statuses this is used with are the point of the file: one is the
    label a well-behaved gather chooses, the other is the label the live defect
    chose while naming the very same fact.
    """

    return {
        "status": status,
        "answer": domain.settled_part,
        "verdict": "",
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [domain.selector_fact],
        "missing_required_facts_detail": _detail(domain),
        "unsettled_reason": unsettled_reason,
        "declined": False,
        "note": "",
    }


# ── the selector is missing: a blocked case, in every domain ─────────


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_missing_selector_among_explicit_outcomes_is_a_missing_fact(
    stubbed, domain: _Domain
) -> None:
    """Acceptance (a), over five unrelated policies.

    The rules cover the situation and set out several outcomes for it. The one
    thing absent is the value that picks between them — a fact of the reviewer's
    own case. So the state is the blocked one, and the caller gets enough
    structure to go and ask for it: a label to put in front of a user, a reason
    it decides anything, and the rules that are waiting on it.
    """

    stubbed.verdict_reply = _blocked_reply(domain, status="missing_required_facts")

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == "", "a blocked case carries no verdict string"
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"] == [
        {
            "fact": domain.selector_fact,
            "label": domain.selector_label,
            "why_needed": domain.why_needed,
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    assert decision["citations"][0]["rule_id"] == domain.rule_id
    assert decision["citations"][0]["source"]["text"] == domain.schedule_text


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_an_unsettled_reply_that_names_the_selector_is_a_blocked_case(
    stubbed, domain: _Domain
) -> None:
    """The live defect's shape, corrected — and corrected identically everywhere.

    This is the reply that shipped: the status says the rules do not settle the
    case, while the reply's own structured field lists the fact that would settle
    it. Both cannot be true. `not_settled_by_rules` means the policy is silent, so
    nothing the reviewer supplies can change it; a reply naming what it waits on
    has described a blocked case under the wrong label.

    The label is corrected from one returned field against another. The prose is
    neither read nor rewritten: it survives whole as the explanation.
    """

    stubbed.verdict_reply = _blocked_reply(
        domain, status="not_settled_by_rules", unsettled_reason="missing_case_fact"
    )

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["label"] == domain.selector_label
    assert decision["answer"] == domain.settled_part, "relabelled, never rewritten"
    assert decision["verdict"] == ""
    assert decision["citations"][0]["rule_id"] == domain.rule_id


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_the_same_correction_holds_on_the_single_policy_path(
    stubbed, domain: _Domain
) -> None:
    """One contract, whichever door the reviewer came in by.

    The single-policy gather and the project gather are the same reading over
    different-sized record sets. A correction reaching only one of them would give
    the same case two different states depending on which path ran — the drift the
    shared post-processing exists to prevent.
    """

    stubbed.verdict_reply = _blocked_reply(
        domain, status="not_settled_by_rules", unsettled_reason="missing_case_fact"
    )

    decision = await ai_case_intent.answer_decision(
        _payload(domain), scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["required_by_rule_ids"] == [domain.rule_id]


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_blocked_case_keeps_what_the_rules_already_settle(
    stubbed, domain: _Domain
) -> None:
    """Half an answer is still an answer, and is not withheld.

    The rules decide that the situation is covered and which outcomes are on the
    table; only the choice between them is blocked. Reporting that as a flat
    non-answer throws away everything the policy does say. So the settled part
    stays in the explanation, while the structured request names *only* the
    selector — one item, not a re-listing of everything the rule mentions.
    """

    stubbed.verdict_reply = _blocked_reply(
        domain, status="not_settled_by_rules", unsettled_reason="missing_case_fact"
    )

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["answer"] == domain.settled_part
    assert len(decision["missing_information"]) == 1, "only the selector is asked for"
    # Neither shape is ever populated without the other.
    assert bool(decision["missing_required_facts"]) is bool(decision["missing_information"])


# ── the selector supplied ────────────────────────────────────────────


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_supplied_selector_is_answered_rather_than_asked_for(
    stubbed, domain: _Domain
) -> None:
    """Acceptance (b), over five unrelated policies.

    The same case with the value stated is blocked on nothing. It reaches a
    verdict, and both missing shapes are empty — a verdict that also listed
    outstanding facts would be telling a reader it decided on incomplete
    information.
    """

    stubbed.verdict_reply = {
        "status": "answered",
        "answer": domain.supplied_answer,
        "verdict": domain.supplied_verdict,
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.supplied_scenario
    )

    assert decision["status"] == ai_case_intent.ANSWERED
    assert decision["verdict"] == domain.supplied_verdict
    assert decision["missing_required_facts"] == []
    assert decision["missing_information"] == []


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_selector_stated_in_the_reviewers_own_words_is_not_asked_for_again(
    stubbed, domain: _Domain
) -> None:
    """Acceptance (e), over five unrelated policies.

    A reviewer who describes the selector in their own phrasing has supplied it;
    the record's term for the same thing is beside the point. A gather that
    answered on that basis must not acquire missing information here — this layer
    adds none of its own, and a "requirement" invented in post-processing would
    read to a caller exactly like one the policy asked for.
    """

    stubbed.verdict_reply = {
        "status": "answered",
        "answer": domain.supplied_answer,
        "verdict": domain.supplied_verdict,
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.supplied_scenario
    )

    assert decision["status"] == ai_case_intent.ANSWERED
    assert decision["missing_required_facts"] == []
    assert decision["missing_information"] == []


# ── the control: the policy itself does not decide ───────────────────


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_judgement_the_policy_delegates_stays_unsettled(
    stubbed, domain: _Domain
) -> None:
    """Acceptance (c), and the reason the boundary is a boundary.

    Each domain's second rule hands the judgement to someone's discretion and
    states no criteria. No value the reviewer could supply changes the reply, so
    the honest state is the policy's own silence and there is nothing to ask them
    for. Without this control the whole contract could be satisfied by treating
    every non-answer as a demand for information — which would be a different
    defect wearing the fix's clothes.
    """

    stubbed.verdict_reply = {
        "status": "not_settled_by_rules",
        "answer": domain.delegated_answer,
        "verdict": "",
        "cited_rule_ids": [domain.delegated_rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "record_does_not_determine",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain, delegated=True)], scenario=domain.delegated_scenario
    )

    assert decision["status"] == ai_case_intent.NOT_SETTLED_BY_RULES
    assert decision["missing_required_facts"] == []
    assert decision["missing_information"] == []
    assert decision["verdict"] == ""
    assert decision["answer"] == domain.delegated_answer
    assert decision["citations"][0]["source"]["text"] == domain.delegated_text


# ── the list is not the only place a needed fact is named ────────────


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_a_selector_no_rule_lists_in_required_facts_is_still_accepted(
    stubbed, domain: _Domain
) -> None:
    """Acceptance (d), over five unrelated policies.

    Every rule here carries an *empty* `required_facts`: the selector exists only
    in the sentence the rule was drawn from. That is the production shape the
    defect was found in, and it is why the test cannot be "is it in
    `required_facts`".

    So nothing filters the named facts against that list. Add such a filter and
    all five of these go back to reporting nothing missing.
    """

    (rule,) = _payload(domain)["rules"]
    assert rule["required_facts"] == [], "the fixture's whole point"

    stubbed.verdict_reply = _blocked_reply(domain, status="missing_required_facts")

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["required_by_rule_ids"] == [domain.rule_id]


# ── the repair invents nothing ───────────────────────────────────────


@pytest.mark.parametrize("domain", DOMAINS[:2], ids=_DOMAIN_IDS[:2])
async def test_an_unsettled_reply_that_names_nothing_is_left_as_it_is(
    stubbed, domain: _Domain
) -> None:
    """The limit of the correction, pinned deliberately.

    Here the reply says a fact of the case would settle it and then names none.
    The blocked state cannot be built without content, and both ways of building
    it anyway are worse than leaving it: composing a fact from the prose would put
    a question in the policy's mouth that no rule asked, and emitting a blocked
    status with an empty list would break the invariant that the two shapes are
    populated together.

    So the state stands. This test exists so a later attempt to "finish the job"
    by guessing has something to fail against.
    """

    stubbed.verdict_reply = {
        "status": "not_settled_by_rules",
        "answer": "The exact outcome cannot be determined from the rules.",
        "verdict": "",
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "missing_case_fact",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.NOT_SETTLED_BY_RULES
    assert decision["missing_required_facts"] == []
    assert decision["missing_information"] == []


@pytest.mark.parametrize("domain", DOMAINS[:2], ids=_DOMAIN_IDS[:2])
async def test_a_fact_named_only_in_the_structured_detail_still_blocks(
    stubbed, domain: _Domain
) -> None:
    """Two structured fields carry the same claim; either being filled is enough.

    A reply that fills only the richer `missing_required_facts_detail` has still
    named what it needs. Reading the flat list alone reported "nothing is missing"
    on a reply whose own structured content said otherwise — and turned the
    blocked state into a refusal, losing the explanation and the citations with
    it.

    This reads one structured field to fill another. It is not a prose reader.
    """

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = []
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["fact"] == domain.selector_fact


@pytest.mark.parametrize("domain", DOMAINS[:2], ids=_DOMAIN_IDS[:2])
async def test_a_corrected_block_still_refuses_a_rule_that_was_never_read(
    stubbed, domain: _Domain
) -> None:
    """The fabrication guard is not skipped on the way through the correction.

    A relabelled reply arrives at the same missing-information block as any other,
    so a rule id naming nothing in the closed set is still refused there. A
    fabrication wearing a different field name is still a fabrication, and a
    caller chasing it would be chasing a rule nobody read.
    """

    reply = _blocked_reply(domain, status="not_settled_by_rules", unsettled_reason="missing_case_fact")
    reply["cited_rule_ids"] = [domain.rule_id, "R-INVENTED"]
    reply["missing_required_facts_detail"] = _detail(
        domain, rule_ids=[domain.rule_id, "R-INVENTED"]
    )
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["missing_information"][0]["required_by_rule_ids"] == [domain.rule_id]
    assert [c["rule_id"] for c in decision["citations"]] == [domain.rule_id]
    assert decision["grounding"]["fabricated_citations"] == ["R-INVENTED"]


@pytest.mark.parametrize("domain", DOMAINS[:2], ids=_DOMAIN_IDS[:2])
async def test_a_verdictless_answer_that_names_the_fact_it_lacks_is_a_blocked_case(
    stubbed, domain: _Domain
) -> None:
    """The other route into the same contradiction, closed at the same test.

    A reply claiming `answered` while naming no verdict already becomes a
    non-answer, because a verdict string is non-empty exactly when one was
    reached. *Which* non-answer it becomes has to follow the same test as
    everything else here: this one listed the fact it waits on, so it is blocked
    on that fact, and calling it `not_settled_by_rules` would report the policy as
    silent while the reply itself says a value would settle it.
    """

    stubbed.verdict_reply = _blocked_reply(domain, status="answered")

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == ""
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["label"] == domain.selector_label


@pytest.mark.parametrize("domain", DOMAINS[:2], ids=_DOMAIN_IDS[:2])
async def test_a_verdictless_answer_that_names_nothing_is_still_merely_unsettled(
    stubbed, domain: _Domain
) -> None:
    """And the same route with nothing named lands where it always did.

    The correction above must not turn every verdictless reply into a demand for
    information. With no fact named there is nothing to ask for, so the state
    stays the one that says the rules did not produce the judgement.
    """

    stubbed.verdict_reply = {
        "status": "answered",
        "answer": "The rules speak to this area but not to the arrangement described.",
        "verdict": "",
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.NOT_SETTLED_BY_RULES
    assert decision["missing_required_facts"] == []
    assert decision["missing_information"] == []


# ── DEF-1: `answered` means finished, not "finished except for one value" ──


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_an_answered_reply_that_names_a_missing_fact_is_a_blocked_case(
    stubbed, domain: _Domain
) -> None:
    """DEF-1, over five unrelated policies.

    The same scenario over byte-identical retrieval came back `answered` once and
    `missing_required_facts` once. The `answered` run was the unsafe one: its own
    determination said the outcome depended on a value nobody had supplied, and
    `missing_information` was empty — so nothing on screen said a question was
    outstanding, and a reader had a verdict that was really a conditional.

    `answered` now means the determination is finished and does not hang on any
    unstated fact of the case. A reply that names such a fact has not finished,
    whichever label it chose, and the structured list is what says so.
    """

    stubbed.verdict_reply = _blocked_reply(domain, status="answered")
    stubbed.verdict_reply["verdict"] = domain.supplied_verdict

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == "", "a conditional determination carries no verdict"
    assert decision["missing_required_facts"] == [domain.selector_fact]
    assert decision["missing_information"][0]["label"] == domain.selector_label
    assert decision["answer"] == domain.settled_part, "relabelled, never rewritten"


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_an_answered_reply_naming_the_fact_only_in_the_detail_is_still_blocked(
    stubbed, domain: _Domain
) -> None:
    """DEF-1 reached through the other structured field.

    A reply can leave the flat list empty and still name what it needs in the
    richer one — that is how the measured `answered` run behaved. Preferring the
    block has to see both fields, or the unsafe reading survives simply by
    filling in the less obvious one.
    """

    reply = _blocked_reply(domain, status="answered")
    reply["verdict"] = domain.supplied_verdict
    reply["missing_required_facts"] = []
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == ""
    assert decision["missing_required_facts"] == [domain.selector_fact]


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_the_preference_does_not_swallow_a_determination_that_is_finished(
    stubbed, domain: _Domain
) -> None:
    """The counterweight, without which "prefer the block" is just "never answer".

    A reply that names nothing outstanding is left exactly as it is: answered,
    with its verdict, and both missing shapes empty. The preference is triggered
    by content in the structured list, never by the status alone.
    """

    stubbed.verdict_reply = {
        "status": "answered",
        "answer": domain.supplied_answer,
        "verdict": domain.supplied_verdict,
        "cited_rule_ids": [domain.rule_id],
        "missing_required_facts": [],
        "missing_required_facts_detail": [],
        "unsettled_reason": "",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.supplied_scenario
    )

    assert decision["status"] == ai_case_intent.ANSWERED
    assert decision["verdict"] == domain.supplied_verdict
    assert decision["missing_information"] == []


def test_the_prompts_define_answered_as_complete_and_unconditional() -> None:
    """Post-processing can only catch a reply that *named* the value it hangs on.

    A reply that says "this depends on which one applies" in its prose and names
    nothing structured is invisible to any check that does not read prose — and
    reading prose is exactly what this must not do. So the prompt is the safeguard
    for that case: it defines `answered` as finished and unconditional, forbids
    answering in the alternative on an unstated value, forbids `answered`
    alongside any named missing fact, and asks the model to re-read its own answer
    against the status it chose before returning.
    """

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert "does not hang on any value about that case they did not give" in prompt
        assert "has to answer in the alternative" in prompt
        assert "Never return `answered` while naming anything in `missing_required_facts`" in prompt
        assert "read back what you have written and check it against the status you chose" in prompt
        assert "whether you were about to return `answered` or `not_settled_by_rules`" in prompt


# ── DEF-4: `fact` is a key a caller can hold; `label` is the prose ───


@pytest.mark.parametrize("domain", DOMAINS, ids=_DOMAIN_IDS)
async def test_the_fact_is_a_stable_key_and_the_label_carries_the_wording(
    stubbed, domain: _Domain
) -> None:
    """DEF-4, over five unrelated policies.

    An integration keys its follow-up form on `fact`: it stores state against it,
    matches the user's reply back to it, and compares one run with the next. Free
    text cannot do that job — the same question came back under a different
    spelling each time. So `fact` is an identifier and `label` is the sentence a
    person reads, and the two never swap roles.
    """

    stubbed.verdict_reply = _blocked_reply(domain, status="missing_required_facts")

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    (missing,) = decision["missing_information"]
    assert missing["fact"] == domain.selector_fact
    assert missing["label"] == domain.selector_label
    # A key, by construction: no spaces, no capitals, nothing but its own words.
    assert missing["fact"] == missing["fact"].casefold()
    assert " " not in missing["fact"]
    # And the flat list agrees with it, so a caller reading either sees one name.
    assert decision["missing_required_facts"] == [missing["fact"]]


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Which tier?", "which-tier"),
        ("which tier", "which-tier"),
        ("Which  tier  this  is", "which-tier-this-is"),
        ("  Which tier this is.  ", "which-tier-this-is"),
        ("Which tier — this is", "which-tier-this-is"),
        ("subscriber_tier", "subscriber-tier"),
        ("subscriber-tier", "subscriber-tier"),
        ("Value (in units)", "value-in-units"),
    ],
)
async def test_the_same_fact_written_several_ways_yields_one_key(
    stubbed, written: str, expected: str
) -> None:
    """The defect DEF-4 names: one question, a different handle every run.

    The gather writes free text, and free text drifts between runs of the same
    case — punctuation, capitals, a trailing full stop, a question mark. Each
    variation was a new key, so a caller storing state against it asked the same
    question again. The key is therefore derived, by one rule with no words in
    it: fold the case, and collapse everything that is not alphanumeric into a
    single hyphen.
    """

    domain = DOMAINS[1]
    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = [written]
    reply["missing_required_facts_detail"] = [
        {
            "fact": written,
            "label": written,
            "why_needed": domain.why_needed,
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["missing_information"][0]["fact"] == expected
    assert decision["missing_required_facts"] == [expected]
    # The wording the gather chose is not destroyed — it is where a person reads
    # it, trimmed of surrounding space as every free-text field here is.
    assert decision["missing_information"][0]["label"] == written.strip()


async def test_a_key_in_another_script_keeps_its_own_letters(stubbed) -> None:
    """The normalisation must be true of the corpus, which is bilingual.

    A rule written for ASCII would reduce an Arabic fact to hyphens, or to
    nothing, and the caller would key every Arabic question on the same empty
    string. The rule is written character by character against Unicode categories
    instead of with a pattern, so letters in any script survive and only the
    separators between them are normalised.
    """

    domain = DOMAINS[1]
    arabic = "عدد الساعات"
    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = [arabic]
    reply["missing_required_facts_detail"] = [
        {
            "fact": arabic,
            "label": "عدد الساعات في الأسبوع",
            "why_needed": domain.why_needed,
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["missing_information"][0]["fact"] == "عدد-الساعات"
    assert decision["missing_information"][0]["label"] == "عدد الساعات في الأسبوع"


@pytest.mark.parametrize("written", ["Weekly Hours", "weekly hours", "weekly-hours", "WEEKLY_HOURS"])
async def test_a_fact_the_rule_already_names_keeps_the_records_own_spelling(
    stubbed, written: str
) -> None:
    """A derived key is a fallback, never a replacement for the record's name.

    Where a rule declares the fact, that declared name is the identifier the rest
    of the platform already uses. Coining a second one here would fork the
    vocabulary: the same fact would be called one thing in the rule and another in
    the question asked about it. So the record wins wherever it has said anything,
    and the derived key is only what lets the gather's spelling find it.
    """

    domain = DOMAINS[1]
    record = _record(domain)
    record["payload"]["rules"][0]["required_facts"] = [
        {"name": "weekly-hours", "data_type": "number", "unit": "hours"}
    ]

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = [written]
    reply["missing_required_facts_detail"] = [
        {
            "fact": written,
            "label": "Hours worked in the week",
            "why_needed": domain.why_needed,
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [record], scenario=domain.blocked_scenario
    )

    assert decision["missing_information"][0]["fact"] == "weekly-hours"
    assert decision["missing_required_facts"] == ["weekly-hours"]
    assert decision["missing_information"][0]["label"] == "Hours worked in the week"


async def test_two_spellings_of_one_fact_do_not_become_two_questions(stubbed) -> None:
    """Once the key is derived, duplicates are duplicates and collapse.

    A gather that named the same thing twice in two spellings used to produce two
    entries, and a caller built a form that asked one question twice. They reduce
    to one key, so they reduce to one question.
    """

    domain = DOMAINS[1]
    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = ["Which tier?", "which tier"]
    stubbed.verdict_reply = reply
    reply["missing_required_facts_detail"] = []

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["missing_required_facts"] == ["which-tier"]


def test_the_prompts_ask_for_a_key_and_keep_the_prose_in_the_label() -> None:
    """Normalisation is the floor, not the whole answer.

    Deriving the key downstream makes it stable whatever arrives; asking for it
    upstream makes it *meaningful* — the record's own name for the fact, rather
    than a key derived from whatever sentence the gather happened to write. Both
    are wanted, so both prompts say which field is an identifier and which is the
    words a person reads.
    """

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert "Write each one as a key, not as prose" in prompt
        assert "lower case" in prompt and "single hyphens" in prompt
        assert "belong in \"label\", not here" in prompt
        assert "this is the prose, and it is the only field here that is" in prompt


# ── the two emitted fields are one set, not two readings ────────────


def _both_fields_agree(decision: dict) -> None:
    """The invariant every reconciliation test below asserts.

    A caller hashing the flat list and a caller rendering the block must be
    looking at the same set of questions. Same keys, same order, same count —
    otherwise the reply says one thing to a receipt and another to a screen.
    """

    assert [item["fact"] for item in decision["missing_information"]] == decision[
        "missing_required_facts"
    ]
    assert len(decision["missing_information"]) == len(decision["missing_required_facts"])


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_a_flat_list_and_a_detail_that_disagree_are_reconciled_into_one_set(
    stubbed, domain: _Domain
) -> None:
    """The defect: two fields, two readers, two different answers.

    The flat list was read by one function that preferred it, and the detail by
    another that preferred the detail. When the gather filled both and they did
    not match, each reader got its way in a different output field — the list a
    caller hashes named one fact and the block their UI renders named another,
    with nothing to say they had diverged. They could differ in length too, so a
    "one entry per missing fact" reader simply had no entry for one of them.

    Both fields now come off one reconciled set, so neither can win: every fact
    either field named is present exactly once, and the two outputs are the same
    set in the same order by construction.
    """

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = ["first-selector"]
    reply["missing_required_facts_detail"] = [
        {
            "fact": "second-selector",
            "label": "The second thing",
            "why_needed": "The other half of the choice turns on it.",
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["first-selector", "second-selector"]
    # Neither is dropped, and the one the detail described keeps what it described.
    flat_only, detailed = decision["missing_information"]
    assert flat_only == {
        "fact": "first-selector",
        "label": "first-selector",
        "why_needed": "",
        "required_by_rule_ids": [],
    }
    assert detailed == {
        "fact": "second-selector",
        "label": "The second thing",
        "why_needed": "The other half of the choice turns on it.",
        "required_by_rule_ids": [domain.rule_id],
    }


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_one_fact_spelled_two_ways_across_the_two_fields_is_one_question(
    stubbed, domain: _Domain
) -> None:
    """The same fact, written differently in each field, is still one fact.

    This is where the disagreement is most likely and least visible: the gather
    means one thing and writes it as a key in one field and as a question in the
    other. Reconciling on the canonical key rather than on the text means the two
    meet, so the caller gets one entry — carrying the detail's wording, because
    that is the field where wording belongs.
    """

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = ["Which tier?"]
    reply["missing_required_facts_detail"] = [
        {
            "fact": "which tier",
            "label": "Which tier this is",
            "why_needed": "The outcome is set separately for each.",
            "required_by_rule_ids": [domain.rule_id],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["which-tier"]
    assert decision["missing_information"][0]["label"] == "Which tier this is"
    assert decision["missing_information"][0]["why_needed"] == "The outcome is set separately for each."


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_a_reply_that_fills_only_the_flat_list_still_pairs_one_to_one(
    stubbed, domain: _Domain
) -> None:
    """Flat only: every key gets an entry, and nothing is composed for it.

    The parts the gather did not supply are left empty — a reason invented in this
    layer would read to a caller exactly like one the policy gave. The label falls
    back to the gather's own wording, which is the only human-readable thing there
    is and is not an invention.
    """

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = ["first-selector", "second-selector"]
    reply["missing_required_facts_detail"] = []
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_information"] == [
        {"fact": "first-selector", "label": "first-selector", "why_needed": "", "required_by_rule_ids": []},
        {"fact": "second-selector", "label": "second-selector", "why_needed": "", "required_by_rule_ids": []},
    ]


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_a_reply_that_fills_only_the_detail_still_pairs_one_to_one(
    stubbed, domain: _Domain
) -> None:
    """Detail only: the flat list is derived from it, key for key.

    A caller reading the flat field must not see an empty list on a reply whose
    richer field named two questions.
    """

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = []
    reply["missing_required_facts_detail"] = [
        {"fact": "first-selector", "label": "The first", "why_needed": "a", "required_by_rule_ids": []},
        {"fact": "second-selector", "label": "The second", "why_needed": "b", "required_by_rule_ids": []},
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["first-selector", "second-selector"]
    assert [item["label"] for item in decision["missing_information"]] == ["The first", "The second"]


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_two_detail_entries_for_one_key_merge_rather_than_double_ask(
    stubbed, domain: _Domain
) -> None:
    """Duplicates inside the detail collapse, and their rule ids are merged.

    Two spellings of one question are one question. The first wording is kept
    because it is the gather's own ordering, and the rule ids are unioned because
    both were named and neither is wrong.
    """

    record = _record(domain)
    record["payload"]["rules"].append(
        {
            "rule_id": "R-SECOND",
            "rule_type": "obligation",
            "evaluation_mode": "ai_ready",
            "effect": "apply the published outcome",
            "required_facts": [],
            "evidence_refs": ["S1"],
        }
    )
    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["cited_rule_ids"] = [domain.rule_id, "R-SECOND"]
    reply["missing_required_facts"] = []
    reply["missing_required_facts_detail"] = [
        {
            "fact": "Which tier?",
            "label": "Which tier this is",
            "why_needed": "The first rule turns on it.",
            "required_by_rule_ids": [domain.rule_id],
        },
        {
            "fact": "which  tier",
            "label": "Tier again",
            "why_needed": "The second rule turns on it too.",
            "required_by_rule_ids": ["R-SECOND"],
        },
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [record], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["which-tier"]
    (missing,) = decision["missing_information"]
    assert missing["label"] == "Which tier this is"
    assert missing["why_needed"] == "The first rule turns on it."
    assert missing["required_by_rule_ids"] == [domain.rule_id, "R-SECOND"]


@pytest.mark.parametrize("domain", DOMAINS[:3], ids=_DOMAIN_IDS[:3])
async def test_reconciling_still_refuses_a_rule_id_that_was_never_read(
    stubbed, domain: _Domain
) -> None:
    """The fabrication guard survives the rewrite, on the merged path too."""

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = []
    reply["missing_required_facts_detail"] = [
        {
            "fact": "first-selector",
            "label": "The first",
            "why_needed": "why",
            "required_by_rule_ids": ["R-INVENTED", domain.rule_id, "R-ALSO-INVENTED"],
        }
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert decision["missing_information"][0]["required_by_rule_ids"] == [domain.rule_id]


async def test_the_two_fields_agree_when_they_name_one_fact_in_two_unicode_forms(
    stubbed,
) -> None:
    """The reconciliation is on canonical keys, so the two fields meet in any script.

    The flat field carries the decomposed spelling and the detail the composed
    one — the same word to any reader, two different sequences of code points to a
    comparison that does not normalise. Without normalisation this is the
    disagreement case again, produced by nothing more than which keyboard or
    library wrote the reply.
    """

    domain = DOMAINS[1]
    reply = _blocked_reply(domain, status="missing_required_facts")
    # Arabic carrying tashkeel in one field and bare in the other; and a Latin
    # word decomposed in one and composed in the other.
    reply["missing_required_facts"] = ["\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a", "dure\u0301e"]
    reply["missing_required_facts_detail"] = [
        {
            "fact": "\u0627\u0644\u0633\u0627\u0639\u0627\u062a",
            "label": "عدد الساعات",
            "why_needed": "why",
            "required_by_rule_ids": [domain.rule_id],
        },
        {
            "fact": "dur\u00e9e",
            "label": "La durée",
            "why_needed": "pourquoi",
            "required_by_rule_ids": [domain.rule_id],
        },
    ]
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["الساعات", "durée"]
    assert [item["label"] for item in decision["missing_information"]] == ["عدد الساعات", "La durée"]


# ── the key is Unicode-stable ────────────────────────────────────────


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        # Latin, composed against decomposed: one word to a reader, two code point
        # sequences to a comparison that does not normalise.
        ("caf\u00e9", "cafe\u0301", "café"),
        ("dur\u00e9e", "dure\u0301e", "durée"),
        # Arabic with and without tashkeel. Marks are dropped rather than turned
        # into separators, which is what would have split the word into fragments.
        (
            "\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a",
            "\u0627\u0644\u0633\u0627\u0639\u0627\u062a",
            "الساعات",
        ),
        (
            "\u0645\u064f\u062f\u0651\u0629 \u0627\u0644\u0639\u064e\u0645\u064e\u0644",
            "\u0645\u062f\u0629 \u0627\u0644\u0639\u0645\u0644",
            "مدة-العمل",
        ),
        # Compatibility forms: fullwidth letters and a typographic ligature are
        # the same word set in different type.
        ("\uff37\uff45\uff45\uff4b\uff4c\uff59\u3000\uff28\uff4f\uff55\uff52\uff53", "Weekly Hours", "weekly-hours"),
        ("\ufb01le number", "file number", "file-number"),
    ],
)
def test_two_unicode_spellings_of_one_name_produce_one_key(
    left: str, right: str, expected: str
) -> None:
    """Exact keys, asserted rather than merely compared.

    Comparing the two sides only proves they agree; it would still pass if both
    collapsed to the empty string, or to a row of hyphens where the letters used
    to be. So the key itself is named, and it keeps its own letters: a rule that
    reduced these to ASCII would silently make every Arabic fact key the same.
    """

    assert ai_case_intent._fact_key(left) == expected
    assert ai_case_intent._fact_key(right) == expected


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        # A mark that is not attached to a letter still must not become a
        # separator that splits the name.
        ("\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a", "الساعات"),
        # Case folding that itself decomposes: the Turkish dotted capital folds to
        # a letter plus a combining dot, which is dropped rather than hyphenated.
        ("\u0130stanbul", "istanbul"),
        # A name that is nothing but marks and punctuation has no key to give.
        ("\u064e\u064f\u0650", ""),
        # Non-ASCII letters are preserved, never transliterated or stripped.
        ("Grün Straße", "grün-strasse"),
        ("Ωμέγα", "ωμέγα"),
    ],
)
def test_the_key_keeps_letters_and_drops_only_marks_and_separators(
    written: str, expected: str
) -> None:
    """Three rules, each visible in one of these rows.

    Normalise, drop combining marks, and join the rest on single hyphens. The last
    two rows are the ones that matter most for a bilingual corpus: a key rule that
    reached for ASCII would turn every non-Latin name into the same empty string,
    and a caller keying state on it would collide every question with every other.
    """

    assert ai_case_intent._fact_key(written) == expected


async def test_a_fact_the_rule_names_is_matched_across_unicode_forms(stubbed) -> None:
    """The record's own spelling wins, and is found however the gather wrote it.

    The rule declares the name; the gather writes the same name with tashkeel.
    Matching on the canonical key is what lets those meet, so the identifier a
    caller sees is the record's, not a second one coined from the gather's
    spelling.
    """

    domain = DOMAINS[1]
    record = _record(domain)
    record["payload"]["rules"][0]["required_facts"] = [
        {"name": "\u0627\u0644\u0633\u0627\u0639\u0627\u062a", "data_type": "number"}
    ]

    reply = _blocked_reply(domain, status="missing_required_facts")
    reply["missing_required_facts"] = ["\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a"]
    reply["missing_required_facts_detail"] = []
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [record], scenario=domain.blocked_scenario
    )

    _both_fields_agree(decision)
    assert decision["missing_required_facts"] == ["الساعات"]


# ── the shape a client reads did not change ──────────────────────────


@pytest.mark.parametrize("status", ["missing_required_facts", "not_settled_by_rules", "answered"])
async def test_the_reply_a_client_reads_carries_no_new_field(stubbed, status: str) -> None:
    """Compatibility, checked rather than assumed.

    `unsettled_reason` constrains what the *model* returns; it is not a field
    added to the reply. Clients already read this shape, and a key appearing in it
    would be a contract change nobody asked for — one that would have to be
    carried through the envelope and the receipt as well.
    """

    domain = DOMAINS[0]
    reply = _blocked_reply(
        domain,
        status=status,
        unsettled_reason="missing_case_fact" if status == "not_settled_by_rules" else "",
    )
    if status == "answered":
        reply["verdict"] = domain.supplied_verdict
        reply["missing_required_facts"] = []
        reply["missing_required_facts_detail"] = []
    stubbed.verdict_reply = reply

    decision = await ai_case_intent.answer_decision_over_policies(
        [_record(domain)], scenario=domain.blocked_scenario
    )

    assert set(decision) == {
        "status",
        "verdict",
        "answer",
        "missing_required_facts",
        "missing_information",
        "citations",
        "note",
        "grounding",
    }


# ── the contract is stated once, semantically, for any subject ───────


def test_both_decision_prompts_state_the_same_test() -> None:
    """One wording, reached by both gathers.

    The single-policy and project decisions are the same contract over
    different-sized record sets. Two copies of the paragraph would drift, and the
    drift would surface as the same case getting two states depending on which
    path a reviewer used.
    """

    boundary = ai_case_intent._SETTLEMENT_BOUNDARY
    assert boundary in ai_case_intent._DECISION_SYSTEM_PROMPT
    assert boundary in ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT
    assert "would the rules then settle the judgement asked for?" in boundary


def test_the_boundary_is_stated_as_a_test_and_not_as_a_vocabulary() -> None:
    """The instruction must be semantic, and must say so.

    A model handed a list of selector words will match words. The paragraph gives
    a few examples because an abstraction with none is hard to apply, and then
    says in as many words that they are a shape rather than a vocabulary, that the
    question is the test, and that it holds whatever the subject is. Those
    sentences are load-bearing: without them the examples become the rule.
    """

    boundary = ai_case_intent._SETTLEMENT_BOUNDARY
    assert "a shape to recognise, not a vocabulary to match" in boundary
    assert "Ask the question, not the words" in boundary
    assert "whatever the subject is" in boundary
    # The examples it does give are drawn from unrelated subjects, so no single
    # policy area can be read as the one this is about.
    for unrelated in ("price", "approval", "inspection interval", "contribution rate"):
        assert unrelated in boundary


def test_the_production_contract_names_no_part_of_the_case_that_found_it() -> None:
    """The hardcoding audit, kept as a test so it cannot quietly regress.

    The defect was found in one document, about one subject, on one rule, from one
    measured scenario. A contract that recognised any of those would pass the case
    that produced it and fail the next one — undetectably, because the next one has
    not been filed yet.

    So this greps the production surface directly: the two decision system prompts,
    the shared boundary, and the source of every post-processing function that
    touches a decision. Scanning source is safe *here* precisely because none of
    those functions carries a prohibition list of its own — the list lives in this
    test, so the scan cannot catch the prohibition and report it as the crime.

    "AIS" and the id shapes are matched on word boundaries: a plain substring
    search for "AIS" matches "raised", which would make this test pass or fail for
    reasons that have nothing to do with what it is about.
    """

    borrowed = (
        # the subject the case came from, and its near neighbours
        "absence",
        "attendance",
        "penalty",
        "occurrence",
        "sanction",
        "disciplinary",
        "employee",
        "employer",
        "salary",
        "deduction",
        "excuse",
        "hr ",
        # unrelated subjects a keyword fix might also reach for
        "laptop",
        "vacation",
        "sick leave",
        # the measured scenario's own wording
        "didnt attend",
        "didn't attend",
        "no execuse",
        "no excuse",
        "what will happen to me",
        "3 days",
        "three days",
        "contract year",
    )
    identifiers = (
        ("the acronym AIS", re.compile(r"\bAIS\b")),
        ("a concrete rule id", re.compile(r"\bAI-[0-9a-f]{6,}\b", re.I)),
        (
            "a concrete decision or provision uuid",
            re.compile(
                r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
            ),
        ),
        ("a fixture-style rule id", re.compile(r"\bR-[A-Z][A-Z-]{2,}\b")),
    )

    post_processing = "\n".join(
        inspect.getsource(fn)
        for fn in (
            ai_case_intent._decision_from_parsed,
            ai_case_intent._reconciled_missing_facts,
            ai_case_intent._unsettled_reason,
            ai_case_intent._checked_citation_ids,
            ai_case_intent._fact_key,
            ai_case_intent._rule_fact_names,
            ai_case_intent._fact_identity,
        )
    )
    surfaces = {
        "_SETTLEMENT_BOUNDARY": ai_case_intent._SETTLEMENT_BOUNDARY,
        "_DECISION_SYSTEM_PROMPT": ai_case_intent._DECISION_SYSTEM_PROMPT,
        "_DECISION_MULTI_SYSTEM_PROMPT": ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
        "decision post-processing": post_processing,
    }

    for name, text in surfaces.items():
        lowered = text.lower()
        for word in borrowed:
            assert word not in lowered, f"{name} borrowed {word!r} from the case that found it"
        for label, pattern in identifiers:
            assert not pattern.search(text), f"{name} names {label}"


def test_the_decision_path_has_no_keyword_branch_and_reads_no_prose() -> None:
    """The correction is field-against-field, and there is nothing else it could be.

    Two ways of "fixing" this would have looked like a fix and been a trap: match
    the wording of the rule to spot a schedule, or read the model's explanation for
    a phrase like "cannot be determined". Both key on language, so both fail on the
    next document and on the other half of a bilingual corpus.

    Neither is present. The module imports no regular-expression machinery, the
    post-processing never inspects the generated answer beyond asking whether it is
    empty, and it never looks at a rule's own text to decide a status.
    """

    module_source = inspect.getsource(ai_case_intent)
    post_processing = "\n".join(
        inspect.getsource(fn)
        for fn in (
            ai_case_intent._decision_from_parsed,
            ai_case_intent._reconciled_missing_facts,
            ai_case_intent._unsettled_reason,
        )
    )

    assert "import re" not in module_source, "no regular expressions in the decision module"
    assert not re.search(r"\bre\.(search|match|findall|sub|compile)\b", module_source)
    # `answer` is read for emptiness and passed through; never searched, split or
    # lower-cased, which is what reading prose would look like.
    assert not re.search(r"answer\.(lower|find|split|startswith|endswith)|in answer", post_processing)
    assert "source_text" not in post_processing, "a status never turns on a rule's own words"

    # The fact key is derived from characters, not from a vocabulary. The only
    # string literals in its body are the hyphen it joins with, the empty string it
    # joins on, and two Unicode identifiers — the normalisation form and the
    # general category of a combining mark. Anything else would be a word, and a
    # word here would be a subject leaking into an identifier.
    key_body = inspect.getsource(ai_case_intent._fact_key).split('"""')[-1]
    literals = re.findall(r"\"([^\"]*)\"|'([^']*)'", key_body)
    assert {a or b for a, b in literals} <= {"", "-", "NFKC", "Mn"}, (
        f"the key derivation carries words: {literals}"
    )


# ── the measured case, as a regression and never as the proof ────────


def _measured_case_record() -> dict:
    """The reported case's *shape*, written here rather than copied from anywhere.

    This reproduces the live defect: a rule that fixes a category of situation and
    then sets out four alternative measures for it, selected by which time in a
    period it is, with the scenario naming the situation and not the time. The
    sentence is this file's own wording — no document's text is reproduced — and
    the rule id is a fixture's, not the one that was measured.

    It stands here as a *regression*: proof that the case that was reported now
    comes back correctly. It is not the proof of the contract. That is the five
    unrelated policies above, which is the order these two things have to be in —
    a fix that passed only this fixture would be the subject-scoped fix this whole
    file exists to make impossible.
    """

    text = (
        "Where a participant is away without permission and without an accepted reason for two to "
        "six days within one period, the first time attracts a warning, the second a reduction, the "
        "third a suspension and the fourth a termination, and the days away are deducted in every "
        "case."
    )
    return {
        "policy": {
            "provision_id": "prov-measured",
            "provision_key": "measured",
            "heading_path": ["3. Measures"],
        },
        "payload": {
            "envelope": {"provision_id": "prov-measured", "provision_key": "measured"},
            "spans": {"S1": {"text": text, "page": 9, "section": "3. Measures"}},
            "facts": {},
            "rules": [
                {
                    "rule_id": "R-MEASURED",
                    "rule_type": "obligation",
                    "evaluation_mode": "ai_ready",
                    "effect": "apply the measure set for the time reached",
                    # Empty, exactly as the measured rule's persisted list was.
                    "required_facts": [],
                    "evidence_refs": ["S1"],
                }
            ],
        },
    }


async def test_the_reported_case_now_comes_back_as_a_blocked_case(stubbed) -> None:
    """Regression for the reported decision, reproduced in its own terms.

    What shipped: correctly classified as asking for a verdict, correctly retaining
    and citing the rule that governs it, and then `not_settled_by_rules` with prose
    saying the exact measure could not be determined and an empty
    `missing_information` — a reviewer told the policy did not answer them, when it
    answered everything but the one value they were never asked for.

    What comes back now: the blocked state, the settled part kept in the
    explanation, and a structured question naming only the selector. The same code
    path, with no branch of its own, produces this for the four unrelated policies
    above.
    """

    stubbed.verdict_reply = {
        "status": "not_settled_by_rules",
        "answer": (
            "Being away without permission or an accepted reason for that many days falls under the "
            "rule, which sets four measures running from a warning to a termination, with the days "
            "away deducted in every case. Which measure applies depends on which time this is."
        ),
        "verdict": "",
        "cited_rule_ids": ["R-MEASURED"],
        "missing_required_facts": ["time-within-period"],
        "missing_required_facts_detail": [
            {
                "fact": "time-within-period",
                "label": "Which time this has happened within the period",
                "why_needed": "The rule sets a different measure for each time.",
                "required_by_rule_ids": ["R-MEASURED"],
            }
        ],
        "unsettled_reason": "missing_case_fact",
        "declined": False,
        "note": "",
    }

    decision = await ai_case_intent.answer_decision_over_policies(
        [_measured_case_record()],
        scenario="I was away for three days without an accepted reason. What happens to me?",
    )

    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == ""
    assert decision["missing_required_facts"] == ["time-within-period"]
    assert decision["missing_information"] == [
        {
            "fact": "time-within-period",
            "label": "Which time this has happened within the period",
            "why_needed": "The rule sets a different measure for each time.",
            "required_by_rule_ids": ["R-MEASURED"],
        }
    ]
    # The part the rule does settle is still in front of the reviewer.
    assert "falls under the rule" in decision["answer"]
    assert decision["citations"][0]["rule_id"] == "R-MEASURED"


def test_the_measured_case_is_not_the_only_shape_under_test() -> None:
    """A guard on this file's own method, not on the module's behaviour.

    The regression above is one policy. If it ever became the only fixture — by
    deletion, by a merge, or by someone trimming "duplicate" parametrisation — the
    suite would go on passing while proving something far weaker than it claims.
    So the file asserts its own breadth: several unrelated subjects, each with a
    delegated-discretion control, and at least one written in vocabulary that
    exists nowhere.
    """

    assert len(DOMAINS) >= 3, "the contract is proved over unrelated domains, not one"
    assert len({d.key for d in DOMAINS}) == len(DOMAINS), "the domains must be distinct"
    # Each domain states explicit alternative outcomes *and* carries a control in
    # which the record itself declines to decide.
    for domain in DOMAINS:
        assert domain.schedule_text and domain.delegated_text
        assert domain.selector_fact and domain.selector_label
    # And one of them shares no vocabulary with anything, so no word list can pass.
    assert any("quandle" in d.schedule_text for d in DOMAINS)


def test_the_gather_is_told_the_list_is_not_the_only_place_a_fact_is_named() -> None:
    """The correction that matters most stops the wrong reply being produced.

    Post-processing can only relabel what the model returned. The reading itself
    lives in the prompt, and both prompts must say that `required_facts` is one
    place a needed fact is named rather than the test, and must point at the
    rule's own words for the rest.
    """

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert "whether or not `required_facts` lists it" in prompt
        assert "not the only one" in prompt
        assert "`evidence_refs` into `spans`" in prompt


def test_the_gather_is_asked_which_kind_of_non_settlement_it_found() -> None:
    """The distinction is asked for, and self-checked, not inferred downstream.

    The older contract asked for the missing facts *only* when the status was
    already the blocked one — so a model that had settled on
    `not_settled_by_rules` was told to leave the one field that contradicts it
    empty, and the contradiction never became visible. Both prompts now ask for
    the missing facts whatever status was chosen, ask which kind of
    non-settlement it is, and ask the model to re-read its own answer before
    claiming the policy is silent.
    """

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert '"unsettled_reason"' in prompt
        assert ai_case_intent.UNSETTLED_MISSING_CASE_FACT in prompt
        assert ai_case_intent.UNSETTLED_RECORD_DOES_NOT_DETERMINE in prompt
        assert "including when you were minded to return" in prompt
        assert "read back what you have written and check it against the status you chose" in prompt


def test_the_prompts_do_not_ask_the_model_to_supply_a_fact_it_was_not_given() -> None:
    """Naming what is missing is not the same as filling it in.

    The one thing worse than reporting a blocked case as unsettled is answering it
    with a value nobody supplied. Both prompts forbid choosing the selector,
    reading it off from what is typical, and answering for a value that was not
    given — and post-processing never manufactures one either, which the
    "names nothing" tests above hold from the other side.
    """

    for prompt in (
        ai_case_intent._DECISION_SYSTEM_PROMPT,
        ai_case_intent._DECISION_MULTI_SYSTEM_PROMPT,
    ):
        assert "do not choose the selector for the reviewer" in prompt
        assert "read it off from what is usual or likely" in prompt
        assert "answer for a value they did not give" in prompt
        assert "Never guess a fact of the case that the rules turn on" in prompt
