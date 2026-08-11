"""Why a decision failed to compile — measured against real agent output.

Every payload below was captured verbatim from the formulator agent running
against AD-103 clauses 3.2.1 and 3.2.3 with a trusted fact model installed.
That matters: before these tests existed, six of six `executable` decisions
produced by live runs compiled to nothing, and every one of them reported the
same bare `None` as an ordinary non-executable rule. The platform therefore
told reviewers to "supply the missing mapping" for rules whose mapping was
already complete.

These tests pin the distinction that was missing, not the compiler's coverage.
Extending coverage is a separate, larger change (it needs the condition
contract and the evaluator to represent fact-relative comparison); until then
the gap must at least be visible and correctly attributed.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
)
from policy_platform.contracts.policy import AmbiguityStatus
from policy_platform.infrastructure.formulation_mapping import (
    ConditionDerivationReason,
    _ambiguity_for,
    condition_provenance,
    derive_condition,
    derive_condition_outcome,
)

# --------------------------------------------------------------------------
# Verbatim agent output
# --------------------------------------------------------------------------

#: AD-103 clause 3.2.1, emitted on 3 of 3 trials once the fact model named the
#: clause's terms. A complete, grounded FEEL expression — and the shape the
#: compiler never reads.
LITERAL_EXPRESSION_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "literal_expression": {
        "output": {"name": "annual_increase_permitted", "type": "boolean"},
        "feel": (
            "employee.compensation.proposed_annual_increase <= "
            "employee.compensation.current_basic_salary * 0.10"
        ),
    },
}

#: AD-103 clause 3.2.3. A decision *table*, so the compiler reads it — but the
#: unary test compares against a percentage of another fact, which the platform
#: condition contract cannot represent.
FACT_RELATIVE_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [
            {
                "label": "inflation increase",
                "expression": "employee.compensation.proposed_inflation_increase",
                "type": "number",
            },
            {
                "label": "approval of the Board of Trustees",
                "expression": "approval.board_of_trustees_approved",
                "type": "boolean",
            },
        ],
        "outputs": [
            {
                "label": "inflation increase permitted",
                "name": "inflation_increase_permitted",
                "type": "boolean",
            }
        ],
        "rules": [
            {
                "input_entries": [
                    "<= employee.compensation.basic_salary * 0.05",
                    "true",
                ],
                "output_entries": ["true"],
            }
        ],
    },
}

#: The shape the compiler *does* support, kept as the control: without it, a
#: test asserting "these do not compile" would pass even if nothing compiled.
SUPPORTED_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [{"label": "expense amount", "expression": "expense.amount", "type": "number"}],
        "outputs": [{"label": "route", "name": "approvalRoute", "type": "string"}],
        "rules": [{"input_entries": [">= 5000"], "output_entries": ['"executive"']}],
    },
}


def _decision(payload: dict) -> DmnDecision:
    return DmnDecision.model_validate(payload)


def _policy(condition: str | None) -> CanonicalPolicy:
    rule = CanonicalPolicyRule(
        rule_type=CanonicalRuleType.OBLIGATION,
        subject="the University",
        predicate="grant",
        object="the annual increase",
        condition=condition,
    )
    return CanonicalPolicy(source_text="The University shall grant the annual increase.", rule=rule)


# --------------------------------------------------------------------------
# The control: the compiler still works where it always worked
# --------------------------------------------------------------------------


def test_supported_table_still_compiles():
    """Guards the tests below: they only mean something if compilation works."""

    outcome = derive_condition_outcome(_decision(SUPPORTED_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert outcome.derived is True
    assert outcome.platform_limited is False
    assert [f.name for f in outcome.facts] == ["expense.amount"]


def test_wrapper_agrees_with_outcome_on_success():
    """The tuple API and the outcome API are one implementation, not two."""

    decision = _decision(SUPPORTED_TABLE_DECISION)
    outcome = derive_condition_outcome(decision, 0)
    wrapped = derive_condition(decision, 0)

    assert wrapped is not None
    condition, facts = wrapped
    assert condition == outcome.condition
    assert facts == list(outcome.facts)


# --------------------------------------------------------------------------
# The two real failures, each named rather than collapsed to None
# --------------------------------------------------------------------------


def test_literal_expression_is_reported_not_silently_dropped():
    outcome = derive_condition_outcome(_decision(LITERAL_EXPRESSION_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.LITERAL_EXPRESSION_UNSUPPORTED
    assert outcome.derived is False
    assert outcome.platform_limited is True
    # The reviewer sees exactly what the agent produced, not a paraphrase.
    assert outcome.unsupported_expression == (
        "employee.compensation.proposed_annual_increase <= "
        "employee.compensation.current_basic_salary * 0.10"
    )


def test_fact_relative_unary_test_is_reported_not_silently_dropped():
    outcome = derive_condition_outcome(_decision(FACT_RELATIVE_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.UNSUPPORTED_UNARY_TEST
    assert outcome.platform_limited is True
    assert "employee.compensation.basic_salary * 0.05" in outcome.unsupported_expression


def test_ordinary_non_executable_is_not_mistaken_for_a_platform_limit():
    """The common case must stay distinguishable from the two above."""

    outcome = derive_condition_outcome(
        _decision(
            {
                "source_rule_indexes": [0],
                "dmn_mapping_status": "enrichment_required",
                "requirements": ["FACT_MODEL_REQUIRED"],
            }
        ),
        0,
    )

    assert outcome.reason is ConditionDerivationReason.NOT_DECLARED_EXECUTABLE
    assert outcome.platform_limited is False


@pytest.mark.parametrize(
    "payload",
    [LITERAL_EXPRESSION_DECISION, FACT_RELATIVE_TABLE_DECISION],
    ids=["literal_expression", "fact_relative_table"],
)
def test_grounded_but_uncompilable_never_becomes_executable(payload):
    """Naming the failure must not soften the gate.

    The whole point of the `executable` gate is that an uncompilable decision
    stays non-executable. Reporting *why* must not become a way to let one
    through.
    """

    assert derive_condition(_decision(payload), 0) is None


# --------------------------------------------------------------------------
# The reviewer-facing consequence
# --------------------------------------------------------------------------


def test_platform_limit_does_not_blame_the_fact_model():
    """The defect this whole module exists to prevent.

    The old message said "a reviewer must supply the missing mapping" for a
    rule whose mapping was already supplied and correct — sending a human to
    edit a fact model that was not the problem.
    """

    outcome = derive_condition_outcome(_decision(LITERAL_EXPRESSION_DECISION), 0)
    code, message = condition_provenance(
        _policy("annual increase not exceeding 10% of current basic salary"),
        None,
        outcome,
    )

    assert code == "conditions_not_representable"
    # It must not *instruct* a reviewer to go and supply a mapping; saying
    # "not a missing mapping" is exactly the correction being asserted.
    assert "supply the missing mapping" not in message
    assert "not a missing mapping" in message
    assert "platform limitation" in message
    # The agent's actual expression is quoted, so the gap is auditable.
    assert "proposed_annual_increase" in message


def test_missing_mapping_message_survives_for_the_case_it_describes():
    """The old message is still right when the agent never grounded anything."""

    outcome = derive_condition_outcome(
        _decision({"source_rule_indexes": [0], "dmn_mapping_status": "enrichment_required"}),
        0,
    )
    code, message = condition_provenance(_policy("only for P1 incidents"), None, outcome)

    assert code == "conditions_not_projected"
    assert "supply the missing mapping" in message


def test_provenance_without_an_outcome_is_unchanged():
    """Existing callers that pass no outcome keep their previous behaviour."""

    assert condition_provenance(_policy("only for P1 incidents"), None)[0] == (
        "conditions_not_projected"
    )
    assert condition_provenance(_policy(None), None)[0] == "no_scope_derived"
    assert condition_provenance(_policy("anything"), object())[0] == "derived"


# --------------------------------------------------------------------------
# The safety gate must not weaken as a side effect of naming the cause
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["conditions_not_projected", "conditions_not_representable"],
)
def test_an_understated_tree_always_requires_human_judgment(code):
    """Naming a new cause must not create a hole in the safety gate.

    Both codes leave an empty tree that reads as "always applies" while the
    source states conditions. Adding `conditions_not_representable` without
    adding it here would have silently downgraded exactly the rules that are
    closest to executable — the stored tree is equally wrong in both cases.
    """

    assert _ambiguity_for(_policy("only for P1 incidents"), False, code) is (
        AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    )


def test_a_textually_clear_unconfigured_rule_is_still_not_escalated():
    """The control: the gate must stay discriminating, not fire on everything."""

    assert _ambiguity_for(_policy(None), False, "no_scope_derived") is (
        AmbiguityStatus.NON_BLOCKING
    )
