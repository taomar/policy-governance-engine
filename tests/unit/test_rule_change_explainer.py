"""Tests for the deterministic half of the change explainer.

Only `_diff_fields` is exercised here: it is the part that must be exactly
right, because it is what a reviewer acts on. The narrative is an LLM call and
is deliberately not asserted — it is decoration over this diff, and the module
is built so that its absence changes nothing about the result.
"""
from __future__ import annotations

from policy_platform.infrastructure.rule_change_explainer import (
    PROSE_FIELDS,
    _diff_fields,
)
from policy_platform.infrastructure.rule_delta import SEMANTIC_FIELDS


def test_identical_payloads_produce_no_diff():
    payload = {"rule_type": "obligation", "priority": 10, "effect": {"kind": "deny"}}
    assert _diff_fields(payload, payload, SEMANTIC_FIELDS) == []


def test_reports_only_the_field_that_changed():
    before = {"rule_type": "obligation", "priority": 10}
    after = {"rule_type": "obligation", "priority": 50}

    diff = _diff_fields(before, after, SEMANTIC_FIELDS)

    assert diff == [{"field": "priority", "before": 10, "after": 50}]


def test_detects_nested_condition_change():
    before = {"condition": {"fact": "tenure_months", "op": ">=", "value": 12}}
    after = {"condition": {"fact": "tenure_months", "op": ">=", "value": 24}}

    diff = _diff_fields(before, after, SEMANTIC_FIELDS)

    assert len(diff) == 1
    assert diff[0]["field"] == "condition"
    assert diff[0]["before"]["value"] == 12
    assert diff[0]["after"]["value"] == 24


def test_prose_changes_are_not_reported_as_semantic():
    """The model rewords freely between runs. If a retitle showed up in the
    semantic diff, every unchanged rule would look like a behavioural change."""
    before = {"title": "Annual leave", "description": "old wording", "priority": 10}
    after = {"title": "Annual Leave Entitlement", "description": "new wording", "priority": 10}

    assert _diff_fields(before, after, SEMANTIC_FIELDS) == []
    assert len(_diff_fields(before, after, PROSE_FIELDS)) == 2


def test_field_added_where_previously_absent_is_a_change():
    """A newly-populated exceptions list narrows who the rule applies to. Absent
    and empty are not the same thing and must not be treated as equal."""
    before = {"rule_type": "obligation"}
    after = {"rule_type": "obligation", "exceptions": ["probation"]}

    diff = _diff_fields(before, after, SEMANTIC_FIELDS)

    assert diff == [{"field": "exceptions", "before": None, "after": ["probation"]}]


def test_field_removed_is_a_change():
    before = {"rule_type": "obligation", "exceptions": ["probation"]}
    after = {"rule_type": "obligation"}

    diff = _diff_fields(before, after, SEMANTIC_FIELDS)

    assert diff == [{"field": "exceptions", "before": ["probation"], "after": None}]


def test_diff_order_follows_the_field_list_not_dict_order():
    """A reviewer comparing two rules should not see the reasons reshuffle
    between page loads, so the order must come from SEMANTIC_FIELDS."""
    before = {"priority": 1, "rule_type": "obligation", "effect": {"kind": "allow"}}
    after = {"priority": 2, "rule_type": "permission", "effect": {"kind": "deny"}}

    fields = [d["field"] for d in _diff_fields(before, after, SEMANTIC_FIELDS)]

    assert fields == [f for f in SEMANTIC_FIELDS if f in fields]
    assert fields.index("rule_type") < fields.index("effect") < fields.index("priority")


def test_untracked_fields_are_ignored():
    """rule_id and effective_from are regenerated every run. Including them
    would flag every rule in the document as changed."""
    before = {"rule_id": "AI-aaaaaaaaaa", "effective_from": "2024-01-01", "priority": 10}
    after = {"rule_id": "AI-bbbbbbbbbb", "effective_from": "2025-06-01", "priority": 10}

    assert _diff_fields(before, after, SEMANTIC_FIELDS) == []
    assert _diff_fields(before, after, PROSE_FIELDS) == []


def test_empty_payloads_are_handled():
    assert _diff_fields({}, {}, SEMANTIC_FIELDS) == []
