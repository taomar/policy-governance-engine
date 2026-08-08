"""Unit tests for cross-rule aggregate limits (Section 15 combined-cap gap;
OMG DMN "Collect" hit policy with a SUM aggregator).

Scenario grounding the tests: pregnancy leave entitles 60 days, sick-family
leave entitles 15 days/year, but combined they may not exceed 70 days/year --
structurally NOT expressible as a single-rule `RuleException`, since it spans
two different rules' outputs (the same shape as the real-world US FMLA
12-workweek cap combined across qualifying leave reasons).
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationRequest
from policy_platform.contracts.policy import AggregateLimit, AggregateLimitContribution, EffectType
from policy_platform.evaluator.engine import evaluate_policy
from tests.fixtures.factories import make_package, make_rule

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


def _leave_aggregate() -> AggregateLimit:
    return AggregateLimit(
        aggregate_id="AGG-LEAVE-ANNUAL",
        description="Combined pregnancy + sick-family leave may not exceed 70 days/year",
        contributing_rules=[
            AggregateLimitContribution(rule_id="R-PREGNANCY", amount_fact="leave.pregnancyDaysRequested"),
            AggregateLimitContribution(rule_id="R-SICK-FAMILY", amount_fact="leave.sickFamilyDaysRequested"),
        ],
        aggregator="SUM",
        max_value=70,
        period="annual",
    )


class TestAggregateLimits:
    def test_combined_total_within_cap_is_no_breach(self):
        pregnancy = make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave")
        sick_family = make_rule("R-SICK-FAMILY", _ALWAYS_TRUE, effect_action="grant_sick_family_leave")
        package = make_package([pregnancy, sick_family])
        package.aggregate_limits.append(_leave_aggregate())
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "leave.pregnancyDaysRequested": 50, "leave.sickFamilyDaysRequested": 15},
        )

        response = evaluate_policy(package, request)

        assert response.aggregate_breaches == []

    def test_combined_total_over_cap_is_a_breach(self):
        pregnancy = make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave")
        sick_family = make_rule("R-SICK-FAMILY", _ALWAYS_TRUE, effect_action="grant_sick_family_leave")
        package = make_package([pregnancy, sick_family])
        package.aggregate_limits.append(_leave_aggregate())
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "leave.pregnancyDaysRequested": 60, "leave.sickFamilyDaysRequested": 15},
        )

        response = evaluate_policy(package, request)

        assert len(response.aggregate_breaches) == 1
        breach = response.aggregate_breaches[0]
        assert breach.aggregate_id == "AGG-LEAVE-ANNUAL"
        assert breach.total == 75
        assert breach.max_value == 70
        assert set(breach.contributing_rule_ids) == {"R-PREGNANCY", "R-SICK-FAMILY"}

    def test_exactly_at_cap_is_not_a_breach(self):
        pregnancy = make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave")
        sick_family = make_rule("R-SICK-FAMILY", _ALWAYS_TRUE, effect_action="grant_sick_family_leave")
        package = make_package([pregnancy, sick_family])
        package.aggregate_limits.append(_leave_aggregate())
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "leave.pregnancyDaysRequested": 55, "leave.sickFamilyDaysRequested": 15},
        )

        response = evaluate_policy(package, request)

        assert response.aggregate_breaches == []

    def test_only_one_contributing_rule_satisfied_sums_just_that_one(self):
        pregnancy = make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave")
        sick_family_condition = FactComparisonCondition(fact="never_true", operator=ConditionOperator.EXISTS)
        sick_family = make_rule("R-SICK-FAMILY", sick_family_condition, effect_action="grant_sick_family_leave")
        package = make_package([pregnancy, sick_family])
        package.aggregate_limits.append(_leave_aggregate())
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "leave.pregnancyDaysRequested": 60, "leave.sickFamilyDaysRequested": 15},
        )

        response = evaluate_policy(package, request)

        # sick-family rule's condition is FALSE (not satisfied) so it does not
        # contribute; 60 alone is within the 70 cap.
        assert response.aggregate_breaches == []

    def test_overridden_rule_does_not_contribute_to_aggregate(self):
        """A SATISFIED rule that lost the combining-algorithm conflict (deny
        overrode it) should not count toward an aggregate cap it lost the
        right to apply."""
        pregnancy = make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave")
        sick_family = make_rule("R-SICK-FAMILY", _ALWAYS_TRUE, effect_action="grant_sick_family_leave")
        blocking_deny = make_rule(
            "R-BLOCK", _ALWAYS_TRUE, effect_type=EffectType.DENY, effect_action="deny_all_leave"
        )
        package = make_package([pregnancy, sick_family, blocking_deny])
        agg = _leave_aggregate()
        agg.contributing_rules.append(
            AggregateLimitContribution(rule_id="R-BLOCK", amount_fact="leave.blockDaysRequested")
        )
        package.aggregate_limits.append(agg)
        request = EvaluationRequest(
            policy_set_id="test-policy",
            facts={"x": 1, "leave.pregnancyDaysRequested": 60, "leave.sickFamilyDaysRequested": 15},
        )

        response = evaluate_policy(package, request)

        # R-BLOCK (DENY) wins by precedence tiebreak over the two ALLOW rules
        # in this test's default equal-authority setup only if it sorts first;
        # regardless of which side wins, only non-overridden rules contribute.
        contributing = {rid for b in response.aggregate_breaches for rid in b.contributing_rule_ids}
        overridden_ids = {r.rule_id for r in response.rule_results if r.overridden_by is not None}
        assert contributing.isdisjoint(overridden_ids)
