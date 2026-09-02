"""Rank says which policies bear on a question. It does not say they fit.

THE DEFECT THIS FILE HOLDS

Receipt `94067e47-ea6d-466b-ad7a-c5d841c7532a`, scenario "i need to take 4 days
annual vacation". Retrieval retained five policies: the Annual Vacation policy at
rank 0 with ten rules — the one that governs the question — and, at rank 3, a
Table of Violations and Penalties with seventy-four rules that has nothing to do
with taking leave. Combined: 229,389 characters against a 200,000 budget. The
gather refused the *whole set* and the reviewer received no answer at all.

Every individual step behaved as designed. Retrieval ranked correctly. The
gather refused rather than trimming, which is right. What was missing was the
step between them: nothing asked whether the retained set *fit*, so an
irrelevant large policy could deny an answer that was sitting in the relevant
small one. The reviewer's own reading was blunt and correct — this is a missing
information case, not a no-answer case.

WHAT IS ASSERTED HERE

  * the bearing policy survives and is evaluated, and the oversized irrelevant
    one is set aside with `outside_payload_budget` — not trimmed, not silently
    dropped, and visible in the narrowing disclosure;
  * rank order is preserved and a smaller policy ranked *below* the oversized one
    is still admitted, so one large record costs only itself;
  * when the highest-ranked policy alone cannot fit, the honest oversize refusal
    stands rather than an empty retained set that would read as "nothing matched";
  * a policy narrowed to a slice and *then* set aside for size carries no
    `rule_selection` at all — a selection records what was read, and a discarded
    policy delivered none of it to any gather, so neither the disclosure nor the
    decision hash may name its rules;
  * end to end, the live scenario now reaches a verdict branch that returns
    structured missing information instead of a global oversize refusal.

Nothing here names a real document. The fixture's headings and sentences are its
own; what is asserted is the *relationship* between rank, size and what was
evaluated, which must hold for any governance corpus.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/test")

from policy_platform.contracts.conditions import AllCondition  # noqa: E402
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation  # noqa: E402
from policy_platform.contracts.policy import EvidenceReference, RequiredFact  # noqa: E402
from policy_platform.infrastructure.assistants import ai_case_intent, ai_case_project  # noqa: E402
from policy_platform.infrastructure.projection.policy_case_payload import (  # noqa: E402
    build_case_payload,
)
from policy_platform.infrastructure.projection import policy_rule_slice as rule_slice  # noqa: E402
from policy_platform.infrastructure.search.policy_index import policy_document_id  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402
from tests.fixtures.search_stubs import manifest_ids  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_DV = "22222222-2222-2222-2222-222222222222"
_PV = "33333333-3333-4333-8333-333333333333"

#: The policy that governs the live scenario: few rules, one of them naming a
#: quantity the case must supply before a verdict can be reached.
_LEAVE_KEY = "annual-leave"

#: The policy that broke it: many rules, each carrying a long source sentence.
#: Nothing about leave is in it; it is retained only because it ranked inside the
#: retention budget, and it is large enough on its own to exhaust the payload.
_PENALTIES_KEY = "violations-and-penalties"


def _long_sentence(marker: str, *, bulk: int = 4) -> str:
    """A source sentence of realistic length, so size comes from real content.

    Padding the payload with a repeated character would make the budget check
    pass against something no document produces. Each rule here carries a
    paragraph-length clause, which is what a penalties table's rows actually look
    like once their verbatim text is stored. `bulk` scales the clause so a
    fixture can be large in *characters* while staying small in *rule count* —
    the two are independent, and the two narrowings they trigger are different
    mechanisms that must be testable apart.
    """

    return (
        f"Clause {marker}. Where a person subject to this instrument acts in the manner described "
        f"in this clause, the responsible authority shall record the matter, notify the parties "
        f"entitled to notice under the preceding clause, and apply the measure set out in the "
        f"corresponding column of the schedule, having regard to any prior occurrence recorded "
        f"against the same person within the period the schedule prescribes for that measure."
    ) * bulk


def _payload(
    provision_key: str,
    *,
    rule_count: int,
    required_fact: str | None = None,
    heading: str | None = None,
    bulk: int = 4,
    distinctive: dict[int, str] | None = None,
) -> dict:
    """One lean record with `rule_count` rules, sized by its own source text.

    `distinctive` gives named rows their own vocabulary — a real penalties table
    row says what it is about, and the relevance selection has nothing to key on
    unless the fixture's rows differ the way a document's rows differ.
    """

    rules = []
    for index in range(rule_count):
        marker = f"{provision_key}-{index}"
        subject = (distinctive or {}).get(index, "")
        source = _long_sentence(marker, bulk=bulk)
        if subject:
            source = f"{subject} {source}"
        rule = make_rule(f"AI-{marker}", condition=AllCondition(all=[]))
        update: dict[str, Any] = {
            "title": f"Rule {index} of {provision_key}",
            "description": f"What {provision_key} provides at {index}.",
            "formulation": RuleFormulation(canonical=CanonicalPolicy(source_text=source)),
            "evidence": [
                EvidenceReference(
                    document_version_id=_DV,
                    source_hash="h" * 16,
                    page=index + 1,
                    section=f"section {index}",
                    clause_id=f"C-{marker}",
                    start_offset=0,
                    end_offset=10,
                )
            ],
        }
        if required_fact and index == 0:
            update["required_facts"] = [RequiredFact(name=required_fact, data_type="number", unit="days")]
        rules.append(rule.model_copy(update=update))

    return build_case_payload(
        policy_set_id="set-1",
        provision_id=f"prov-{provision_key}",
        provision_key=provision_key,
        heading_path=[heading or f"Heading of {provision_key}"],
        rules=rules,
    )


def _candidate(provision_key: str, payload: dict) -> dict:
    envelope = payload.get("envelope") or {}
    return {
        "provision_id": f"prov-{provision_key}",
        "provision_key": provision_key,
        # The document's own heading, so the disclosure sentence a reviewer reads
        # names the policy the way the document does.
        "heading_path": list(envelope.get("heading_path") or [f"Heading of {provision_key}"]),
        "rules": len(payload.get("rules") or []),
        "policy_version_id": _PV,
        "search_document_id": policy_document_id(policy_version_id=_PV, provision_key=provision_key),
        "payload": payload,
    }


def _hit(provision_key: str, score: float) -> dict:
    return {
        "id": policy_document_id(policy_version_id=_PV, provision_key=provision_key),
        "@search.score": score,
        "policy_id": provision_key,
        "document_version": _PV,
    }


def _record(provision_key: str, payload: dict) -> dict:
    return {
        "policy": {
            "provision_id": f"prov-{provision_key}",
            "provision_key": provision_key,
            "heading_path": [f"Heading of {provision_key}"],
        },
        "payload": payload,
    }


class _Settings:
    ai_enabled = True
    search_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_secondary_deployment = "fast"
    azure_search_authoring_index = "policy-authoring"


class _NamespacePolicySet:
    def __init__(self, set_id: str, key: str) -> None:
        self.id = set_id
        self.key = key


class _StubEmbedClient:
    def __init__(self, settings: Any) -> None:
        pass

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


def _search_client(order: list[str]):
    """A search client whose ranking is exactly `order`, highest first."""

    class _Client:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_hit(key, 0.9 - (i * 0.1)) for i, key in enumerate(order)]

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return manifest_ids(k.get("filter_expr", ""))

    return _Client


def _wire(
    monkeypatch: pytest.MonkeyPatch, *, candidates: list[dict], order: list[str]
) -> list[list[dict]]:
    """Stub the project scope, the embedding and the search, and spy the gather."""

    scope = {
        "has_published_version": True,
        "active_version_id": _PV,
        "active_version_number": 2,
        "candidates": candidates,
        "excluded": [],
    }

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return scope

    gathered: list[list[dict]] = []

    async def _spy(records: list[dict], *, scenario: str, reasoning_effort: str = "medium", **kw: Any) -> dict:
        gathered.append(records)
        return {
            "intent": ai_case_intent.DECISION,
            "information_requested": False,
            "verdict_requested": True,
            "classification_reasoning": "supplies a duration and asks whether it is allowed",
            "classifier_version": ai_case_intent.NEEDS_CLASSIFIER_VERSION,
            "informational": None,
            "decision": {
                "status": ai_case_intent.MISSING_REQUIRED_FACTS,
                "verdict": "",
                "answer": "The entitlement turns on accrued balance, which was not supplied.",
                "missing_required_facts": ["accrued-leave-balance"],
                "missing_information": [
                    {
                        "fact": "accrued-leave-balance",
                        "label": "Accrued leave balance",
                        "why_needed": "The entitlement is measured against the balance already accrued.",
                        "required_by_rule_ids": [f"AI-{_LEAVE_KEY}-0"],
                    }
                ],
                "citations": [],
                "note": "",
                "grounding": {"prompt_version": ai_case_intent.PROMPT_VERSION},
            },
            "reasoning_effort": reasoning_effort,
        }

    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _StubEmbedClient)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _search_client(order))
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy)
    return gathered


async def _run(scenario: str = "i need to take 4 days annual vacation") -> dict:
    return await ai_case_project.answer_project_case(
        object(), policy_set=_NamespacePolicySet("set-1", "xx"), scenario=scenario
    )


# ── the fitting rule, on its own ─────────────────────────────────────


def test_whole_records_are_admitted_in_rank_order_while_they_fit() -> None:
    """The rule, stated directly: rank order, whole records, up to the budget."""

    small = _record("a", _payload("a", rule_count=2))
    medium = _record("b", _payload("b", rule_count=3))
    pairs = [({"provision_key": "a"}, small), ({"provision_key": "b"}, medium)]

    kept, over = ai_case_project.fit_within_payload_budget(pairs, budget_chars=1_000_000)

    assert [r["policy"]["provision_key"] for _, r in kept] == ["a", "b"]
    assert over == []


def test_a_policy_that_would_overflow_is_set_aside_and_the_rest_still_fit() -> None:
    """One large record costs only itself.

    Stopping the scan at the first overflow would discard every policy below it,
    including ones that fit — a narrowing with no defensible account of itself.
    So the scan continues in rank order and later, smaller policies are still
    admitted.
    """

    first = _record("a", _payload("a", rule_count=2))
    huge = _record("big", _payload("big", rule_count=40))
    last = _record("c", _payload("c", rule_count=2))

    entries = [
        {"provision_key": "a", "retained": True},
        {"provision_key": "big", "retained": True},
        {"provision_key": "c", "retained": True},
    ]
    pairs = list(zip(entries, [first, huge, last]))

    budget = ai_case_project._combined_chars([first, last]) + 10
    kept, over = ai_case_project.fit_within_payload_budget(pairs, budget_chars=budget)

    assert [r["policy"]["provision_key"] for _, r in kept] == ["a", "c"]
    assert [e["provision_key"] for e in over] == ["big"]
    # Rank order among the survivors is untouched, and nothing was trimmed.
    assert len(kept[0][1]["payload"]["rules"]) == 2
    assert len(kept[1][1]["payload"]["rules"]) == 2


def test_a_sole_oversized_policy_is_kept_so_the_refusal_stays_honest() -> None:
    """An empty retained set would read as "no policy matched". That is false.

    When the highest-ranked policy alone exceeds the budget, the truthful outcome
    is the existing oversize refusal — the policy that matched is larger than one
    pass can read — not a narrowing that quietly reports nothing bore on the
    question.
    """

    huge = _record("big", _payload("big", rule_count=40))
    pairs = [({"provision_key": "big", "retained": True}, huge)]

    kept, over = ai_case_project.fit_within_payload_budget(pairs, budget_chars=100)

    assert [r["policy"]["provision_key"] for _, r in kept] == ["big"]
    assert over == []


# ── the live defect, end to end ──────────────────────────────────────


async def test_a_large_irrelevant_policy_is_read_by_rule_and_stops_denying_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported receipt, reproduced and fixed.

    Rank 0 is the policy that governs the question and is small. Rank 3 is a
    penalties table with seventy-four rows and nothing to do with leave. Before
    rule-level retrieval their combined record exceeded the one-pass budget and
    the gather refused everything — the reviewer got no answer for a question the
    corpus could answer.

    The table is now read *by rule*: fifteen of its seventy-four rows are put in
    front of the model instead of all of them, the combined record fits, and the
    leave policy — small enough to pass whole — is evaluated.
    """

    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")
    penalties = _payload(_PENALTIES_KEY, rule_count=74)
    filler = [_payload(f"other-{i}", rule_count=3) for i in range(2)]

    candidates = [
        _candidate(_LEAVE_KEY, leave),
        _candidate("other-0", filler[0]),
        _candidate("other-1", filler[1]),
        _candidate(_PENALTIES_KEY, penalties),
    ]
    order = [_LEAVE_KEY, "other-0", "other-1", _PENALTIES_KEY]

    # The precondition: read whole, the retained set really does overflow.
    everything = [_record(c["provision_key"], c["payload"]) for c in candidates]
    assert ai_case_project._combined_chars(everything) > ai_case_project.PAYLOAD_BUDGET_CHARS

    gathered = _wire(monkeypatch, candidates=candidates, order=order)

    result = await _run()

    assert len(gathered) == 1
    evaluated = {r["policy"]["provision_key"]: r for r in gathered[0]}

    # The governing policy is there, whole — it is under the threshold.
    assert _LEAVE_KEY in evaluated
    assert len(evaluated[_LEAVE_KEY]["payload"]["rules"]) == 10

    # The table is there too, but only fifteen of its rows.
    assert _PENALTIES_KEY in evaluated
    assert len(evaluated[_PENALTIES_KEY]["payload"]["rules"]) == rule_slice.SELECTED_RULE_BUDGET

    assert result["size"]["combined_chars"] <= ai_case_project.PAYLOAD_BUDGET_CHARS
    assert result["size"]["oversize"] is False

    # And the reviewer gets the verdict branch's structured missing information,
    # not a global refusal.
    decision = result["evaluation"]["decision"]
    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == ""
    assert decision["missing_information"][0]["label"] == "Accrued leave balance"


async def test_the_slice_is_disclosed_as_a_count_of_the_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No answer may claim a policy was read whole when a slice of it was.

    The disclosure a reviewer is owed reads "74 rules · 15 selected for this
    case", and the ids make it checkable rather than merely counted.
    """

    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")
    penalties = _payload(_PENALTIES_KEY, rule_count=74, heading="Table of Violations and Penalties")
    candidates = [_candidate(_LEAVE_KEY, leave), _candidate(_PENALTIES_KEY, penalties)]

    _wire(monkeypatch, candidates=candidates, order=[_LEAVE_KEY, _PENALTIES_KEY])

    result = await _run()

    by_key = {entry["provision_key"]: entry for entry in result["considered"]}

    # The small policy is untouched and says so, rather than being described as
    # a selection of all of its rules.
    whole = by_key[_LEAVE_KEY]["rule_selection"]
    assert whole["method"] == rule_slice.METHOD_WHOLE_POLICY
    assert whole["sliced"] is False
    assert whole["total_rules"] == whole["selected_rules"] == 10
    assert whole["rules_discarded"] == 0

    sliced = by_key[_PENALTIES_KEY]["rule_selection"]
    assert sliced["sliced"] is True
    assert sliced["total_rules"] == 74
    assert sliced["selected_rules"] == rule_slice.SELECTED_RULE_BUDGET
    assert sliced["rules_discarded"] == 74 - rule_slice.SELECTED_RULE_BUDGET
    assert len(sliced["selected_rule_ids"]) == sliced["selected_rules"]
    # Nothing in the question's vocabulary appears in a penalties table, so the
    # honest report is that no rule matched and a bounded sample was taken —
    # not a relevance claim the words do not support.
    assert sliced["method"] == rule_slice.METHOD_DOCUMENT_ORDER

    retrieval = result["retrieval"]
    assert retrieval["policies_rule_sliced"] == 1
    assert retrieval["large_policy_rule_threshold"] == rule_slice.LARGE_POLICY_RULE_THRESHOLD
    assert retrieval["selected_rule_budget"] == rule_slice.SELECTED_RULE_BUDGET
    # The sentence a reviewer reads names the policy, its size and the slice.
    assert "Table of Violations and Penalties · 74 rules · 15 selected for this case" in (
        retrieval["reason"]
    )


async def test_a_query_targeting_one_violation_selects_its_rows_not_all_seventy_four(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same fix.

    Skipping the table wholesale was honest and blunt: a question that genuinely
    asks about one violation then got nothing from the one document that answers
    it. Selection has to actually work — the rows that name the subject are
    chosen, and the sixty-odd that do not are not.
    """

    penalties = _payload(
        _PENALTIES_KEY,
        rule_count=74,
        heading="Table of Violations and Penalties",
        # Three rows carry their own subject, the way a schedule's rows do.
        distinctive={
            7: "Unauthorised absence from the workplace without notice.",
            41: "Unauthorised absence exceeding the permitted consecutive days.",
            60: "Damage to equipment issued for official duties.",
        },
    )
    candidates = [_candidate(_PENALTIES_KEY, penalties)]
    gathered = _wire(monkeypatch, candidates=candidates, order=[_PENALTIES_KEY])

    result = await _run(scenario="what is the penalty for unauthorised absence from the workplace?")

    selection = result["considered"][0]["rule_selection"]
    # The rule index took part — it was queried under the expected projection and
    # ranked none of this policy's rows — so the method says so and the count of
    # what it contributed is zero. "Asked and silent" and "not asked" are
    # different facts and the disclosure keeps them apart.
    assert selection["method"] == rule_slice.METHOD_HYBRID_RULE
    assert selection["rule_index_state"] == rule_slice.RULE_INDEX_MATCHED
    assert selection["rule_index_hits"] == 0
    assert selection["total_rules"] == 74
    # Only the rows the question's terms reach — far fewer than the budget, and
    # very far from all seventy-four.
    assert selection["selected_rules"] < rule_slice.SELECTED_RULE_BUDGET
    assert f"AI-{_PENALTIES_KEY}-7" in selection["selected_rule_ids"]
    assert f"AI-{_PENALTIES_KEY}-41" in selection["selected_rule_ids"]
    assert f"AI-{_PENALTIES_KEY}-60" not in selection["selected_rule_ids"]

    # And that is exactly what reached the model.
    evaluated = {r["rule_id"] for r in gathered[0][0]["payload"]["rules"]}
    assert evaluated == set(selection["selected_rule_ids"])


async def test_the_selection_is_deterministic_for_one_question_and_version() -> None:
    """A receipt naming `selected_rule_ids` is worth nothing if they can change.

    No model call, no randomness, and every tie broken by document order — so the
    same question against the same published version selects the same rules on
    every run, which is what makes the disclosure checkable months later.
    """

    penalties = _payload(
        _PENALTIES_KEY,
        rule_count=74,
        distinctive={7: "Unauthorised absence from the workplace.", 41: "Unauthorised absence again."},
    )
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}
    question = "what is the penalty for unauthorised absence?"

    runs = [
        rule_slice.select_rules_for_scenario(penalties, policy=policy, scenario=question)[1][
            "selected_rule_ids"
        ]
        for _ in range(4)
    ]

    assert len({tuple(run) for run in runs}) == 1, "the same question selected different rules"


def test_boilerplate_every_row_shares_cannot_carry_a_selection() -> None:
    """Why the weighting is computed over the policy's own rules.

    A schedule's rows share almost all of their words — the authority, the
    measure, the notice. If those counted, every row would score identically and
    the selection would be document order wearing a relevance label. Weighting by
    inverse document frequency *within this policy* clamps them to nothing, so
    only what distinguishes one row from another can decide.
    """

    penalties = _payload(_PENALTIES_KEY, rule_count=40, distinctive={5: "Falsifying a timesheet."})

    # A question made only of the shared boilerplate reaches nothing.
    shared = rule_slice.score_rules(penalties, "the responsible authority shall record the matter")
    assert max(shared) == 0.0

    # A question naming what one row is about reaches that row and only it.
    targeted = rule_slice.score_rules(penalties, "falsifying a timesheet")
    assert targeted[5] > 0
    assert [i for i, score in enumerate(targeted) if score > 0] == [5]


def test_a_policy_at_or_under_the_threshold_is_handed_over_untouched() -> None:
    """The ordinary case is not merely equivalent — it is the same object.

    A selection pass that quietly rebuilt every small policy would be a second
    behaviour nobody asked for, and any difference it introduced would show up
    as an unexplained change in an answer rather than as a change in this file.
    """

    payload = _payload("small", rule_count=rule_slice.LARGE_POLICY_RULE_THRESHOLD)
    policy = {"provision_id": "p", "provision_key": "small", "heading_path": ["h"]}

    returned, selection = rule_slice.select_rules_for_scenario(
        payload, policy=policy, scenario="anything at all"
    )

    assert returned is payload, "a small policy's record was rebuilt rather than passed through"
    assert selection["method"] == rule_slice.METHOD_WHOLE_POLICY
    assert selection["sliced"] is False
    assert selection["total_rules"] == selection["selected_rules"]
    assert selection["rules_discarded"] == 0

    # One rule more and it is a table, read by rule.
    bigger = _payload("bigger", rule_count=rule_slice.LARGE_POLICY_RULE_THRESHOLD + 1)
    _, sliced = rule_slice.select_rules_for_scenario(
        bigger, policy=policy, scenario="anything at all"
    )
    assert sliced["sliced"] is True


def _with_many_links(payload: dict, *, sources: list[int], targets: list[int]) -> dict:
    """Give several selected rules a long list of explicit context each.

    This is the shape decision `991d819b` hit: enough scenario matches to fill the
    rule budget, and enough drafter-written links behind them to more than double
    the record if context were allowed to extend the budget.
    """

    rules = payload["rules"]
    target_ids = [rules[i]["rule_id"] for i in targets]
    half = len(target_ids) // 2
    for source in sources:
        rules[source] = {
            **rules[source],
            "supersedes_rule_ids": list(target_ids[:half]),
            "related_rule_ids": list(target_ids[half:]),
        }
    return payload


def test_context_never_pushes_the_record_past_the_rule_budget() -> None:
    """The defect in decision `991d819b`, stated as the invariant it broke.

    That receipt reported `selected_rule_budget=15` and put thirty-five rules of
    the seventy-four-row penalties policy in front of the gather: fifteen
    scenario matches plus twenty pulled in as context. Every step was within
    something and nothing measured the total, so the number the reviewer was
    shown was not the number that held.

    Here fifteen rows match the question and forty more are named as context
    behind them. The record must still hold fifteen rules, and every count on the
    receipt must describe that same record.
    """

    matched = {index: f"Falsifying a timesheet in case {index}." for index in range(15)}
    penalties = _payload(_PENALTIES_KEY, rule_count=74, distinctive=matched)
    penalties = _with_many_links(
        penalties, sources=list(range(15)), targets=list(range(20, 60))
    )
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    sliced, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="falsifying a timesheet"
    )

    # The claim the receipt makes, and the record it describes, are the same one.
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET
    assert selection["selected_rules"] == rule_slice.SELECTED_RULE_BUDGET
    assert len(sliced["rules"]) == selection["selected_rules"]
    assert len(selection["selected_rule_ids"]) == selection["selected_rules"]
    assert selection["total_rules"] == 74
    assert selection["rules_discarded"] == 74 - selection["selected_rules"]

    # The selection took every slot, so context took none — and said so, by id.
    assert selection["context_rules_added"] == 0
    assert len(selection["context_rules_omitted"]) == 40
    assert set(selection["context_rules_omitted"]) == {
        f"AI-{_PENALTIES_KEY}-{index}" for index in range(20, 60)
    }
    # Nothing is both read and reported as omitted.
    read = {rule["rule_id"] for rule in sliced["rules"]}
    assert read.isdisjoint(selection["context_rules_omitted"])
    assert read == set(selection["selected_rule_ids"])

    # `chars` describes the record that was actually built.
    assert selection["chars"] == rule_slice._record_chars(policy, sliced)
    assert selection["oversize"] is False


def test_context_fills_the_slots_the_selection_left_and_no_more() -> None:
    """Context is not forbidden — it is subordinate.

    When relevance takes only a few rows, the drafter's explicit links are worth
    following into the unused slots. The ceiling still binds: exactly the budget
    is reached, the admitted context is counted inside `selected_rules`, and the
    links that found no slot are named.
    """

    penalties = _payload(
        _PENALTIES_KEY, rule_count=74, distinctive={5: "Falsifying a timesheet."}
    )
    penalties = _with_many_links(penalties, sources=[5], targets=list(range(20, 60)))
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    sliced, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="falsifying a timesheet"
    )

    primary = [
        rid
        for rid in selection["selected_rule_ids"]
        if rid == f"AI-{_PENALTIES_KEY}-5"
    ]
    assert primary, "the rule the question is about was not selected"

    assert selection["selected_rules"] == rule_slice.SELECTED_RULE_BUDGET
    assert len(sliced["rules"]) == rule_slice.SELECTED_RULE_BUDGET
    # One scenario match plus the context that fit the remaining slots.
    assert selection["context_rules_added"] == rule_slice.SELECTED_RULE_BUDGET - 1
    assert (
        selection["context_rules_added"] + 1 == selection["selected_rules"]
    ), "context is counted inside the budget, not beside it"
    assert len(selection["context_rules_omitted"]) == 40 - selection["context_rules_added"]

    # Every named context rule is either read or reported omitted — never neither.
    read = {rule["rule_id"] for rule in sliced["rules"]}
    named = {f"AI-{_PENALTIES_KEY}-{index}" for index in range(20, 60)}
    assert named <= (read | set(selection["context_rules_omitted"]))
    assert read.isdisjoint(selection["context_rules_omitted"])


def test_which_context_wins_a_scarce_slot_is_deterministic() -> None:
    """A scarce slot must go to the same rule on every run of one question.

    Context is offered in the order the selected rules were chosen, and within a
    rule in its own declared order — what it supersedes before what it is merely
    related to. That ordering is what makes `selected_rule_ids`, and the decision
    hash sealing them, mean anything across two runs.
    """

    def _build():
        penalties = _payload(
            _PENALTIES_KEY, rule_count=74, distinctive={5: "Falsifying a timesheet."}
        )
        return _with_many_links(penalties, sources=[5], targets=list(range(20, 60)))

    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    runs = [
        rule_slice.select_rules_for_scenario(
            _build(), policy=policy, scenario="falsifying a timesheet"
        )[1]
        for _ in range(3)
    ]

    assert runs[0]["selected_rule_ids"] == runs[1]["selected_rule_ids"] == runs[2]["selected_rule_ids"]
    assert runs[0]["context_rules_omitted"] == runs[1]["context_rules_omitted"]
    # Superseded rules are offered before merely-related ones, so the first
    # twenty targets are the ones that take the scarce slots.
    admitted = set(runs[0]["selected_rule_ids"]) - {f"AI-{_PENALTIES_KEY}-5"}
    assert admitted <= {f"AI-{_PENALTIES_KEY}-{index}" for index in range(20, 40)}


def test_an_oversize_slice_still_names_the_context_it_did_not_follow() -> None:
    """`context_rules_omitted` must mean one thing on every path.

    When the relevant slice alone will not fit, no context is added — but the
    links are still there and still unfollowed. Reporting an empty omission list
    would tell a reader the rule was read with everything it names.
    """

    penalties = _payload(_PENALTIES_KEY, rule_count=74, bulk=60)
    penalties = _with_many_links(penalties, sources=[0, 1], targets=list(range(20, 30)))
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    _, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="what does this provide?"
    )

    assert selection["oversize"] is True
    assert selection["context_rules_added"] == 0
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET
    assert set(selection["context_rules_omitted"]) == {
        f"AI-{_PENALTIES_KEY}-{index}" for index in range(20, 30)
    }


async def test_no_policy_puts_more_than_the_budget_before_either_gather(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end, and over both tracks: the ceiling holds on the real records.

    Both tracks read the same retained records, so asserting it on what the
    gather was handed covers the information track and the verdict track at once.
    """

    matched = {index: f"Falsifying a timesheet in case {index}." for index in range(15)}
    penalties = _payload(_PENALTIES_KEY, rule_count=74, distinctive=matched)
    penalties = _with_many_links(
        penalties, sources=list(range(15)), targets=list(range(20, 60))
    )
    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")

    candidates = [_candidate(_LEAVE_KEY, leave), _candidate(_PENALTIES_KEY, penalties)]
    gathered = _wire(monkeypatch, candidates=candidates, order=[_LEAVE_KEY, _PENALTIES_KEY])

    result = await _run(scenario="falsifying a timesheet")

    for record in gathered[0]:
        rules = record["payload"].get("rules") or []
        assert len(rules) <= rule_slice.SELECTED_RULE_BUDGET, (
            f"{record['policy']['provision_key']} put {len(rules)} rules before the gather"
        )

    by_key = {entry["provision_key"]: entry for entry in result["considered"]}
    selection = by_key[_PENALTIES_KEY]["rule_selection"]
    assert selection["selected_rules"] <= result["retrieval"]["selected_rule_budget"]

    # The receipt's count and the record the gather read are the same number.
    read = {r["policy"]["provision_key"]: r for r in gathered[0]}
    assert len(read[_PENALTIES_KEY]["payload"]["rules"]) == selection["selected_rules"]


def _with_links(payload: dict, *, source: int, supersedes: int, related: int) -> dict:
    """Give one rule the explicit links a drafter writes between rules."""

    rules = payload["rules"]
    rules[source] = {
        **rules[source],
        "supersedes_rule_ids": [rules[supersedes]["rule_id"]],
        "related_rule_ids": [rules[related]["rule_id"]],
    }
    return payload


def test_a_selected_rules_explicit_context_follows_it_into_the_slice() -> None:
    """A rule read without the rule it overrides is read incompletely.

    Relevance selects the row a question is about; the drafter has already said
    which other rows that row cannot be understood without. Those follow it in —
    they are not selected on their own relevance, and they are counted separately
    so a reader can tell "this bore on your question" from "this was pulled in
    behind something that did".

    `exceptions` are not closed over because they are *inline* on the rule: a
    selected rule always carries its own carve-outs.
    """

    penalties = _payload(
        _PENALTIES_KEY,
        rule_count=40,
        distinctive={5: "Falsifying a timesheet."},
    )
    penalties = _with_links(penalties, source=5, supersedes=30, related=31)
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    sliced, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="falsifying a timesheet"
    )

    ids = set(selection["selected_rule_ids"])
    assert f"AI-{_PENALTIES_KEY}-5" in ids, "the rule the question is about was not selected"
    assert f"AI-{_PENALTIES_KEY}-30" in ids, "the rule it supersedes did not follow it"
    assert f"AI-{_PENALTIES_KEY}-31" in ids, "the rule marked related did not follow it"
    assert selection["context_rules_added"] == 2
    assert selection["context_rules_omitted"] == []

    # The context rules are in the record the model sees, whole.
    present = {rule["rule_id"] for rule in sliced["rules"]}
    assert {f"AI-{_PENALTIES_KEY}-30", f"AI-{_PENALTIES_KEY}-31"} <= present

    # And their spans came with them, so a citation to one can resolve.
    referenced = {ref for rule in sliced["rules"] for ref in rule.get("evidence_refs") or []}
    assert referenced <= set(sliced["spans"]), "a rule points at a span the slice dropped"


def test_context_that_does_not_fit_is_named_rather_than_dropped_in_silence() -> None:
    """A tight budget costs context, and says which.

    Silently omitting the rule a selected rule overrides would leave a reader
    believing they had the whole picture. Naming it lets them fetch it — the
    policy's full record is a URL away — and keeps the omission auditable.
    """

    penalties = _payload(_PENALTIES_KEY, rule_count=40, bulk=8, distinctive={5: "Falsifying a timesheet."})
    penalties = _with_links(penalties, source=5, supersedes=30, related=31)
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    # A budget that admits the selected rule and not everything it names.
    selected_only = rule_slice.build_slice(penalties, [penalties["rules"][5]])
    budget = rule_slice._record_chars(policy, selected_only) + 100

    sliced, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="falsifying a timesheet", budget_chars=budget
    )

    assert selection["oversize"] is False, "the relevant slice itself fits"
    assert selection["context_rules_omitted"], "no omission was reported under a tight budget"
    for omitted in selection["context_rules_omitted"]:
        assert omitted not in {rule["rule_id"] for rule in sliced["rules"]}
    # Whatever survived is whole; nothing was cut down to fit.
    assert all(rule.get("evidence_refs") is not None for rule in sliced["rules"])


async def test_a_lower_ranked_policy_is_still_evaluated_after_a_large_one_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rank order is preserved; an oversized record does not end the scan.

    The policies here are *small in rules and large in characters*, so they pass
    the rule-selection threshold untouched and the whole-policy fitting pass is
    the only thing deciding. That keeps the two narrowings independently
    testable: this asserts nothing about slicing, and slicing asserts nothing
    about this.
    """

    first = _payload("first", rule_count=12, bulk=30, required_fact="accrued-leave-balance")
    middle = _payload("middle", rule_count=12, bulk=30)
    tail = _payload("tail", rule_count=2, bulk=1)

    candidates = [
        _candidate("first", first),
        _candidate("middle", middle),
        _candidate("tail", tail),
    ]
    for candidate in candidates[:2]:
        assert len(candidate["payload"]["rules"]) <= rule_slice.LARGE_POLICY_RULE_THRESHOLD
    assert (
        ai_case_project._combined_chars(
            [_record("first", first), _record("middle", middle)]
        )
        > ai_case_project.PAYLOAD_BUDGET_CHARS
    ), "the fixture must overflow on the second policy or this asserts nothing"

    gathered = _wire(monkeypatch, candidates=candidates, order=["first", "middle", "tail"])

    result = await _run()

    evaluated = [r["policy"]["provision_key"] for r in gathered[0]]
    assert evaluated == ["first", "tail"], "rank order was not preserved past the skip"
    assert result["retrieval"]["policies_over_payload_budget"] == 1
    assert result["retrieval"]["policies_rule_sliced"] == 0


async def test_a_whole_policy_that_will_not_fit_beside_another_is_disclosed_by_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No partial answer may claim it read a policy that was discarded.

    A narrowing a reviewer cannot see is the failure this whole module exists to
    prevent, and a *second* narrowing invisible behind the first would be worse:
    the policy was ranked highly, so a reader would reasonably assume it was
    read. It is reported with its own reason, kept apart from "search ranked it
    too low", and counted in its own field.
    """

    first = _payload("first", rule_count=12, bulk=30)
    second = _payload("second", rule_count=12, bulk=30)
    candidates = [_candidate("first", first), _candidate("second", second)]

    _wire(monkeypatch, candidates=candidates, order=["first", "second"])

    result = await _run()

    by_key = {entry["provision_key"]: entry for entry in result["considered"]}

    kept = by_key["first"]
    assert kept["retained"] is True
    assert kept.get("discard_reason") is None

    dropped = by_key["second"]
    assert dropped["retained"] is False
    assert dropped["discard_reason"] == ai_case_project.DISCARD_OUTSIDE_PAYLOAD_BUDGET
    # It really did surface, and where it surfaced is kept: a reader comparing it
    # against what was evaluated needs to see it ranked, not that it was unranked.
    assert dropped["best_rank"] == 1
    assert dropped["best_score"] is not None

    retrieval = result["retrieval"]
    assert retrieval["policies_over_payload_budget"] == 1
    assert retrieval["payload_budget_chars"] == ai_case_project.PAYLOAD_BUDGET_CHARS
    assert retrieval["policies_retained"] == 1
    assert retrieval["policies_discarded"] == 1
    assert retrieval["status"] == ai_case_project.RETRIEVAL_NARROWED
    assert ai_case_project.DISCARD_OUTSIDE_PAYLOAD_BUDGET in retrieval["reason"]

    # The two narrowings are told apart rather than merged.
    assert ai_case_project.DISCARD_OUTSIDE_BUDGET not in json.dumps(result["considered"])


async def test_a_sliced_policy_set_aside_for_size_carries_no_rule_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selection is a record of what was *read*, so a discarded policy has none.

    The two narrowings run in that order: rules are selected first, then whole
    (already sliced) records are fitted into one pass. A large policy can
    therefore be sliced and *then* set aside for size — and at that point its
    selected rules reached no gather at all. Leaving `rule_selection` on the
    entry would put `selected_rule_ids` on a receipt for a policy nothing was
    evaluated from, and the v2 hash seals those ids, so the seal would cover
    rule text no model ever saw. That is the same claim as an undisclosed
    discard, inverted: not hiding a narrowing, but asserting a reading that
    never happened.

    The policy that *was* evaluated keeps its selection, and the sliced count
    counts only what fit — otherwise the headline would point a reader at a
    per-policy `rule_selection` that is no longer there.
    """

    from datetime import datetime, timezone

    from policy_platform.application.policy_case_decision import Caller, build_envelope
    from policy_platform.contracts.case_decision import (
        PolicySetRef,
        decision_hash_preimage_v2,
    )

    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")
    penalties = _payload(
        _PENALTIES_KEY, rule_count=40, bulk=60, heading="Table of Violations and Penalties"
    )

    # The fixture must exercise *both* narrowings or it asserts nothing: the
    # table has to be large enough in rules to be sliced, and its slice still
    # large enough in characters not to fit beside the leave policy.
    assert len(penalties["rules"]) > rule_slice.LARGE_POLICY_RULE_THRESHOLD
    sliced_payload, selection = rule_slice.select_rules_for_scenario(
        penalties,
        policy={"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]},
        scenario="i need to take 4 days annual vacation",
    )
    assert selection["sliced"] is True
    assert (
        ai_case_project._combined_chars(
            [_record(_LEAVE_KEY, leave), _record(_PENALTIES_KEY, sliced_payload)]
        )
        > ai_case_project.PAYLOAD_BUDGET_CHARS
    ), "the slice must still overflow beside the leave policy or nothing is set aside"

    candidates = [_candidate(_LEAVE_KEY, leave), _candidate(_PENALTIES_KEY, penalties)]
    gathered = _wire(monkeypatch, candidates=candidates, order=[_LEAVE_KEY, _PENALTIES_KEY])

    response = await _run()

    # Only the leave policy was read.
    assert [r["policy"]["provision_key"] for r in gathered[0]] == [_LEAVE_KEY]

    by_key = {entry["provision_key"]: entry for entry in response["considered"]}
    dropped = by_key[_PENALTIES_KEY]

    assert dropped["retained"] is False
    assert dropped["discard_reason"] == ai_case_project.DISCARD_OUTSIDE_PAYLOAD_BUDGET
    assert "rule_selection" not in dropped, (
        "a policy set aside for size claims a rule selection it never delivered"
    )
    # What made it a discard is still fully visible; only the false claim is gone.
    assert dropped["best_rank"] == 1
    assert dropped["best_score"] is not None

    # The policy that was actually evaluated keeps its account of itself.
    assert by_key[_LEAVE_KEY]["rule_selection"]["method"] == rule_slice.METHOD_WHOLE_POLICY

    retrieval = response["retrieval"]
    assert retrieval["policies_over_payload_budget"] == 1
    assert retrieval["policies_rule_sliced"] == 0, "nothing sliced survived to be read"
    # No unread rule id may appear anywhere in the reviewer-facing disclosure.
    disclosure = json.dumps(response["considered"]) + json.dumps(retrieval)
    for rule_id in selection["selected_rule_ids"]:
        assert rule_id not in disclosure

    # ── and the same must hold of the receipt and its seal ───────────
    now = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    envelope = build_envelope(
        decision_id="d-1",
        correlation_id="c-1",
        idempotency_key=None,
        project=PolicySetRef(id="s-1", key="xx", name="Project"),
        caller=Caller(identity="a@b.c", role="viewer", authentication_source="token"),
        scenario="i need to take 4 days annual vacation",
        reasoning_effort="medium",
        requested_provision_id=None,
        received_at=now,
        decided_at=now,
        latency_ms=1,
        response=response,
        context={},
    )

    refs = {ref.provision_key: ref for ref in envelope.considered}
    assert refs[_PENALTIES_KEY].rule_selection is None
    assert refs[_PENALTIES_KEY].discard_reason == ai_case_project.DISCARD_OUTSIDE_PAYLOAD_BUDGET
    assert refs[_LEAVE_KEY].rule_selection is not None

    sealed = {p["provision_key"]: p for p in decision_hash_preimage_v2(envelope)["policies"]}
    assert sealed[_PENALTIES_KEY]["selected_rule_ids"] is None
    assert sealed[_PENALTIES_KEY]["total_rules"] is None
    assert sealed[_PENALTIES_KEY]["retained"] is False


async def test_a_sole_oversized_policy_still_reports_an_honest_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one case neither narrowing can "repair".

    A policy small enough to pass the rule threshold whole, and larger than one
    grounded pass on its own. There is nothing smaller to fall back to: reporting
    an empty retained set would tell the reviewer nothing matched, which is
    false; trimming would answer from part of a policy while presenting as the
    whole. So the policy is kept, `size.oversize` is true, and the gather's
    existing refusal is what the reviewer sees.
    """

    huge = _payload("huge", rule_count=12, bulk=60)
    assert len(huge["rules"]) <= rule_slice.LARGE_POLICY_RULE_THRESHOLD
    assert (
        ai_case_project._combined_chars([_record("huge", huge)])
        > ai_case_project.PAYLOAD_BUDGET_CHARS
    ), "the fixture must exceed the budget on its own or this asserts nothing"

    candidates = [_candidate("huge", huge)]
    gathered = _wire(monkeypatch, candidates=candidates, order=["huge"])

    result = await _run(scenario="what does this provide?")

    # It was not dropped: dropping it would read as "no policy matched".
    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["huge"]
    assert result["size"]["oversize"] is True
    assert result["retrieval"]["policies_retained"] == 1
    assert result["retrieval"]["policies_over_payload_budget"] == 0
    entry = result["considered"][0]
    assert entry["retained"] is True
    assert entry.get("discard_reason") is None


async def test_a_large_policy_whose_slice_will_not_fit_is_an_honest_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rules that bear on the question do not themselves fit.

    Selection has already narrowed as far as it may — the fifteen most relevant
    rows are what was asked for — and they are still too large. Dropping some of
    them would answer from part of the *relevant* slice while presenting as the
    slice, which is the same hiding as trimming a rule, one level up. So the
    slice is returned whole, marked oversize, and refused downstream.
    """

    penalties = _payload(_PENALTIES_KEY, rule_count=40, bulk=60)
    policy = {"provision_id": "p", "provision_key": _PENALTIES_KEY, "heading_path": ["h"]}

    sliced, selection = rule_slice.select_rules_for_scenario(
        penalties, policy=policy, scenario="what does this provide?"
    )

    assert selection["sliced"] is True
    assert selection["oversize"] is True
    assert selection["selected_rules"] == rule_slice.SELECTED_RULE_BUDGET
    assert selection["context_rules_added"] == 0, "no context is added to a slice that cannot fit"
    # Nothing was trimmed to make it fit: every selected rule is present whole.
    assert len(sliced["rules"]) == rule_slice.SELECTED_RULE_BUDGET

    candidates = [_candidate(_PENALTIES_KEY, penalties)]
    gathered = _wire(monkeypatch, candidates=candidates, order=[_PENALTIES_KEY])

    result = await _run(scenario="what does this provide?")

    assert result["size"]["oversize"] is True
    assert [r["policy"]["provision_key"] for r in gathered[0]] == [_PENALTIES_KEY]
    assert result["considered"][0]["rule_selection"]["oversize"] is True


async def test_a_set_that_already_fits_is_left_exactly_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fitting pass must be invisible when nothing needed fitting.

    A budget check that quietly changed the ordinary case would be a second
    behaviour nobody asked for. With every retained policy inside the budget,
    the records, the counts and the reason are what they were before it existed.
    """

    candidates = [
        _candidate("a", _payload("a", rule_count=2)),
        _candidate("b", _payload("b", rule_count=3)),
    ]
    gathered = _wire(monkeypatch, candidates=candidates, order=["a", "b"])

    result = await _run()

    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["a", "b"]
    assert result["retrieval"]["policies_over_payload_budget"] == 0
    assert result["retrieval"]["policies_discarded"] == 0
    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NOT_NARROWED
    assert result["size"]["oversize"] is False
    assert "every published policy in this project was evaluated" in result["retrieval"]["reason"]


# ── the whole path, with the real gather ─────────────────────────────


class _StubModelClient:
    """The model, replaced, serving the classifier and the verdict gather apart.

    Used by the end-to-end test below so the gather's *own* oversize guard is the
    thing being exercised — the guard that refused the live receipt. A spy would
    prove the fitting pass ran; only the real gather proves the refusal no longer
    fires.
    """

    calls: list[dict[str, Any]] = []

    def __init__(self, settings: Any) -> None:
        pass

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        system = messages[0]["content"]
        type(self).calls.append({"system": system, "user": messages[1]["content"]})
        if "information_requested" in system:
            return json.dumps(
                {
                    "information_requested": False,
                    "verdict_requested": True,
                    "reasoning": "supplies a duration and asks whether it may be taken",
                }
            )
        return json.dumps(
            {
                "status": "missing_required_facts",
                "answer": "Whether four days may be taken turns on the balance already accrued.",
                "verdict": "",
                "cited_rule_ids": [f"AI-{_LEAVE_KEY}-0"],
                "missing_required_facts": ["accrued-leave-balance"],
                "missing_required_facts_detail": [
                    {
                        "fact": "accrued-leave-balance",
                        "label": "Accrued leave balance",
                        "why_needed": "The entitlement is measured against the balance accrued.",
                        "required_by_rule_ids": [f"AI-{_LEAVE_KEY}-0"],
                    }
                ],
                "declined": False,
                "note": "",
            }
        )


async def test_the_live_scenario_reaches_missing_information_not_a_global_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acceptance case, through the real gather.

    "I need to take 4 days annual vacation", against a corpus holding a small
    Annual Vacation policy and a large penalties table that ranks inside the
    retention budget. Before the fitting pass the gather measured the combined
    record, found it over budget, and refused the lot — the reviewer received an
    oversize non-answer for a question the corpus could answer.

    The gather's oversize guard is deliberately left running here rather than
    stubbed: it is the code that produced the reported receipt, and the only way
    to show it no longer fires is to let it decide.
    """

    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")
    penalties = _payload(_PENALTIES_KEY, rule_count=74)
    candidates = [_candidate(_LEAVE_KEY, leave), _candidate(_PENALTIES_KEY, penalties)]

    everything = [_record(_LEAVE_KEY, leave), _record(_PENALTIES_KEY, penalties)]
    assert (
        ai_case_project._combined_chars(everything) > ai_case_project.PAYLOAD_BUDGET_CHARS
    ), "the fixture must reproduce the overflow or this asserts nothing"

    scope = {
        "has_published_version": True,
        "active_version_id": _PV,
        "active_version_number": 2,
        "candidates": candidates,
        "excluded": [],
    }

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return scope

    _StubModelClient.reset()
    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _StubEmbedClient)
    monkeypatch.setattr(
        ai_case_project, "AzureSearchClient", _search_client([_LEAVE_KEY, _PENALTIES_KEY])
    )
    # The real gather, with only the model replaced.
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubModelClient)

    result = await _run()

    decision = result["evaluation"]["decision"]
    assert decision["status"] == ai_case_intent.MISSING_REQUIRED_FACTS
    assert decision["verdict"] == "", "a blocked verdict must carry no verdict string"
    assert decision["grounding"]["oversize"] is False, "the gather still refused for size"
    assert decision["missing_information"] == [
        {
            "fact": "accrued-leave-balance",
            "label": "Accrued leave balance",
            "why_needed": "The entitlement is measured against the balance accrued.",
            "required_by_rule_ids": [f"AI-{_LEAVE_KEY}-0"],
        }
    ]

    gathers = [c for c in _StubModelClient.calls if "information_requested" not in c["system"]]
    assert len(gathers) == 1
    prompt = gathers[0]["user"]

    # The leave policy is there whole.
    assert f"AI-{_LEAVE_KEY}-0" in prompt

    # The table is there as a slice, and the rows beyond the budget are not —
    # no answer may claim it read a row it was never shown.
    selection = result["considered"][1]["rule_selection"]
    assert selection["total_rules"] == 74
    assert selection["selected_rules"] == rule_slice.SELECTED_RULE_BUDGET
    for rule_id in selection["selected_rule_ids"]:
        assert rule_id in prompt
    unread = {f"AI-{_PENALTIES_KEY}-{i}" for i in range(74)} - set(selection["selected_rule_ids"])
    assert unread, "the fixture must leave rows unread or this asserts nothing"
    for rule_id in sorted(unread):
        assert rule_id not in prompt

    assert result["retrieval"]["policies_rule_sliced"] == 1
    assert result["size"]["oversize"] is False


# ── the v2 receipt over a budget-narrowed decision ───────────────────


async def test_the_rule_selection_reaches_the_audited_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The receipt must carry the rule-level narrowing, not just the policy one.

    An audited decision that named a seventy-four-rule policy without saying only
    fifteen of its rows were read would let a reader conclude the schedule was
    weighed. It is the same failure as an undisclosed policy discard, one level
    down, and it is the level a citation actually lives at.
    """

    from datetime import datetime, timezone

    from policy_platform.application.policy_case_decision import Caller, build_envelope
    from policy_platform.contracts.case_decision import PolicySetRef

    leave = _payload(_LEAVE_KEY, rule_count=10, required_fact="accrued-leave-balance")
    penalties = _payload(_PENALTIES_KEY, rule_count=74, heading="Table of Violations and Penalties")
    candidates = [_candidate(_LEAVE_KEY, leave), _candidate(_PENALTIES_KEY, penalties)]
    _wire(monkeypatch, candidates=candidates, order=[_LEAVE_KEY, _PENALTIES_KEY])

    response = await _run()

    now = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    envelope = build_envelope(
        decision_id="d-1",
        correlation_id="c-1",
        idempotency_key=None,
        project=PolicySetRef(id="s-1", key="xx", name="Project"),
        caller=Caller(identity="a@b.c", role="viewer", authentication_source="token"),
        scenario="i need to take 4 days annual vacation",
        reasoning_effort="medium",
        requested_provision_id=None,
        received_at=now,
        decided_at=now,
        latency_ms=1,
        response=response,
        context={},
    )

    # The two-track work and the retrieval change compose in one receipt.
    assert envelope.outcome.verdict == "missing_required_facts"
    assert envelope.verdict is not None
    assert envelope.verdict.reached is False
    assert envelope.verdict.decision == ""
    assert [item.label for item in envelope.verdict.missing_information] == [
        "Accrued leave balance"
    ]
    assert envelope.outcome.information == "not_requested"
    assert envelope.information is None

    by_key = {ref.provision_key: ref for ref in envelope.considered}

    whole = by_key[_LEAVE_KEY].rule_selection
    assert whole is not None
    assert whole.sliced is False
    assert whole.method == rule_slice.METHOD_WHOLE_POLICY

    sliced = by_key[_PENALTIES_KEY].rule_selection
    assert sliced is not None
    assert sliced.sliced is True
    assert sliced.total_rules == 74
    assert sliced.selected_rules == rule_slice.SELECTED_RULE_BUDGET
    assert sliced.rules_discarded == 74 - rule_slice.SELECTED_RULE_BUDGET
    assert len(sliced.selected_rule_ids) == sliced.selected_rules

    assert envelope.retrieval.policies_rule_sliced == 1
    assert envelope.retrieval.large_policy_rule_threshold == rule_slice.LARGE_POLICY_RULE_THRESHOLD

    # The seal covers which *rules* were read, not only which policies. The same
    # policy read whole and read as a slice are two different accounts of the
    # same question, and a hash that could not tell them apart would seal the
    # weaker one.
    from policy_platform.contracts.case_decision import decision_hash_preimage_v2

    sealed = {p["provision_key"]: p for p in decision_hash_preimage_v2(envelope)["policies"]}
    assert sealed[_PENALTIES_KEY]["total_rules"] == 74
    assert sealed[_PENALTIES_KEY]["selected_rule_ids"] == sorted(sliced.selected_rule_ids)

    # A different slice of the same policy is a different decision.
    baseline = envelope.decision_hash
    envelope.considered[1].rule_selection.selected_rule_ids = ["AI-something-else"]
    from policy_platform.contracts.case_decision import compute_decision_hash_v2

    assert compute_decision_hash_v2(envelope) != baseline
