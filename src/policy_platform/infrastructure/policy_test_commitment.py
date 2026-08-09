"""Stable commitments for blind PolicyTest expectations."""
from __future__ import annotations

from typing import Any

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.domain.models import PolicyTest


def build_expectation_snapshot(
    *,
    scenario_text: str,
    input_facts: dict,
    evaluation_timestamp: Any,
    expected_overall_status: str,
    expected_rule_id: str | None,
    expected_rule_status: str | None,
    expected_missing_facts: list | None,
) -> dict:
    return {
        "scenario_text": scenario_text,
        "input_facts": input_facts,
        "evaluation_timestamp": evaluation_timestamp.isoformat() if evaluation_timestamp else None,
        "expected_overall_status": expected_overall_status,
        "expected_rule_id": expected_rule_id,
        "expected_rule_status": expected_rule_status,
        "expected_missing_facts": expected_missing_facts,
    }


def expectation_snapshot_for_test(test: PolicyTest) -> dict:
    return build_expectation_snapshot(
        scenario_text=test.scenario_text,
        input_facts=test.input_facts_json or {},
        evaluation_timestamp=test.evaluation_timestamp_override,
        expected_overall_status=test.expected_overall_status,
        expected_rule_id=test.expected_rule_id,
        expected_rule_status=test.expected_rule_status,
        expected_missing_facts=test.expected_missing_facts_json,
    )


def expectation_hash(snapshot: dict) -> str:
    return canonical_hash(snapshot)
