"""The light external mode returns selected policy records and no decision."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from policy_platform.application import policy_case_decision
from policy_platform.infrastructure.assistants import ai_case_project
from tests.fixtures.language_boundary import install_language_boundary

pytestmark = pytest.mark.anyio


class _PolicySet:
    id = "11111111-1111-4111-8111-111111111111"
    key = "published-policy"
    name = "Published policy"


async def test_light_mode_crosses_the_same_boundary_and_returns_only_selected_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = "السؤال كما كتبه المتصل"
    processed = "the caller's scenario in English"
    boundary = install_language_boundary(
        monkeypatch,
        source_language="ar",
        english=processed,
    )
    monkeypatch.setattr(
        policy_case_decision,
        "get_settings",
        lambda: SimpleNamespace(ai_enabled=True),
    )
    received: list[str] = []

    async def _retrieve(session, *, policy_set, scenario, with_context):
        received.append(scenario)
        assert with_context is True
        return ai_case_project.ProjectPolicyRetrieval(
            response={
                "scope": "project",
                "policy_set_key": policy_set.key,
                "retrieval": {
                    "status": "narrowed",
                    "method": ai_case_project.RETRIEVAL_METHOD,
                    "policies_considered": 2,
                    "policies_retained": 1,
                    "policies_discarded": 1,
                    "projection_profile": "policy-english-projection-v1",
                    "projection_ready": True,
                },
                "considered": [],
                "excluded": [],
                "evaluation": None,
                "size": {
                    "combined_chars": 321,
                    "budget_chars": ai_case_project.PAYLOAD_BUDGET_CHARS,
                    "oversize": False,
                },
                "policies": [
                    {
                        "policy": {
                            "provision_id": "22222222-2222-4222-8222-222222222222",
                            "provision_key": "leave",
                            "heading_path": ["Leave"],
                        },
                        "match": {"best_rank": 0, "best_score": 0.91},
                        "payload": {
                            "projection": "grounding_projection_v1",
                            "envelope": {"provision_key": "leave"},
                            "rules": [{"rule_id": "rule-leave"}],
                        },
                    }
                ],
            },
            context={
                "policy_version_id": "33333333-3333-4333-8333-333333333333",
                "version_number": 4,
            },
        )

    monkeypatch.setattr(ai_case_project, "retrieve_project_policies", _retrieve)

    envelope = await policy_case_decision.retrieve_project_policies(
        object(),
        policy_set=_PolicySet(),
        scenario=original,
        correlation_id="correlation-1",
    )
    wire = envelope.model_dump(mode="json")

    assert boundary.scenarios == [original]
    assert received == [processed]
    assert wire["schema_version"] == "policy_retrieval_v1"
    assert wire["query"]["scenario"] == original
    assert wire["language"]["processing_scenario"] == processed
    assert wire["retrieval"]["policies_retained"] == 1
    assert wire["policies"][0]["policy"]["provision_key"] == "leave"
    assert wire["policies"][0]["payload"]["rules"] == [{"rule_id": "rule-leave"}]
    assert wire["token_usage"] == {
        "calls": 0,
        "calls_without_usage": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
    }
    assert wire["latency_ms"] >= 0
    assert set(wire).isdisjoint(
        {"decision_id", "receipt_url", "asked", "outcome", "information", "verdict", "citations"}
    )
    assert boundary.prose == [], "policy JSON must never enter the prose renderer"


async def test_light_mode_refuses_an_oversized_scenario_before_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy_case_decision,
        "get_settings",
        lambda: SimpleNamespace(ai_enabled=True),
    )

    with pytest.raises(policy_case_decision.CaseDecisionError) as caught:
        await policy_case_decision.retrieve_project_policies(
            object(),
            policy_set=_PolicySet(),
            scenario="x" * 20_001,
            correlation_id="correlation-2",
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "scenario_too_long"
