from policy_platform.infrastructure.policy_tests.ai_test_proposal import _validate_proposed_test


def _proposal(kind: str, timestamp: str | None) -> dict:
    return {
        "name": "neutral scenario",
        "scenario_text": "A device has three repairs.",
        "description": "Boundary scenario",
        "test_kind": kind,
        "input_facts": {"repairs": 3},
        "evaluation_timestamp": timestamp,
        "expected_overall_status": "SATISFIED",
        "expected_rule_id": "R1",
        "expected_rule_status": "SATISFIED",
    }


def test_non_effective_date_proposal_discards_timestamp_override():
    payload, error = _validate_proposed_test(_proposal("boundary", "2026-08-08"), {"R1"})

    assert error is None
    assert payload is not None
    assert payload["evaluation_timestamp_override"] is None


def test_effective_date_proposal_normalizes_date_to_utc():
    payload, error = _validate_proposed_test(_proposal("effective_date", "2026-08-08"), {"R1"})

    assert error is None
    assert payload is not None
    assert payload["evaluation_timestamp_override"].isoformat() == "2026-08-08T00:00:00+00:00"
