"""Relationship anchors describe a rule by the facts it actually declares.

An anchor carries `fact_paths` so discovery can notice that two rules read the
same quantity -- a shared fact path is strong evidence they answer one
question. The path is the identifier the rule's condition names and the rule
declares back: `RequiredFact.name`, the same string `condition.fact` is matched
against (`contracts/policy.py` `unrunnable_reasons`). There is no `path`
attribute on a declared fact and there never was; reading one aborts the whole
anchor build, and because the caller treats discovery as additive and swallows
the failure, every rule on the run is reported with zero relationships for a
reason that has nothing to do with the document.

These tests drive the real `_relationship_anchors`. The load-bearing case is a
rule that declares a fact: only then does the comprehension read the per-fact
attribute at all, so a rule with no facts would pass against the bug and prove
nothing (this repository's most-logged failure, a green test over a dead path).
"""
from __future__ import annotations

from policy_platform.contracts.conditions import (
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.policy import RequiredFact
from policy_platform.infrastructure.extraction.ai_extraction import (
    _relationship_anchors,
)

from tests.fixtures.factories import make_rule


def _condition() -> FactComparisonCondition:
    return FactComparisonCondition(
        fact="leave-calendar-days",
        operator=ConditionOperator.GREATER_THAN,
        value=15,
    )


def _rule_declaring(*fact_names: str):
    """A drafted rule that declares the named facts, everything else defaulted.

    `make_rule` builds a schema-valid `CanonicalRule`; `model_copy` adds the
    declared facts without the test needing to name every unrelated field.
    """

    rule = make_rule("R-facts", _condition())
    return rule.model_copy(
        update={
            "required_facts": [
                RequiredFact(name=name, data_type="number") for name in fact_names
            ]
        }
    )


def test_a_declared_fact_becomes_the_anchors_fact_path() -> None:
    rule = _rule_declaring("leave-calendar-days")

    anchors = _relationship_anchors([rule])

    assert len(anchors) == 1
    # The anchor carries the identifier the rule declares -- the join key
    # discovery compares -- not a placeholder and not a crash.
    assert anchors[0].fact_paths == ["leave-calendar-days"]


def test_every_declared_fact_is_carried_deduplicated_and_ordered() -> None:
    # Two facts, given out of order and with a duplicate, so the assertion is
    # about the set the rule declares rather than any one document's count.
    rule = _rule_declaring("employee-hours", "leave-calendar-days", "employee-hours")

    anchors = _relationship_anchors([rule])

    assert anchors[0].fact_paths == ["employee-hours", "leave-calendar-days"]


def test_a_rule_that_declares_no_facts_still_anchors_with_an_empty_path_set() -> None:
    # The state a rule is in when its projection came back enrichment_required.
    # It must still produce an anchor -- an unprojected rule still belongs to
    # its table and section -- with no fact paths rather than no anchor.
    rule = _rule_declaring()

    anchors = _relationship_anchors([rule])

    assert len(anchors) == 1
    assert anchors[0].fact_paths == []


def test_a_fact_carrying_rule_does_not_abort_the_whole_batch() -> None:
    # The shape the live defect took: one fact-carrying rule made the anchor
    # build raise, and the caller's additive-discovery guard turned that into
    # zero relationships for every rule in the run. All rules must anchor.
    with_facts = _rule_declaring("employee-hours").model_copy(update={"rule_id": "R-1"})
    without_facts = _rule_declaring().model_copy(update={"rule_id": "R-2"})

    anchors = _relationship_anchors([with_facts, without_facts])

    assert [a.rule_id for a in anchors] == ["R-1", "R-2"]
