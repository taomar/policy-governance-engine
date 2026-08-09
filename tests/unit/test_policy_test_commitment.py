from policy_platform.infrastructure.policy_test_commitment import (
    build_expectation_snapshot,
    expectation_hash,
)


def test_expectation_commitment_is_stable_across_fact_key_order():
    first = build_expectation_snapshot(
        scenario_text="Employee submits a small claim",
        input_facts={"amount": 50, "country": "US"},
        evaluation_timestamp=None,
        expected_overall_status="SATISFIED",
        expected_rule_id="R1",
        expected_rule_status="SATISFIED",
        expected_missing_facts=None,
    )
    second = build_expectation_snapshot(
        scenario_text="Employee submits a small claim",
        input_facts={"country": "US", "amount": 50},
        evaluation_timestamp=None,
        expected_overall_status="SATISFIED",
        expected_rule_id="R1",
        expected_rule_status="SATISFIED",
        expected_missing_facts=None,
    )

    assert expectation_hash(first) == expectation_hash(second)


def test_expectation_commitment_changes_when_expected_result_changes():
    base = build_expectation_snapshot(
        scenario_text="Employee submits a small claim",
        input_facts={"amount": 50},
        evaluation_timestamp=None,
        expected_overall_status="SATISFIED",
        expected_rule_id="R1",
        expected_rule_status="SATISFIED",
        expected_missing_facts=None,
    )
    changed = {**base, "expected_rule_status": "NOT_SATISFIED"}

    assert expectation_hash(base) != expectation_hash(changed)
