"""Decision Light is a compact projection, never a second decision path."""
from __future__ import annotations

from datetime import datetime, timezone

from policy_platform.application.policy_case_decision import compact_decision_receipt
from policy_platform.contracts.case_decision import CaseDecisionEnvelope, CaseDecisionEnvelopeV2


def _common() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "decision_id": "decision-1",
        "correlation_id": "correlation-1",
        "idempotency_key": "key-1",
        "policy_set": {"id": "set-1", "key": "set-key", "name": "Policy set"},
        "active_version": {"version_id": "version-1", "version_number": 3},
        "caller": {
            "principal_identity": "agent-1",
            "principal_role": "viewer",
            "authentication_source": "subscription-key",
        },
        "request": {
            "scenario": "Is this entitlement available?",
            "scenario_hash": "a" * 64,
            "scope": "project",
            "reasoning_effort_requested": "medium",
            "received_at": now,
        },
        "retrieval": {
            "status": "narrowed",
            "method": "direct_policy_rrf_elbow_rule_rescue_v1",
            "policies_retained": 1,
            "rule_rescued_policies": 0,
            "reason": "one policy retained",
        },
        "trace": {
            "prompt_version": "prompt-v1",
            "model_deployment": "model-1",
            "stage_latency_ms": {"policy_search": 125, "gather_wall": 900},
            "token_usage": {
                "calls": 2,
                "calls_without_usage": 0,
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "reasoning_tokens": 10,
            },
        },
        "decision_hash": "b" * 64,
        "hash_basis": "case_decision_v2_lang_verification",
        "receipt_url": "/api/policy-decisions/decision-1",
        "decided_at": now,
        "latency_ms": 1200,
    }


def _citation(*, serves: list[str] | None = None) -> dict:
    citation = {
        "rule_id": "R-ONE",
        "policy": {
            "provision_id": "provision-1",
            "provision_key": "entitlement",
            "heading_path": ["Entitlement"],
        },
        "source": {
            "state": "quoted",
            "text": "The record states the entitlement.",
            "page": 4,
            "section": "Entitlement",
        },
    }
    if serves is not None:
        citation["serves"] = serves
    return citation


def test_v2_light_response_keeps_only_essential_decision_fields() -> None:
    data = {
        **_common(),
        "schema_version": "case_decision_v2",
        "receipt_status": "completed",
        "language": None,
        "asked": {
            "information_requested": True,
            "verdict_requested": True,
            "classifier_version": "classifier-v2",
        },
        "outcome": {"information": "answered", "verdict": "answered"},
        "information": {
            "status": "answered",
            "answered": True,
            "answer": "The policy states an entitlement.",
            "citations": [_citation()],
        },
        "verdict": {
            "status": "answered",
            "reached": True,
            "decision": "Entitled under the stated rate",
            "explanation": "The supplied duration produces the requested amount.",
            "verification_requirements": [
                {
                    "fact": "recorded-balance",
                    "label": "Recorded balance",
                    "why_needed": "Confirm before acting.",
                    "required_by_rule_ids": ["R-ONE"],
                }
            ],
            "citations": [_citation()],
            "grounding": {
                "plan_profile": "case-plan-v3",
                "selector_catalogue_version": "case-selectors-v1",
            },
        },
        "considered": [{"provision_key": "unused-extra-policy", "retained": False}],
        "excluded": [{"provision_key": "another-extra-policy"}],
        "citations": [_citation(serves=["information", "verdict"])],
        "size": {"combined_chars": 50000, "budget_chars": 200000, "oversize": False},
    }
    full = CaseDecisionEnvelopeV2.model_validate(data)

    light = compact_decision_receipt(full).model_dump(mode="json")

    assert set(light) == {
        "schema_version",
        "response_type",
        "decision_id",
        "correlation_id",
        "idempotency_key",
        "policy_set",
        "active_version",
        "request",
        "asked",
        "outcome",
        "information",
        "verdict",
        "retrieval",
        "policies",
        "citations",
        "trace",
        "decision_hash",
        "hash_basis",
        "receipt_url",
        "latency_ms",
    }
    assert light["schema_version"] == "case_decision_light_v1"
    assert light["response_type"] == "mixed"
    assert light["verdict"]["decision"] == "Entitled under the stated rate"
    assert light["verdict"]["verification_requirements"][0]["fact"] == "recorded-balance"
    assert [policy["provision_key"] for policy in light["policies"]] == ["entitlement"]
    assert light["citations"][0]["serves"] == ["information", "verdict"]
    assert light["trace"]["plan_profile"] == "case-plan-v3"
    assert light["trace"]["stage_latency_ms"] == {"policy_search": 125, "gather_wall": 900}
    assert light["trace"]["token_usage"]["total_tokens"] == 150
    assert light["latency_ms"] == 1200
    assert light["retrieval"]["method"] == "direct_policy_rrf_elbow_rule_rescue_v1"
    assert light["retrieval"]["policies_retained"] == 1
    assert light["decision_hash"] == full.decision_hash
    assert "considered" not in light
    assert "excluded" not in light
    assert "size" not in light
    assert "language" not in light
    assert "grounding" not in light["verdict"]


def test_v1_replay_can_be_projected_without_rewriting_the_stored_receipt() -> None:
    full = CaseDecisionEnvelope.model_validate(
        {
            **_common(),
            "schema_version": "case_decision_v1",
            "hash_basis": "case_decision_v1",
            "decision_status": "answered",
            "decision": {
                "intent": "decision",
                "status": "answered",
                "verdict": "allowed",
                "explanation": "The rule allows it.",
                "decider_route": "decision",
            },
            "citations": [_citation()],
        }
    )

    light = compact_decision_receipt(full)

    assert light.schema_version == "case_decision_light_v1"
    assert light.response_type == "decision"
    assert light.verdict is not None and light.verdict.decision == "allowed"
    assert light.outcome.verdict == "answered"
    assert light.outcome.information == "not_requested"
    assert light.decision_hash == full.decision_hash
    assert light.receipt_url == full.receipt_url
