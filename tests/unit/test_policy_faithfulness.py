"""The second pass that re-reads a rule against the source it cites.

Every check here exists because the corresponding defect was found in real
extracted output, so the tests are written from those cases rather than from
imagined ones — and each records the precision problem that shaped it.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition, FactComparisonCondition, ConditionOperator
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EffectType, RuleFormulation
from policy_platform.infrastructure.policy_faithfulness import validate_rule
from tests.fixtures.factories import make_rule


def _rule(
    *,
    source: str,
    action: str,
    effect: EffectType = EffectType.REQUIRE_ACTION,
    condition_text: str = "",
    condition=None,
):
    rule = make_rule("R1", condition or AllCondition(all=[]), effect_type=effect, effect_action=action)
    rule.formulation = RuleFormulation(
        source_index=0,
        canonical=CanonicalPolicy(
            source_text=source,
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="Annual increase",
                predicate="exceed",
                condition=condition_text,
            ),
        ),
        dmn_decisions=[],
    )
    return rule


def _codes(rule):
    return {f.code for f in validate_rule(rule)}


class TestNegationPreserved:
    def test_stripped_negation_is_reported(self):
        # The real case: "shall not exceed 10%" became an obligation to exceed
        # 10% — the opposite of the policy, with the same citation.
        rule = _rule(
            source="3.2.1. Annual increase which shall not exceed 10% of the current basic salary.",
            action="exceed 10% of the current basic salary",
        )

        assert "negation_dropped" in _codes(rule)

    def test_negation_inside_a_condition_is_not_reported(self):
        # The precision case. An earlier version flagged any "not" in the first
        # half of the source and was right half the time: here the negation
        # qualifies *which clinics*, while the obligation to submit is real.
        # A check that cries wolf on half its findings teaches a reviewer to
        # skip it, which leaves the true inversions less visible than before.
        rule = _rule(
            source=(
                "In the case of medical treatment in clinics that are not approved by the "
                "insurance company, the original receipt shall be submitted to Human Resources."
            ),
            action="be submitted to the Human Resources Department",
        )

        assert "negation_dropped" not in _codes(rule)

    def test_action_that_keeps_the_negation_is_not_reported(self):
        rule = _rule(
            source="FBSU will not bear any responsibility for excluded coverage.",
            action="will not bear any responsibility",
        )

        assert "negation_dropped" not in _codes(rule)

    def test_deny_effect_is_never_reported(self):
        rule = _rule(
            source="Annual increase shall not exceed 10% of the current basic salary.",
            action="exceed 10% of the current basic salary",
            effect=EffectType.DENY,
        )

        assert "negation_dropped" not in _codes(rule)


class TestQuantitiesPreserved:
    def test_dropped_limit_is_reported(self):
        # "not exceeding 5%" becoming "not exceeding" reads as a complete rule
        # and enforces nothing.
        rule = _rule(
            source="Increase due to inflation with a percentage not exceeding 5% of basic salary.",
            action="be increased due to inflation",
        )

        assert "quantity_dropped" in _codes(rule)

    def test_limit_carried_in_the_action_is_not_reported(self):
        rule = _rule(
            source="Increase due to inflation with a percentage not exceeding 5% of basic salary.",
            action="be increased by no more than 5%",
        )

        assert "quantity_dropped" not in _codes(rule)

    def test_limit_carried_in_the_condition_tree_is_not_reported(self):
        # A quantity is preserved whether it landed in the action or in the
        # compiled condition; demanding one location would report faithful
        # rules as defective.
        rule = _rule(
            source="Annual leave shall be 30 days per year.",
            action="grant annual leave",
            condition=AllCondition(
                all=[
                    FactComparisonCondition(
                        fact="leave.days", operator=ConditionOperator.EQUALS, value=30
                    )
                ]
            ),
        )

        assert "quantity_dropped" not in _codes(rule)

    def test_unit_wording_difference_is_not_reported(self):
        # The source may write "10%" where the rule writes "10 percent".
        rule = _rule(
            source="The increase shall not be more than 10% of basic salary.",
            action="limit the increase to 10 percent",
        )

        assert "quantity_dropped" not in _codes(rule)


class TestConditionsRepresented:
    def test_lost_condition_is_reported(self):
        rule = _rule(
            source="Leave is granted where the employee has completed probation.",
            action="grant leave",
            condition_text="where the employee has completed probation",
        )

        assert "condition_lost" in _codes(rule)

    def test_condition_carried_as_prose_is_not_reported(self):
        # Carried but not compiled is a mapping gap, recorded elsewhere. Nothing
        # was lost, so it is not a faithfulness failure.
        rule = _rule(
            source="Leave is granted where the employee has completed probation.",
            action="grant leave where the employee has completed probation",
            condition_text="where the employee has completed probation",
        )

        assert "condition_lost" not in _codes(rule)


class TestActionIsNotAFragment:
    def test_trailing_preposition_is_reported(self):
        # The tell that a value-deriving rule was projected as an obligation.
        rule = _rule(
            source="The allowance is calculated as twice the basic salary up to a maximum of 15,000 SAR.",
            action="is calculated as twice the monthly basic salary up to a maximum of",
        )

        assert "action_fragment" in _codes(rule)

    def test_complete_action_is_not_reported(self):
        rule = _rule(
            source="The employee shall submit the receipt to Human Resources.",
            action="submit the receipt to Human Resources",
        )

        assert "action_fragment" not in _codes(rule)

    def test_informational_effect_is_never_reported(self):
        rule = _rule(
            source="The allowance is calculated as twice the basic salary up to a maximum of",
            action="is calculated as twice the basic salary up to a maximum of",
            effect=EffectType.INFORMATIONAL,
        )

        assert "action_fragment" not in _codes(rule)
