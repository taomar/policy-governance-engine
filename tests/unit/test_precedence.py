"""Unit tests for deterministic rule precedence (Section 15.4).

Explicitly verifies that precedence is NOT "newest rule always wins":
authority rank and scope specificity are considered before recency.
"""
from __future__ import annotations

from datetime import date

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.evaluator.precedence import order_rules_by_precedence
from tests.fixtures.factories import make_authority, make_rule, make_scope

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


class TestPrecedenceOrdering:
    def test_higher_authority_rank_wins_regardless_of_recency(self):
        older_but_higher_authority = make_rule(
            "RULE-A",
            _ALWAYS_TRUE,
            authority=make_authority(rank=20),
            effective_from=date(2020, 1, 1),
        )
        newer_but_lower_authority = make_rule(
            "RULE-B",
            _ALWAYS_TRUE,
            authority=make_authority(rank=10),
            effective_from=date(2024, 1, 1),
        )
        ordered = order_rules_by_precedence([newer_but_lower_authority, older_but_higher_authority])
        assert [r.rule_id for r in ordered] == ["RULE-A", "RULE-B"]

    def test_more_specific_scope_wins_at_equal_authority(self):
        broad_scope = make_rule(
            "RULE-BROAD",
            _ALWAYS_TRUE,
            authority=make_authority(rank=10),
            scope=make_scope(organizational_units=["*"], personas=["*"]),
        )
        specific_scope = make_rule(
            "RULE-SPECIFIC",
            _ALWAYS_TRUE,
            authority=make_authority(rank=10),
            scope=make_scope(organizational_units=["finance"], personas=["manager"]),
        )
        ordered = order_rules_by_precedence([broad_scope, specific_scope])
        assert [r.rule_id for r in ordered] == ["RULE-SPECIFIC", "RULE-BROAD"]

    def test_priority_breaks_ties_at_equal_authority_and_scope(self):
        low_priority = make_rule("RULE-LOW", _ALWAYS_TRUE, priority=1)
        high_priority = make_rule("RULE-HIGH", _ALWAYS_TRUE, priority=5)
        ordered = order_rules_by_precedence([low_priority, high_priority])
        assert [r.rule_id for r in ordered] == ["RULE-HIGH", "RULE-LOW"]

    def test_recency_is_only_a_tiebreaker_after_authority_scope_priority(self):
        older = make_rule("RULE-OLD", _ALWAYS_TRUE, effective_from=date(2020, 1, 1))
        newer = make_rule("RULE-NEW", _ALWAYS_TRUE, effective_from=date(2024, 1, 1))
        ordered = order_rules_by_precedence([older, newer])
        # among otherwise-equal rules, more recently effective wins as a tiebreaker
        assert [r.rule_id for r in ordered] == ["RULE-NEW", "RULE-OLD"]

    def test_rule_id_is_final_deterministic_tiebreaker(self):
        rule_z = make_rule("RULE-Z", _ALWAYS_TRUE)
        rule_a = make_rule("RULE-A", _ALWAYS_TRUE)
        # all other factors identical -> rule_id ascending
        ordered = order_rules_by_precedence([rule_z, rule_a])
        assert [r.rule_id for r in ordered] == ["RULE-A", "RULE-Z"]

    def test_ordering_is_stable_regardless_of_input_order(self):
        rule_a = make_rule("RULE-A", _ALWAYS_TRUE, authority=make_authority(rank=20))
        rule_b = make_rule("RULE-B", _ALWAYS_TRUE, authority=make_authority(rank=10))
        rule_c = make_rule("RULE-C", _ALWAYS_TRUE, authority=make_authority(rank=15))

        order_1 = [r.rule_id for r in order_rules_by_precedence([rule_a, rule_b, rule_c])]
        order_2 = [r.rule_id for r in order_rules_by_precedence([rule_c, rule_a, rule_b])]
        order_3 = [r.rule_id for r in order_rules_by_precedence([rule_b, rule_c, rule_a])]

        assert order_1 == order_2 == order_3 == ["RULE-A", "RULE-C", "RULE-B"]


class TestSpecUnimplementedPrecedenceDimensions:
    """Section 15.4's remaining 3 dimensions beyond the original 5: jurisdiction
    (as its own dimension, distinct from scope specificity), explicit override,
    and explicit exception. See precedence.py's module docstring for the
    interpretive choices made where the spec doesn't further define a term.
    """

    def test_specific_jurisdiction_wins_over_wildcard_at_equal_authority(self):
        wildcard_jurisdiction = make_rule(
            "RULE-GENERAL", _ALWAYS_TRUE, scope=make_scope(jurisdictions=["*"])
        )
        specific_jurisdiction = make_rule(
            "RULE-US-SPECIFIC", _ALWAYS_TRUE, scope=make_scope(jurisdictions=["US"])
        )
        ordered = order_rules_by_precedence([wildcard_jurisdiction, specific_jurisdiction])
        assert [r.rule_id for r in ordered] == ["RULE-US-SPECIFIC", "RULE-GENERAL"]

    def test_jurisdiction_is_considered_before_scope_specificity(self):
        """A rule with a specific jurisdiction but broad org/persona scope
        still outranks a rule with wildcard jurisdiction but narrow org/persona
        scope, since jurisdiction is listed before scope specificity."""
        specific_jurisdiction_broad_scope = make_rule(
            "RULE-JURISDICTION",
            _ALWAYS_TRUE,
            scope=make_scope(jurisdictions=["US"], organizational_units=["*"], personas=["*"]),
        )
        wildcard_jurisdiction_narrow_scope = make_rule(
            "RULE-SCOPE",
            _ALWAYS_TRUE,
            scope=make_scope(jurisdictions=["*"], organizational_units=["finance"], personas=["manager"]),
        )
        ordered = order_rules_by_precedence(
            [wildcard_jurisdiction_narrow_scope, specific_jurisdiction_broad_scope]
        )
        assert [r.rule_id for r in ordered] == ["RULE-JURISDICTION", "RULE-SCOPE"]

    def test_explicit_override_wins_at_equal_authority_and_scope(self):
        normal_rule = make_rule("RULE-NORMAL", _ALWAYS_TRUE, is_explicit_override=False)
        override_rule = make_rule("RULE-OVERRIDE", _ALWAYS_TRUE, is_explicit_override=True)
        ordered = order_rules_by_precedence([normal_rule, override_rule])
        assert [r.rule_id for r in ordered] == ["RULE-OVERRIDE", "RULE-NORMAL"]

    def test_explicit_exception_rule_type_wins_over_general_rule(self):
        from policy_platform.contracts.policy import RuleType

        general_rule = make_rule("RULE-GENERAL", _ALWAYS_TRUE, rule_type=RuleType.APPROVAL_REQUIREMENT)
        exception_rule = make_rule("RULE-EXCEPTION", _ALWAYS_TRUE, rule_type=RuleType.EXCEPTION)
        ordered = order_rules_by_precedence([general_rule, exception_rule])
        assert [r.rule_id for r in ordered] == ["RULE-EXCEPTION", "RULE-GENERAL"]

    def test_rule_with_nested_exceptions_wins_over_rule_without(self):
        """A non-EXCEPTION-typed rule that nonetheless carries RuleException
        entries is also treated as carrying an "explicit exception" signal."""
        from policy_platform.contracts.policy import RuleException

        plain_rule = make_rule("RULE-PLAIN", _ALWAYS_TRUE)
        rule_with_exception = make_rule(
            "RULE-WITH-EXCEPTION",
            _ALWAYS_TRUE,
            exceptions=[RuleException(exception_id="EXC-1", description="carve-out")],
        )
        ordered = order_rules_by_precedence([plain_rule, rule_with_exception])
        assert [r.rule_id for r in ordered] == ["RULE-WITH-EXCEPTION", "RULE-PLAIN"]

    def test_effective_date_is_considered_before_priority(self):
        """Spec order lists 'Effective date' before 'Rule priority' -- a more
        recently effective rule wins over a higher-priority-but-older rule
        when authority/jurisdiction/scope/override/exception all tie."""
        older_higher_priority = make_rule(
            "RULE-OLD-HIGH-PRIORITY", _ALWAYS_TRUE, priority=100, effective_from=date(2020, 1, 1)
        )
        newer_lower_priority = make_rule(
            "RULE-NEW-LOW-PRIORITY", _ALWAYS_TRUE, priority=1, effective_from=date(2024, 1, 1)
        )
        ordered = order_rules_by_precedence([older_higher_priority, newer_lower_priority])
        assert [r.rule_id for r in ordered] == ["RULE-NEW-LOW-PRIORITY", "RULE-OLD-HIGH-PRIORITY"]

    def test_supersession_relationship_as_final_tiebreak(self):
        """A rule that another applicable rule explicitly supersedes sorts
        after the superseding rule, even though it would otherwise tie (and
        even alphabetically sort first)."""
        superseded_rule = make_rule("RULE-A-OLD", _ALWAYS_TRUE)
        superseding_rule = make_rule(
            "RULE-B-NEW", _ALWAYS_TRUE, supersedes_rule_ids=["RULE-A-OLD"]
        )
        ordered = order_rules_by_precedence([superseded_rule, superseding_rule])
        assert [r.rule_id for r in ordered] == ["RULE-B-NEW", "RULE-A-OLD"]
