"""A case put to a *project* is answered against the published policies retrieval
keeps, never against the whole set, and what retrieval did is reported so a
reviewer can see the narrowing.

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

"Retrieval narrowed to a subset", "retrieval matched nothing", "the project has
no published version", "the policy index is absent", "the policy index is stale
or empty", "search is not configured", "the search call failed", and "the active
published version has no policy rules" are different facts about a search
(constraint 5). The one thing forbidden is degrading any of them silently to
"answer against all" (constraint 10). The tests below assert the states read
differently and that only a genuine narrowing reaches the evaluator.

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
from policy_platform.infrastructure.search.policy_index import policy_document_id
from tests.fixtures.factories import make_rule

pytestmark = pytest.mark.anyio


#: A stand-in document version id. The retrieval join key is
#: ``{document_version_id}_{clause_id}`` (`clause_search_document_id`), the same
#: key the search index writes and the projection's spans carry, so a fixture can
#: predict the id a clause would surface under without touching Azure.
_DV = "22222222-2222-2222-2222-222222222222"
_PV = "33333333-3333-4333-8333-333333333333"


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
        "policy_version_id": _PV,
        "search_document_id": policy_document_id(policy_version_id=_PV, provision_key=provision_key),
        "payload": payload,
    }


def _hit(clause_id: str, score: float) -> dict:
    """One legacy clause search hit, for the span-key helper tests."""

    return {"id": _clause_key(clause_id), "@search.score": score, "clause_id": clause_id}


def _policy_hit(provision_key: str, score: float, *, version: str = _PV) -> dict:
    """One policy-index search hit in the shape `AzureSearchClient.vector_search` returns."""

    return {
        "id": policy_document_id(policy_version_id=version, provision_key=provision_key),
        "@search.score": score,
        "policy_id": provision_key,
        "document_version": version,
    }


def _ids(entries: list[dict]) -> set[str]:
    return {entry["provision_id"] for entry in entries}


# --- published policy identity: the retrieval join key ------------------------


def test_published_policy_search_id_uses_version_and_policy_identity() -> None:
    payload = _payload_for("prov-1", "P1", ["C-a"])
    payload["envelope"]["policy_version_id"] = _PV

    key = ai_case_project.published_policy_search_id(payload)

    assert key == policy_document_id(policy_version_id=_PV, provision_key="P1")


# --- select_retained: retrieval narrows, and the budget does the narrowing -----


def test_retrieval_retains_the_bearing_policy_and_discards_the_unrelated() -> None:
    """A question whose retrieved policy documents name two policies retains those two
    and discards the third — and the discarded one carries the honest reason that
    it never surfaced, told apart from a policy that surfaced but ranked out."""

    bearing_a = _candidate("prov-a", "A", ["C-a1", "C-a2"])
    bearing_b = _candidate("prov-b", "B", ["C-b1"])
    unrelated = _candidate("prov-c", "C", ["C-c1"])
    candidates = [bearing_a, bearing_b, unrelated]

    # The retrieval surfaces A and B from the policy index; C never appears.
    hits = [_policy_hit("A", 0.90), _policy_hit("B", 0.55)]

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
    """The policy budget is what narrows: a policy whose document ranks below
    the budget is discarded even though it surfaced, and says so — proving the
    budget is load-bearing, not decoration."""

    top = _candidate("prov-top", "TOP", ["C-top"])
    below_1 = _candidate("prov-x", "X", ["C-x"])
    below_2 = _candidate("prov-y", "Y", ["C-y"])
    candidates = [top, below_1, below_2]

    # All three surface, in this rank order; the budget keeps only the first.
    hits = [_policy_hit("TOP", 0.9), _policy_hit("X", 0.4), _policy_hit("Y", 0.2)]

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
    hits = [_policy_hit("A", 0.9)]

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
    decision_reply: dict[str, Any] = {
        "status": "answered",
        "answer": "the decision",
        "verdict": "compliant",
        "cited_rule_ids": [],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        type(self).calls.append({"messages": messages, "kwargs": kwargs})
        system = messages[0]["content"]
        is_classify = "sort one question" in system
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
    _StubClient.decision_reply = {
        "status": "answered",
        "answer": "the decision",
        "verdict": "compliant",
        "cited_rule_ids": [],
        "missing_required_facts": [],
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


async def test_multi_policy_reuses_the_shared_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """The intent is read by the one shared classifier, not a second copy. A
    determination then gathers once over the retained records."""

    seen: dict[str, Any] = {}

    async def _spy_classify(scenario: str, *, tested_quantities: list[str] | None = None) -> dict:
        seen["scenario"] = scenario
        seen["tested_quantities"] = tested_quantities
        return {"intent": ai_case_intent.DECISION, "reasoning": "supplies a tested fact"}

    monkeypatch.setattr(ai_case_intent, "classify_case_intent", _spy_classify)
    decision_calls: list[list[dict]] = []

    async def _spy_decision(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
        decision_calls.append(records)
        return {
            "status": ai_case_intent.ANSWERED,
            "verdict": "compliant",
            "answer": "grounded decision",
            "missing_required_facts": [],
            "citations": [],
            "note": "",
            "grounding": {},
        }

    monkeypatch.setattr(ai_case_intent, "answer_decision_over_policies", _spy_decision)

    record = _record("prov-a", "A", ["C-a"])
    result = await ai_case_intent.answer_case_over_policies(
        [record], scenario="a supplied fact, are we within the cap?"
    )

    assert seen, "the shared classifier was not called"
    assert result["intent"] == ai_case_intent.DECISION
    assert result["informational"] is None
    assert result["decision"]["status"] == ai_case_intent.ANSWERED
    assert len(decision_calls) == 1


async def test_multi_policy_decision_citations_name_the_policy_they_came_from(
    stub_model: type[_StubClient],
) -> None:
    """A project-scope decision is one gather over retained records, with
    per-policy citations."""

    record_a = _record("prov-a", "A", ["C-a"])
    record_b = _record("prov-b", "B", ["C-b"])
    rule_from_b = record_b["payload"]["rules"][0]["rule_id"]
    stub_model.decision_reply = {
        "status": "answered",
        "answer": "Policy B settles the supplied case.",
        "verdict": "compliant",
        "cited_rule_ids": [rule_from_b],
        "missing_required_facts": [],
        "declined": False,
        "note": "",
    }

    result = await ai_case_intent.answer_decision_over_policies(
        [record_a, record_b], scenario="a supplied fact, is it compliant?"
    )

    assert result["status"] == ai_case_intent.ANSWERED
    assert result["citations"][0]["rule_id"] == rule_from_b
    assert result["citations"][0]["policy"]["provision_id"] == "prov-b"
    gathers = [c for c in stub_model.calls if "asked for a judgement" in c["messages"][0]["content"]]
    assert len(gathers) == 1


# --- the orchestrator: scope, and the honest retrieval states ------------------


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


class _NamespaceProvision:
    """A provision as the bypass reads it: identity only, no rules of its own."""

    def __init__(self, provision_id: str, provision_key: str) -> None:
        self.id = provision_id
        self.provision_key = provision_key
        self.heading_path_json = [provision_key]


def _bypass_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict | None,
    has_version: bool,
    provision_key: str = "A",
) -> list[list[dict]]:
    """Stub the bypass's three collaborators and spy on what got evaluated."""

    async def _fake_provision(session: Any, *, policy_set: Any, provision_id: Any) -> Any:
        return _NamespaceProvision(str(provision_id), provision_key)

    async def _fake_version(session: Any, policy_set_id: Any) -> Any:
        return object() if has_version else None

    async def _fake_published(session: Any, policy_set_id: Any, key: str) -> dict | None:
        return payload

    calls: list[list[dict]] = []

    async def _spy_eval(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
        calls.append(records)
        return await _canned_evaluation(records, scenario=scenario, reasoning_effort=reasoning_effort)

    monkeypatch.setattr(ai_case_project, "_provision_in_project", _fake_provision)
    monkeypatch.setattr(ai_case_project, "active_version_for_policy_set", _fake_version)
    monkeypatch.setattr(ai_case_project, "published_case_payload_for_policy", _fake_published)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _ExplodingSearchClient)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy_eval)
    return calls


async def test_single_policy_scope_bypasses_retrieval(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """A reviewer who has already chosen one policy sends its `provision_id`; that
    policy must not go through retrieval at all. The search client is rigged to
    explode if touched, so a bypass that isn't a bypass fails here."""

    payload = _payload_for("prov-a", "A", ["C-a"])
    calls = _bypass_stubs(monkeypatch, payload=payload, has_version=True)

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


async def test_single_policy_scope_refuses_when_the_project_has_no_published_version(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """Naming a policy must not smuggle the draft set past the published scope.

    The project scope answers from the active approved version; if there is none,
    the single scope has nothing approved to answer from either, and says so
    rather than quietly falling back to candidate rules."""

    calls = _bypass_stubs(monkeypatch, payload=None, has_version=False)

    result = await ai_case_project.answer_project_case(
        object(),
        policy_set=_NamespacePolicySet("set-1", "xx"),
        scenario="was this compliant?",
        provision_id="prov-a",
    )

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_PUBLISHED_VERSION
    assert result["evaluation"] is None
    assert calls == []


async def test_single_policy_scope_tells_unpublished_apart_from_unpublishable(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """A project that publishes, and a policy of it that does not, is its own state.

    Reporting this as "the project has nothing published" would be false, and
    answering it from drafts would be worse — the reviewer would receive a draft
    answer for a question they asked of the published set."""

    calls = _bypass_stubs(monkeypatch, payload=None, has_version=True)

    result = await ai_case_project.answer_project_case(
        object(),
        policy_set=_NamespacePolicySet("set-1", "xx"),
        scenario="was this compliant?",
        provision_id="prov-a",
    )

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_POLICY_NOT_PUBLISHED
    assert result["evaluation"] is None
    assert calls == []


def _project_scope(candidates: list[dict], excluded: list[dict] | None = None) -> dict:
    return {
        "has_published_version": True,
        "active_version_id": _PV,
        "active_version_number": 2,
        "candidates": candidates,
        "excluded": excluded or [],
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

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            raise RuntimeError("search backend is down")

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _RaisingSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert result["evaluation"] is None


async def test_index_empty_is_when_the_project_policy_index_has_no_documents(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _EmptyIndexSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return []

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return []  # nothing indexed for this project

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _EmptyIndexSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_EMPTY
    assert result["evaluation"] is None


async def test_index_not_built_is_when_the_project_index_does_not_exist(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _MissingIndexSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return False

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            raise AssertionError("an unbuilt index must not be searched")

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _MissingIndexSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_NOT_BUILT
    assert result["evaluation"] is None


async def test_index_stale_is_when_only_superseded_policy_documents_exist(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _StaleSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_policy_hit("A", 0.7, version="44444444-4444-4444-8444-444444444444")]

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _StaleSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_STALE
    assert result["evaluation"] is None


async def test_no_match_is_when_search_ran_but_nothing_retained(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _NoMatchSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return []

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return ["something"]  # the active version IS indexed

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _NoMatchSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_MATCH
    assert result["evaluation"] is None


async def test_current_version_hits_outside_the_active_payload_are_stale(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    class _OrphanHitSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_policy_hit("unrelated", 0.4)]

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _OrphanHitSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_STALE
    assert result["evaluation"] is None


async def test_narrowed_is_when_a_policy_is_retained_and_only_then_is_it_evaluated(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    """Narrowing means some policies were set aside, and only survivors evaluated.

    Two candidates, one of which surfaces, so the discard is real. The status is
    reserved for that case: see the companion test below for a project small
    enough that nothing can be set aside.
    """

    two_candidates = _project_scope(
        [_candidate("prov-a", "A", ["C-a"]), _candidate("prov-b", "B", ["C-b"])]
    )

    async def _load_two(session: Any, policy_set_id: Any) -> dict:
        return two_candidates

    class _MatchingSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_policy_hit("A", 0.7)]

    evaluated: list[list[dict]] = []

    async def _spy_eval(records: list[dict], *, scenario: str, reasoning_effort: str = "medium") -> dict:
        evaluated.append(records)
        return await _canned_evaluation(records, scenario=scenario, reasoning_effort=reasoning_effort)

    # The fixture supplies the embedding stub; only the candidate set is widened.
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load_two)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _MatchingSearchClient)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy_eval)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NARROWED
    assert result["retrieval"]["policies_discarded"] == 1
    assert result["evaluation"] is not None
    # Only the retained policy reached the evaluator.
    assert len(evaluated) == 1
    assert _ids([{"provision_id": r["policy"]["provision_id"]} for r in evaluated[0]]) == {"prov-a"}


async def test_a_project_within_the_budget_is_not_reported_as_narrowed(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings, one_candidate_project: None
) -> None:
    """Discarding nothing is not narrowing, and must not be reported as it.

    A project whose published policies fit inside the retention budget has every
    one of them evaluated. Calling that ``narrowed`` tells a reviewer that search
    chose these policies as the matching ones, when search chose nothing. A real
    project reported two considered, two retained and none discarded, under a
    banner claiming the rest had been discarded — while the answer itself
    correctly found that neither policy bore on the question.

    The evaluation still runs and is still present: this is the same answer with
    an honest account of how its inputs were chosen.
    """

    class _MatchingSearchClient:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_policy_hit("A", 0.7)]

    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _MatchingSearchClient)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _canned_evaluation)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NOT_NARROWED
    assert result["retrieval"]["policies_discarded"] == 0
    assert result["retrieval"]["policies_retained"] == result["retrieval"]["policies_considered"]
    # The answer is not weakened by the honesty: the policy was still evaluated.
    assert result["evaluation"] is not None
    assert "not selected" in result["retrieval"]["reason"]


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


async def test_no_published_version_is_its_own_state(
    monkeypatch: pytest.MonkeyPatch, project_settings: _Settings
) -> None:
    """A project with draft rules but no active approved version has no published
    project scope yet. That must not be reported as a search no-match."""

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return {
            "has_published_version": False,
            "active_version_id": None,
            "active_version_number": None,
            "candidates": [],
            "excluded": [],
        }

    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _ExplodingSearchClient)

    result = await _run_project()

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_PUBLISHED_VERSION
    assert result["evaluation"] is None
    assert result["retrieval"]["status"] != ai_case_project.RETRIEVAL_NO_MATCH


def test_the_retrieval_states_are_distinct() -> None:
    """Absent, empty, matched-nothing, unavailable, failed, and bypassed are
    different facts and must not collapse into one another (constraint 5)."""

    states = {
        ai_case_project.RETRIEVAL_NARROWED,
        ai_case_project.RETRIEVAL_NOT_NARROWED,
        ai_case_project.RETRIEVAL_NO_MATCH,
        ai_case_project.RETRIEVAL_INDEX_EMPTY,
        ai_case_project.RETRIEVAL_NO_PUBLISHED_VERSION,
        ai_case_project.RETRIEVAL_INDEX_NOT_BUILT,
        ai_case_project.RETRIEVAL_INDEX_STALE,
        ai_case_project.RETRIEVAL_UNAVAILABLE,
        ai_case_project.RETRIEVAL_FAILED,
        ai_case_project.RETRIEVAL_EMPTY_SET,
        ai_case_project.RETRIEVAL_BYPASSED,
        ai_case_project.RETRIEVAL_POLICY_NOT_PUBLISHED,
    }
    # Twelve named states, none equal to another.
    assert len(states) == 12

