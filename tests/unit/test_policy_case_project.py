"""A case put to a *project* is answered against the policies retrieval keeps,
never against the whole set, and what retrieval did is reported so a reviewer can
see the narrowing.

WHY THIS FILE EXISTS

The per-policy path (`ai_case_intent.answer_policy_case`) answers one policy a
reviewer already chose. The project path answers a question the reviewer has *not*
narrowed: it must first retrieve the policies that bear on the question and discard
the rest, then evaluate only the survivors — the user's explicit instruction, and
the core of the feature ("u never run against all published, u must use AI search
and any technique possible to retrieve highest policies match before evaluation,
non matching policies are discarded").

WHY THE GUARDS ARE LOAD-BEARING

A test that passes because a policy was never in front of the evaluator proves
nothing (§9.15). So the narrowing tests assert two things at once: that the
unrelated policy is *discarded*, and that its record never reaches the gather. A
retrieval that retained everything, or the budget being ignored, both fail here.

WHY THE STATES ARE TOLD APART

"Retrieval narrowed to a subset", "retrieval matched nothing", "the project is not
indexed", "search is not configured", "the search call failed", and "the project
has no testable policy" are six different facts about a search (constraint 5). The
one thing forbidden is degrading any of them silently to "answer against all"
(constraint 10). The tests below assert the six read differently and that only a
genuine narrowing reaches the evaluator.

Nothing here names a domain: the fixtures state headings and sentences no document
in this repository contains, so the behaviour must hold for any governance corpus
(constraint 1). The counts a test asserts are *relationships* — retained is a
subset of considered, the bearing policy is retained while the unrelated one is
not — never a literal drawn from one corpus.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation
from policy_platform.contracts.policy import EvidenceReference
from policy_platform.infrastructure.assistants import ai_case_intent
from policy_platform.infrastructure.assistants import ai_case_project
from policy_platform.infrastructure.projection.policy_case_payload import build_case_payload
from policy_platform.infrastructure.search.indexing import clause_search_document_id
from tests.fixtures.factories import make_rule

pytestmark = pytest.mark.anyio


#: A stand-in document version id. The retrieval join key is
#: ``{document_version_id}_{clause_id}`` (`clause_search_document_id`), the same
#: key the search index writes and the projection's spans carry, so a fixture can
#: predict the id a clause would surface under without touching Azure.
_DV = "22222222-2222-2222-2222-222222222222"


def _clause_key(clause_id: str) -> str:
    return clause_search_document_id(_DV, clause_id)


def _payload_for(provision_id: str, provision_key: str, clause_ids: list[str]) -> dict:
    """One lean ``grounding_projection_v1`` record whose rules are grounded in the
    named clauses, so its spans carry exactly those clauses' search keys."""

    rules = []
    for clause_id in clause_ids:
        rule = make_rule(f"AI-{provision_key}-{clause_id}", condition=AllCondition(all=[]))
        rule = rule.model_copy(
            update={
                "title": f"Rule in {provision_key}",
                "description": "A rule the fixture states.",
                "formulation": RuleFormulation(
                    canonical=CanonicalPolicy(source_text=f"The provision {provision_key} states {clause_id}.")
                ),
                "evidence": [
                    EvidenceReference(
                        document_version_id=_DV,
                        source_hash="h" * 16,
                        page=1,
                        section=f"section for {clause_id}",
                        clause_id=clause_id,
                        start_offset=0,
                        end_offset=10,
                    )
                ],
            }
        )
        rules.append(rule)
    return build_case_payload(
        policy_set_id="set-1",
        provision_id=provision_id,
        provision_key=provision_key,
        heading_path=[f"Heading of {provision_key}"],
        rules=rules,
    )


def _candidate(provision_id: str, provision_key: str, clause_ids: list[str]) -> dict:
    """A candidate provision as the retrieval core consumes it: its identity, how
    many rules it holds, the search keys its spans carry, and its lean payload."""

    payload = _payload_for(provision_id, provision_key, clause_ids)
    return {
        "provision_id": provision_id,
        "provision_key": provision_key,
        "heading_path": [f"Heading of {provision_key}"],
        "rules": len(clause_ids),
        "search_document_ids": {_clause_key(c) for c in clause_ids},
        "payload": payload,
    }


def _hit(clause_id: str, score: float) -> dict:
    """One search hit in the shape `AzureSearchClient.vector_search` returns."""

    return {"id": _clause_key(clause_id), "@search.score": score, "clause_id": clause_id}


def _ids(entries: list[dict]) -> set[str]:
    return {entry["provision_id"] for entry in entries}


# --- provision_search_ids: the retrieval join key is read from the payload ----


def test_provision_search_ids_reads_every_span_key() -> None:
    """The keys a provision can be retrieved under are exactly the search keys of
    the clauses its rules are grounded in — read from the payload's spans, the
    same join the index writes, so no second key format is invented."""

    payload = _payload_for("prov-1", "P1", ["C-a", "C-b"])

    keys = ai_case_project.provision_search_ids(payload)

    # A relationship, not a literal: the keys are precisely the fixture's own
    # clauses under the shared join-key function.
    assert keys == {_clause_key("C-a"), _clause_key("C-b")}


# --- select_retained: retrieval narrows, and the budget does the narrowing -----


def test_retrieval_retains_the_bearing_policy_and_discards_the_unrelated() -> None:
    """A question whose retrieved clauses fall in two policies retains those two
    and discards the third — and the discarded one carries the honest reason that
    it never surfaced, told apart from a policy that surfaced but ranked out."""

    bearing_a = _candidate("prov-a", "A", ["C-a1", "C-a2"])
    bearing_b = _candidate("prov-b", "B", ["C-b1"])
    unrelated = _candidate("prov-c", "C", ["C-c1"])
    candidates = [bearing_a, bearing_b, unrelated]

    # The retrieval surfaces A's and B's clauses; C's never appears.
    hits = [_hit("C-a1", 0.90), _hit("C-b1", 0.55), _hit("C-a2", 0.30)]

    selection = ai_case_project.select_retained(candidates, hits, budget=8)

    retained_ids = _ids(selection["retained"])
    discarded_ids = _ids(selection["discarded"])

    # The bearing policies are kept, the unrelated one is dropped.
    assert "prov-a" in retained_ids and "prov-b" in retained_ids
    assert "prov-c" in discarded_ids and "prov-c" not in retained_ids
    # Narrowing is honest: retained is a subset of everything considered.
    assert retained_ids | discarded_ids == {"prov-a", "prov-b", "prov-c"}
    assert retained_ids < ({"prov-a", "prov-b", "prov-c"})
    # A policy that never surfaced is discarded for that reason, with no score —
    # distinct from one that surfaced and ranked out.
    dropped = next(e for e in selection["discarded"] if e["provision_id"] == "prov-c")
    assert dropped["best_score"] is None
    assert dropped["discard_reason"] == ai_case_project.DISCARD_NO_MATCH
    # A retained policy carries the evidence it was kept on.
    kept = next(e for e in selection["retained"] if e["provision_id"] == "prov-a")
    assert kept["best_score"] is not None


def test_the_budget_narrows_even_when_more_policies_surface() -> None:
    """The clause budget is what narrows: a policy whose only clause ranks below
    the budget is discarded even though it surfaced, and says so — proving the
    budget is load-bearing, not decoration."""

    top = _candidate("prov-top", "TOP", ["C-top"])
    below_1 = _candidate("prov-x", "X", ["C-x"])
    below_2 = _candidate("prov-y", "Y", ["C-y"])
    candidates = [top, below_1, below_2]

    # All three surface, in this rank order; the budget keeps only the first.
    hits = [_hit("C-top", 0.9), _hit("C-x", 0.4), _hit("C-y", 0.2)]

    selection = ai_case_project.select_retained(candidates, hits, budget=1)

    assert _ids(selection["retained"]) == {"prov-top"}
    dropped = {e["provision_id"]: e for e in selection["discarded"]}
    assert set(dropped) == {"prov-x", "prov-y"}
    # They were seen (they carry a score) but ranked out of the budget — a
    # different fact from never having surfaced.
    for entry in dropped.values():
        assert entry["best_score"] is not None
        assert entry["discard_reason"] == ai_case_project.DISCARD_OUTSIDE_BUDGET


def test_every_candidate_appears_in_considered_so_narrowing_is_visible() -> None:
    """Constraint 10: a reviewer must always be able to see how much narrowing
    happened. Every candidate is in `considered`, each marked retained or not."""

    candidates = [
        _candidate("prov-a", "A", ["C-a"]),
        _candidate("prov-b", "B", ["C-b"]),
    ]
    hits = [_hit("C-a", 0.9)]

    selection = ai_case_project.select_retained(candidates, hits, budget=8)

    considered = selection["considered"]
    assert _ids(considered) == {"prov-a", "prov-b"}
    retained_flags = {e["provision_id"]: e["retained"] for e in considered}
    assert retained_flags["prov-a"] is True
    assert retained_flags["prov-b"] is False


# --- the multi-policy gather: fabrication check and per-policy citations --------


class _Settings:
    ai_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"
    search_enabled = True
    azure_search_authoring_index = "policy-authoring"


class _StubClient:
    """Stands in for the model, serving the classify call and the gather apart by
    the system prompt each is handed, and recording every message so a test can
    prove what was sent."""

    calls: list[dict[str, Any]] = []
    classify_reply: dict[str, Any] = {"intent": "informational", "reasoning": "asks after a value"}
    info_reply: dict[str, Any] = {
        "bears": True,
        "answer": "the answer",
        "cited_rule_ids": [],
        "declined": False,
        "note": "",
    }

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).calls.append({"messages": messages, "kwargs": kwargs})
        system = messages[0]["content"]
        is_classify = "sort one question" in system
        reply = type(self).classify_reply if is_classify else type(self).info_reply
        return json.dumps(reply, ensure_ascii=False)


@pytest.fixture()
def stub_model(monkeypatch: pytest.MonkeyPatch) -> type[_StubClient]:
    monkeypatch.setattr(ai_case_intent, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_intent, "AzureOpenAIClient", _StubClient)
    _StubClient.calls = []
    _StubClient.classify_reply = {"intent": "informational", "reasoning": "asks after a value"}
    _StubClient.info_reply = {
        "bears": True,
        "answer": "the answer",
        "cited_rule_ids": [],
        "declined": False,
        "note": "",
    }
    return _StubClient


def _record(provision_id: str, provision_key: str, clause_ids: list[str]) -> dict:
    payload = _payload_for(provision_id, provision_key, clause_ids)
    return {
        "policy": {
            "provision_id": provision_id,
            "provision_key": provision_key,
            "heading_path": [f"Heading of {provision_key}"],
        },
        "payload": payload,
    }


async def test_multi_policy_gather_drops_and_reports_fabricated_citations(
    stub_model: type[_StubClient],
) -> None:
    """A cited id that names no rule in any retained policy is a fabrication: it is
    dropped from the citations and reported in `grounding.fabricated_citations`, so
    the check is seen to refuse something (§ the validator that could not fail)."""

    record = _record("prov-a", "A", ["C-a"])
    real_id = record["payload"]["rules"][0]["rule_id"]
    stub_model.info_reply = {
        "bears": True,
        "answer": "drawn from the record",
        "cited_rule_ids": [real_id, "AI-not-a-real-rule"],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_informational_over_policies(
        [record], scenario="what does the policy provide?"
    )

    assert result["status"] == ai_case_intent.ANSWERED
    cited_ids = [c["rule_id"] for c in result["citations"]]
    assert real_id in cited_ids
    assert "AI-not-a-real-rule" not in cited_ids
    assert result["grounding"]["fabricated_citations"] == ["AI-not-a-real-rule"]


async def test_multi_policy_citations_name_the_policy_they_came_from(
    stub_model: type[_StubClient],
) -> None:
    """With several policies in play, a citation that names a rule but not its
    policy is not traceable. Each citation carries the identity of the policy whose
    rule it is."""

    record_a = _record("prov-a", "A", ["C-a"])
    record_b = _record("prov-b", "B", ["C-b"])
    rule_from_b = record_b["payload"]["rules"][0]["rule_id"]
    stub_model.info_reply = {
        "bears": True,
        "answer": "drawn from policy B",
        "cited_rule_ids": [rule_from_b],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_informational_over_policies(
        [record_a, record_b], scenario="what does the set provide?"
    )

    assert result["status"] == ai_case_intent.ANSWERED
    (citation,) = result["citations"]
    assert citation["rule_id"] == rule_from_b
    # The citation is traceable to the policy it was drawn from, not merely to a
    # rule id floating free of any policy.
    assert citation["policy"]["provision_id"] == "prov-b"


async def test_multi_policy_reuses_the_shared_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The intent is read by the one shared classifier, not a second copy. A
    determination returns the classification and gathers nothing — the caller runs
    the deciders it already has."""

    seen: dict[str, Any] = {}

    async def _spy_classify(scenario: str, *, tested_quantities: list[str] | None = None) -> dict:
        seen["scenario"] = scenario
        seen["tested_quantities"] = tested_quantities
        return {"intent": ai_case_intent.DECISION, "reasoning": "supplies a tested fact"}

    monkeypatch.setattr(ai_case_intent, "classify_case_intent", _spy_classify)

    record = _record("prov-a", "A", ["C-a"])
    result = await ai_case_intent.answer_case_over_policies(
        [record], scenario="a supplied fact, are we within the cap?"
    )

    assert seen, "the shared classifier was not called"
    assert result["intent"] == ai_case_intent.DECISION
    assert result["informational"] is None


# --- the orchestrator: scope, and the six honest retrieval states --------------


class _NamespacePolicySet:
    def __init__(self, id_: str, key: str) -> None:
        self.id = id_
        self.key = key


class _ExplodingSearchClient:
    """A search client that fails the test if it is ever constructed or queried —
    the load-bearing proof that a scope which must not retrieve never does."""

    def __init__(self, settings: Any) -> None:
        raise AssertionError("retrieval must not run for this scope")


@pytest.fixture()
def project_settings(monkeypatch: pytest.MonkeyPatch) -> _Settings:
    settings = _Settings()
    monkeypatch.setattr(ai_case_project, "get_settings", lambda: settings)
    return settings


async def _canned_evaluation(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
    return {
        "intent": ai_case_intent.INFORMATIONAL,
        "classification_reasoning": "canned",
        "informational": {
            "status": ai_case_intent.ANSWERED,
            "answer": "canned answer",
            "citations": [],
            "note": "",
            "grounding": {},
        },
        "reasoning_effort": reasoning_effort,
    }


async def test_single_policy_scope_bypasses_retrieval(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """A reviewer who has already chosen one policy sends its `provision_id`; that
    policy must not go through retrieval at all. The search client is rigged to
    explode if touched, so a bypass that isn't a bypass fails here."""

    payload = _payload_for("prov-a", "A", ["C-a"])

    async def _fake_payload(session: Any, provision_id: Any) -> dict:
        return payload

    calls: list[list[dict]] = []

    async def _spy_eval(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
        calls.append(records)
        return await _canned_evaluation(records, scenario=scenario, reasoning_effort=reasoning_effort)

    monkeypatch.setattr(ai_case_project, "case_payload_for_provision", _fake_payload)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _ExplodingSearchClient)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy_eval)

    result = await ai_case_project.answer_project_case(
        object(),
        policy_set=_NamespacePolicySet("set-1", "xx"),
        scenario="what does this one policy provide?",
        provision_id="prov-a",
    )

    assert result["scope"] == ai_case_project.SCOPE_SINGLE
    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_BYPASSED
    # The chosen policy was evaluated (retrieval did not gate it out).
    assert len(calls) == 1
    assert _ids([{"provision_id": r["policy"]["provision_id"]} for r in calls[0]]) == {"prov-a"}


def _project_scope(candidates: list[dict], excluded: list[dict] | None = None) -> dict:
    return {
        "candidates": candidates,
        "excluded": excluded or [],
        "document_ids": ["doc-1"],
    }


@pytest.fixture()
def one_candidate_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """A project with one testable policy, its scope-load and embedding stubbed so
    only the search behaviour under test varies between the state cases."""

    scope = _project_scope([_candidate("prov-a", "A", ["C-a"])])

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return scope

    class _StubEmbedClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def embed(self, inputs: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in inputs]

    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _StubEmbedClient)


async def _run_project(**overrides: Any) -> dict:
    return await ai_case_project.answer_project_case(
        object(),
        policy_set=_NamespacePolicySet("set-1", "xx"),
        scenario=overrides.get("scenario", "a project question"),
    )


async def test_unavailable_is_when_search_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    project_settings.search_enabled = False
    evaluated: list[Any] = []

    async def _spy_eval(records: list[dict], **kwargs: Any) -> dict:
        evaluated.append(records)
        return await _canned_evaluation(records, scenario="x")

    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy_eval)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_UNAVAILABLE
    assert result["evaluation"] is None
    assert not evaluated, "nothing may be evaluated when retrieval cannot run"


async def test_failed_is_when_the_search_call_raises(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _RaisingSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            raise RuntimeError("search backend is down")

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _RaisingSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert result["evaluation"] is None


async def test_index_empty_is_when_the_project_has_no_indexed_clauses(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _EmptyIndexSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return []

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return []  # nothing indexed for this project

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _EmptyIndexSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_EMPTY
    assert result["evaluation"] is None


async def test_no_match_is_when_search_ran_but_nothing_retained(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _NoMatchSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            # A hit that belongs to no candidate provision's clauses.
            return [{"id": _clause_key("C-unrelated"), "@search.score": 0.4}]

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return ["something"]  # the project IS indexed

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _NoMatchSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_MATCH
    assert result["evaluation"] is None


async def test_narrowed_is_when_a_policy_is_retained_and_only_then_is_it_evaluated(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _MatchingSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [{"id": _clause_key("C-a"), "@search.score": 0.7}]

    evaluated: list[list[dict]] = []

    async def _spy_eval(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
        evaluated.append(records)
        return await _canned_evaluation(records, scenario=scenario, reasoning_effort=reasoning_effort)

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _MatchingSearchClient)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy_eval)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NARROWED
    assert result["evaluation"] is not None
    # Only the retained policy reached the evaluator.
    assert len(evaluated) == 1
    assert _ids([{"provision_id": r["policy"]["provision_id"]} for r in evaluated[0]]) == {"prov-a"}


async def test_empty_project_is_its_own_state(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """A project with no testable policy is not the same as one where retrieval
    matched nothing: there was nothing to retrieve against. Distinct state, and no
    search call is made."""

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return _project_scope([], excluded=[
            {"provision_id": "prov-z", "provision_key": "Z", "heading_path": ["Z"], "reason": "no_live_rules"}
        ])

    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _ExplodingSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_EMPTY_SET
    assert result["evaluation"] is None


def test_the_six_retrieval_states_are_distinct() -> None:
    """Absent, empty, matched-nothing, unavailable, failed, and bypassed are six
    different facts and must not collapse into one another (constraint 5)."""

    states = {
        ai_case_project.RETRIEVAL_NARROWED,
        ai_case_project.RETRIEVAL_NO_MATCH,
        ai_case_project.RETRIEVAL_INDEX_EMPTY,
        ai_case_project.RETRIEVAL_UNAVAILABLE,
        ai_case_project.RETRIEVAL_FAILED,
        ai_case_project.RETRIEVAL_EMPTY_SET,
        ai_case_project.RETRIEVAL_BYPASSED,
    }
    # Seven named states, none equal to another.
    assert len(states) == 7
