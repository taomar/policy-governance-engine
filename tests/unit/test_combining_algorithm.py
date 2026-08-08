"""Unit tests for the SATISFIED-rule combining algorithm (Section 15.2 step 7
"apply explicit precedence"; XACML Permit/Deny combining-algorithm family).

Verifies the fix for the conflation bug: previously a satisfied DENY rule's
action landed in the same `required_actions` bag as ALLOW/REQUIRE_ACTION
actions, and `outcome` was chosen alphabetically rather than by precedence.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.contracts.policy import EffectType
from policy_platform.evaluator.engine import evaluate_policy
from tests.fixtures.factories import make_authority, make_package, make_rule

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


class TestCombiningAlgorithm:
    def test_higher_precedence_deny_overrides_lower_precedence_allow(self):
        allow_rule = make_rule(
            "R-ALLOW",
            _ALWAYS_TRUE,
            effect_type=EffectType.ALLOW,
            effect_action="allow_purchase",
            authority=make_authority(rank=5),
        )
        deny_rule = make_rule(
            "R-DENY",
            _ALWAYS_TRUE,
            effect_type=EffectType.DENY,
            effect_action="deny_purchase",
            authority=make_authority(rank=50),
        )
        package = make_package([allow_rule, deny_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.outcome == "deny_purchase"
        assert response.denied_actions == ["deny_purchase"]
        assert response.required_actions == []
        allow_result = next(r for r in response.rule_results if r.rule_id == "R-ALLOW")
        assert allow_result.overridden_by == "R-DENY"
        deny_result = next(r for r in response.rule_results if r.rule_id == "R-DENY")
        assert deny_result.overridden_by is None
        # the overridden rule is still SATISFIED (transparent), just excluded
        # from the winning action lists and marked as overridden
        assert allow_result.status == EvaluationStatus.SATISFIED

    def test_higher_precedence_allow_overrides_lower_precedence_deny(self):
        allow_rule = make_rule(
            "R-ALLOW",
            _ALWAYS_TRUE,
            effect_type=EffectType.ALLOW,
            effect_action="allow_purchase",
            authority=make_authority(rank=50),
        )
        deny_rule = make_rule(
            "R-DENY",
            _ALWAYS_TRUE,
            effect_type=EffectType.DENY,
            effect_action="deny_purchase",
            authority=make_authority(rank=5),
        )
        package = make_package([allow_rule, deny_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.outcome == "allow_purchase"
        assert response.required_actions == ["allow_purchase"]
        assert response.denied_actions == []
        deny_result = next(r for r in response.rule_results if r.rule_id == "R-DENY")
        assert deny_result.overridden_by == "R-ALLOW"

    def test_non_conflicting_satisfied_rules_all_coexist(self):
        """Two ALLOW-side rules (allow + require_action) never conflict with
        each other -- both contribute, matching DMN's Collect hit policy."""
        allow_rule = make_rule("R-ALLOW", _ALWAYS_TRUE, effect_type=EffectType.ALLOW, effect_action="allow_purchase")
        require_rule = make_rule(
            "R-REQUIRE", _ALWAYS_TRUE, effect_type=EffectType.REQUIRE_ACTION, effect_action="notify_finance"
        )
        package = make_package([allow_rule, require_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert set(response.required_actions) == {"allow_purchase", "notify_finance"}
        assert all(r.overridden_by is None for r in response.rule_results)

    def test_outcome_is_precedence_first_not_alphabetical(self):
        """Regression guard for the alphabetical-selection bug: 'zzz_action'
        must still win when it is the higher-precedence satisfied rule."""
        low_alpha_low_precedence = make_rule(
            "R-A",
            _ALWAYS_TRUE,
            effect_action="aaa_action",
            authority=make_authority(rank=1),
        )
        high_alpha_high_precedence = make_rule(
            "R-Z",
            _ALWAYS_TRUE,
            effect_action="zzz_action",
            authority=make_authority(rank=99),
        )
        package = make_package([low_alpha_low_precedence, high_alpha_high_precedence])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.outcome == "zzz_action"

    def test_informational_effect_alone_produces_no_outcome_but_no_crash(self):
        """A `definition`/`classification` rule carries `EffectType.INFORMATIONAL`,
        which never competes for allow/deny precedence. If it is ever the only
        SATISFIED rule (e.g. it becomes machine_executable via a future
        `trusted_config`), the combining algorithm must not crash or force it
        onto a spurious side."""
        info_rule = make_rule(
            "R-INFO",
            _ALWAYS_TRUE,
            effect_type=EffectType.INFORMATIONAL,
            effect_action="Work considered by its nature to end within a limited period.",
        )
        package = make_package([info_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        assert response.outcome is None
        assert response.required_actions == []
        assert response.denied_actions == []
        info_result = next(r for r in response.rule_results if r.rule_id == "R-INFO")
        assert info_result.status == EvaluationStatus.SATISFIED
        assert info_result.overridden_by is None

    def test_informational_effect_does_not_corrupt_a_real_allow_deny_conflict(self):
        """Regression guard: `winner = satisfied[0]` used to pick the top
        precedence SATISFIED rule regardless of effect type. An informational
        rule ranked above a genuine allow/deny conflict is not in `allow_side`,
        so it used to default `winning_side` to `deny_side` -- and would have
        forced that outcome even with no real DENY rule present. Winner
        selection must be restricted to rules that actually compete on the
        allow/deny axis."""
        info_rule = make_rule(
            "R-INFO",
            _ALWAYS_TRUE,
            effect_type=EffectType.INFORMATIONAL,
            effect_action="informational text",
            authority=make_authority(rank=999),
        )
        allow_rule = make_rule(
            "R-ALLOW",
            _ALWAYS_TRUE,
            effect_type=EffectType.ALLOW,
            effect_action="allow_purchase",
            authority=make_authority(rank=5),
        )
        deny_rule = make_rule(
            "R-DENY",
            _ALWAYS_TRUE,
            effect_type=EffectType.DENY,
            effect_action="deny_purchase",
            authority=make_authority(rank=50),
        )
        package = make_package([info_rule, allow_rule, deny_rule])
        request = EvaluationRequest(policy_set_id="test-policy", facts={"x": 1})

        response = evaluate_policy(package, request)

        # The real conflict is R-ALLOW vs R-DENY; R-DENY has higher precedence
        # between the two and must still win, unaffected by R-INFO's higher
        # raw precedence, since R-INFO never competes on this axis.
        assert response.outcome == "deny_purchase"
        assert response.denied_actions == ["deny_purchase"]
        assert response.required_actions == []
        allow_result = next(r for r in response.rule_results if r.rule_id == "R-ALLOW")
        assert allow_result.overridden_by == "R-DENY"
        info_result = next(r for r in response.rule_results if r.rule_id == "R-INFO")
        assert info_result.overridden_by is None
        assert info_result.status == EvaluationStatus.SATISFIED
