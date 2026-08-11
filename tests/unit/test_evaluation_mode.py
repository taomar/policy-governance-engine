"""Every policy states how it can be decided, in one field.

The JSON is the product. A consumer reads a policy and routes it: a
`deterministic` one to an engine that runs its condition over facts, an
`ai_ready` one to a judge that reads it against the evidence for a case. That
routing decision has to be answerable from the file itself, without inference
and without reconciling several partial signals.

Neither value is a grade. Most policy text is not a decision table and never
will be — an obligation to notify, a delegation of authority, a definition —
and those are complete, correct records.

The field is derived from the condition rather than declared beside it,
because the condition is the thing that decides it. A declared copy could
disagree with the tree it describes.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import (
    AllCondition,
    AnyCondition,
    ConditionOperator,
    FactComparisonCondition,
    FactOperand,
    FactRelativeComparisonCondition,
)
from policy_platform.contracts.policy import (
    EvaluationMode,
    RequiredFact,
    evaluation_mode_from,
)

_FACT = [RequiredFact(name="a.b", data_type="number")]


def _comparison():
    return FactComparisonCondition(
        fact="a.b", operator=ConditionOperator.GREATER_THAN, value=1
    )


# --------------------------------------------------------------------------
# Deterministic
# --------------------------------------------------------------------------


def test_a_condition_over_named_facts_is_deterministic():
    tree = AllCondition(all=[_comparison()])

    assert evaluation_mode_from(tree, _FACT) is EvaluationMode.DETERMINISTIC


def test_a_relative_comparison_is_deterministic():
    """The engine can run a proportional bound as readily as a literal one."""

    tree = AllCondition(
        all=[
            FactRelativeComparisonCondition(
                fact="a.b",
                operator=ConditionOperator.LESS_THAN_OR_EQUAL,
                reference=FactOperand(fact="a.c", factor=0.1),
            )
        ]
    )

    assert evaluation_mode_from(tree, _FACT) is EvaluationMode.DETERMINISTIC


def test_a_bare_leaf_is_deterministic():
    """A tree need not be wrapped in a group to be runnable."""

    assert evaluation_mode_from(_comparison(), _FACT) is EvaluationMode.DETERMINISTIC


# --------------------------------------------------------------------------
# AI-ready
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tree",
    [AllCondition(all=[]), AnyCondition(any=[])],
    ids=["empty_all", "empty_any"],
)
def test_an_empty_tree_is_ai_ready(tree):
    """Nothing to run. The policy is still complete; it is read, not executed."""

    assert evaluation_mode_from(tree, _FACT) is EvaluationMode.AI_READY


def test_a_tree_with_no_named_facts_is_ai_ready():
    """A test with nothing to read a case against decides on nothing.

    Guards the pairing the engine depends on: a condition and the facts it
    reads arrive together or the rule is not runnable, whatever the tree looks
    like.
    """

    assert evaluation_mode_from(AllCondition(all=[_comparison()]), []) is EvaluationMode.AI_READY


# --------------------------------------------------------------------------
# The field on the record
# --------------------------------------------------------------------------


def test_the_mode_is_one_of_exactly_two_values():
    """A consumer routes on this, so the vocabulary has to be closed."""

    assert {mode.value for mode in EvaluationMode} == {"deterministic", "ai_ready"}


def test_the_mode_appears_in_the_serialised_policy():
    """It is the field a consumer reads; it must survive to the JSON."""

    from policy_platform.contracts.policy import CanonicalRule

    payload = CanonicalRule(
        policy_set_id="set",
        policy_version_id="v",
        rule_id="R-1",
        rule_revision=1,
        title="A rule",
        rule_type="obligation",
        authority={"level": "ai_drafted", "owner": "x", "rank": 0},
        scope={},
        condition=AllCondition(all=[_comparison()]),
        effect={"type": "require_action", "action": "do the thing"},
        required_facts=_FACT,
        effective_from="2026-01-01",
        evaluation_mode=EvaluationMode.DETERMINISTIC,
    ).model_dump(mode="json")

    assert payload["evaluation_mode"] == "deterministic"


def test_a_policy_defaults_to_ai_ready_rather_than_deterministic():
    """The safe default. Claiming a rule is runnable when it is not would send
    a consumer down a path that cannot decide it, and report the failure as
    the policy's rather than the classification's."""

    assert EvaluationMode("ai_ready") is EvaluationMode.AI_READY
    from policy_platform.contracts.policy import CanonicalRule

    field = CanonicalRule.model_fields["evaluation_mode"]
    assert field.default is EvaluationMode.AI_READY
