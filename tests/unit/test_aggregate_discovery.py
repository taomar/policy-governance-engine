"""Unit tests for aggregate-limit eligibility and draft preview.

These cover the two silent failure modes in
`evaluator/engine.py::_evaluate_aggregate_limits` that made the aggregate
limits feature meaningless in practice: a rule that can never be SATISFIED, and
an `amount_fact` that is never a number. Both cause the evaluator to skip the
contribution without raising, so a cap over such rules saves and publishes
cleanly and then does nothing at all.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import RequiredFact
from policy_platform.infrastructure.aggregate_eligibility import (
    BLOCKER_NO_NUMERIC_FACT,
    BLOCKER_NOT_MACHINE_EXECUTABLE,
    assess_rule,
    assess_rules,
    numeric_facts_for,
)
from policy_platform.infrastructure.aggregate_preview import preview_aggregate_limit
from policy_platform.infrastructure.ai_aggregate_proposal import _validate_group
from tests.fixtures.factories import make_package, make_rule

_ALWAYS_TRUE = FactComparisonCondition(fact="x", operator=ConditionOperator.EXISTS)


def _rule(rule_id: str, *, facts: list[tuple[str, str]] | None = None, executable: bool = True):
    """A rule with declared `required_facts`, which `make_rule` does not expose."""

    return make_rule(rule_id, _ALWAYS_TRUE, machine_executable=executable).model_copy(
        update={
            "required_facts": [RequiredFact(name=n, data_type=t) for n, t in (facts or [])],
        }
    )


class TestNumericFactDetection:
    def test_number_typed_facts_are_summable(self):
        rule = _rule("R1", facts=[("leave.days", "number")])
        assert [f.name for f in numeric_facts_for(rule)] == ["leave.days"]

    def test_string_and_boolean_facts_are_not_summable(self):
        rule = _rule("R1", facts=[("employee.name", "string"), ("employee.active", "boolean")])
        assert numeric_facts_for(rule) == []

    def test_numeric_type_synonyms_are_accepted_case_insensitively(self):
        rule = _rule(
            "R1",
            facts=[("a", "Integer"), ("b", "DECIMAL"), ("c", "double"), ("d", "long")],
        )
        assert {f.name for f in numeric_facts_for(rule)} == {"a", "b", "c", "d"}


class TestRuleEligibility:
    def test_executable_rule_with_numeric_fact_is_eligible(self):
        result = assess_rule(_rule("R1", facts=[("leave.days", "number")]))
        assert result.eligible is True
        assert result.blockers == []

    def test_non_executable_rule_is_blocked(self):
        """`_evaluate_rule` returns NOT_APPLICABLE before reading scope or
        condition when machine_executable is false, so the rule can never reach
        the SATISFIED state a contribution requires."""

        result = assess_rule(_rule("R1", facts=[("leave.days", "number")], executable=False))
        assert result.eligible is False
        assert BLOCKER_NOT_MACHINE_EXECUTABLE in result.blockers

    def test_rule_without_numeric_fact_is_blocked(self):
        result = assess_rule(_rule("R1", facts=[("employee.name", "string")]))
        assert result.eligible is False
        assert BLOCKER_NO_NUMERIC_FACT in result.blockers

    def test_rule_declaring_no_facts_at_all_is_blocked(self):
        result = assess_rule(_rule("R1"))
        assert result.eligible is False
        assert BLOCKER_NO_NUMERIC_FACT in result.blockers

    def test_both_blockers_are_reported_together(self):
        """Reporting one blocker at a time would send the reviewer round the
        loop twice for a rule that has two distinct problems."""

        result = assess_rule(_rule("R1", executable=False))
        assert sorted(result.blockers) == sorted(
            [BLOCKER_NOT_MACHINE_EXECUTABLE, BLOCKER_NO_NUMERIC_FACT]
        )


class TestEligibilityReport:
    def test_two_eligible_rules_can_build_a_limit(self):
        report = assess_rules(
            [_rule("R1", facts=[("a", "number")]), _rule("R2", facts=[("b", "number")])]
        )
        assert report.can_build_limit is True
        assert report.to_dict()["eligible_count"] == 2

    def test_one_eligible_rule_cannot_build_a_combined_cap(self):
        """A cap over a single rule is that rule's own threshold and belongs in
        its condition, not in cross-rule machinery."""

        report = assess_rules([_rule("R1", facts=[("a", "number")]), _rule("R2")])
        assert report.can_build_limit is False

    def test_blocker_totals_are_counted_per_reason(self):
        report = assess_rules(
            [
                _rule("R1", facts=[("a", "number")], executable=False),
                _rule("R2", facts=[("b", "string")]),
            ]
        )
        totals = report.to_dict()["blocker_totals"]
        assert totals[BLOCKER_NOT_MACHINE_EXECUTABLE] == 1
        assert totals[BLOCKER_NO_NUMERIC_FACT] == 1


class TestAggregatePreview:
    def _package(self):
        return make_package(
            [
                make_rule("R-PREGNANCY", _ALWAYS_TRUE, effect_action="grant_pregnancy_leave"),
                make_rule("R-SICK", _ALWAYS_TRUE, effect_action="grant_sick_leave"),
            ]
        )

    def _contributions(self):
        return [
            {"rule_id": "R-PREGNANCY", "amount_fact": "leave.pregnancyDays"},
            {"rule_id": "R-SICK", "amount_fact": "leave.sickDays"},
        ]

    def test_total_under_cap_is_within_limit(self):
        result = preview_aggregate_limit(
            self._package(),
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1, "leave.pregnancyDays": 50, "leave.sickDays": 15},
        )
        assert result["verdict"] == "within_limit"
        assert result["breached"] is False
        assert result["total"] == 65
        assert result["contributing_count"] == 2

    def test_total_over_cap_is_breached(self):
        result = preview_aggregate_limit(
            self._package(),
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1, "leave.pregnancyDays": 60, "leave.sickDays": 15},
        )
        assert result["verdict"] == "breached"
        assert result["breached"] is True
        assert result["total"] == 75

    def test_cap_with_no_contributions_is_inert_not_a_pass(self):
        """The headline failure this feature had: nothing contributed, so the
        cap is meaningless — reporting that as "within limits" would be the
        same false reassurance as before."""

        result = preview_aggregate_limit(
            self._package(),
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1},
        )
        assert result["verdict"] == "inert"
        assert result["breached"] is False
        assert result["contributing_count"] == 0

    def test_non_numeric_amount_is_explained_as_a_silent_zero(self):
        result = preview_aggregate_limit(
            self._package(),
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1, "leave.pregnancyDays": "sixty", "leave.sickDays": 15},
        )
        pregnancy = next(c for c in result["contributions"] if c["rule_id"] == "R-PREGNANCY")
        assert pregnancy["contributed"] is False
        assert "silent-zero" in pregnancy["reason"]
        assert result["total"] == 15

    def test_non_executable_rule_is_explained_by_its_status(self):
        package = make_package(
            [
                make_rule("R-PREGNANCY", _ALWAYS_TRUE, machine_executable=False),
                make_rule("R-SICK", _ALWAYS_TRUE, effect_action="grant_sick_leave"),
            ]
        )
        result = preview_aggregate_limit(
            package,
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1, "leave.pregnancyDays": 60, "leave.sickDays": 15},
        )
        pregnancy = next(c for c in result["contributions"] if c["rule_id"] == "R-PREGNANCY")
        assert pregnancy["contributed"] is False
        assert pregnancy["rule_status"] == "NOT_APPLICABLE"
        assert "only a SATISFIED rule contributes" in pregnancy["reason"]

    def test_preview_does_not_mutate_the_published_package(self):
        """The draft is spliced into a copy. Leaking it into the real package
        would make a preview permanently change evaluation for everyone."""

        package = self._package()
        before = len(package.aggregate_limits)
        preview_aggregate_limit(
            package,
            contributing_rules=self._contributions(),
            max_value=70,
            facts={"x": 1, "leave.pregnancyDays": 50, "leave.sickDays": 15},
        )
        assert len(package.aggregate_limits) == before


class TestProposalValidation:
    """The AI may only assemble groups from rules and facts that really exist.

    Every rejection here corresponds to a cap that would have saved cleanly and
    then silently counted nothing, which is precisely the class of bug that made
    this feature feel meaningless.
    """

    ALLOWED = {"R1": {"leave.days"}, "R2": {"leave.sickDays"}}

    def _group(self, **overrides):
        base = {
            "aggregate_key": "combined-leave-cap",
            "description": "Shared annual leave ceiling",
            "rationale": "Both rules draw on the same annual entitlement.",
            "max_value": 70,
            "max_value_confidence": "stated",
            "period": "year",
            "contributing_rules": [
                {"rule_id": "R1", "amount_fact": "leave.days", "why": "grants annual leave"},
                {"rule_id": "R2", "amount_fact": "leave.sickDays", "why": "consumes the same pool"},
            ],
        }
        base.update(overrides)
        return base

    def test_valid_group_is_accepted(self):
        validated, reason = _validate_group(self._group(), self.ALLOWED)
        assert reason is None
        assert validated is not None
        assert validated["aggregator"] == "SUM"
        assert len(validated["contributing_rules"]) == 2

    def test_unknown_rule_id_is_rejected(self):
        group = self._group(
            contributing_rules=[
                {"rule_id": "R1", "amount_fact": "leave.days"},
                {"rule_id": "GHOST", "amount_fact": "leave.days"},
            ]
        )
        validated, reason = _validate_group(group, self.ALLOWED)
        assert validated is None
        assert "not an eligible rule" in reason

    def test_fact_borrowed_from_another_rule_is_rejected(self):
        """`leave.sickDays` is real, but it belongs to R2. Attaching it to R1
        would make R1 contribute nothing forever."""

        group = self._group(
            contributing_rules=[
                {"rule_id": "R1", "amount_fact": "leave.sickDays"},
                {"rule_id": "R2", "amount_fact": "leave.sickDays"},
            ]
        )
        validated, reason = _validate_group(group, self.ALLOWED)
        assert validated is None
        assert "not a declared numeric fact" in reason

    def test_invented_fact_name_is_rejected(self):
        group = self._group(
            contributing_rules=[
                {"rule_id": "R1", "amount_fact": "leave.totalDaysTaken"},
                {"rule_id": "R2", "amount_fact": "leave.sickDays"},
            ]
        )
        validated, reason = _validate_group(group, self.ALLOWED)
        assert validated is None
        assert "not a declared numeric fact" in reason

    def test_single_contributor_group_is_rejected(self):
        group = self._group(
            contributing_rules=[{"rule_id": "R1", "amount_fact": "leave.days"}]
        )
        validated, reason = _validate_group(group, self.ALLOWED)
        assert validated is None
        assert "at least 2 contributing rules" in reason

    def test_duplicate_rule_would_double_count_and_is_rejected(self):
        group = self._group(
            contributing_rules=[
                {"rule_id": "R1", "amount_fact": "leave.days"},
                {"rule_id": "R1", "amount_fact": "leave.days"},
            ]
        )
        validated, reason = _validate_group(group, self.ALLOWED)
        assert validated is None
        assert "more than once" in reason

    def test_non_numeric_max_value_is_rejected(self):
        validated, reason = _validate_group(self._group(max_value="seventy"), self.ALLOWED)
        assert validated is None
        assert "must be a number" in reason

    def test_boolean_max_value_is_rejected(self):
        """bool is a subclass of int in Python, so True would otherwise pass an
        isinstance check and become a cap of 1."""

        validated, reason = _validate_group(self._group(max_value=True), self.ALLOWED)
        assert validated is None
        assert "must be a number" in reason

    def test_zero_or_negative_cap_is_rejected(self):
        validated, reason = _validate_group(self._group(max_value=0), self.ALLOWED)
        assert validated is None
        assert "greater than zero" in reason

    def test_missing_key_is_rejected(self):
        validated, reason = _validate_group(self._group(aggregate_key="  "), self.ALLOWED)
        assert validated is None
        assert "aggregate_key" in reason

    def test_unrecognised_confidence_defaults_to_unstated(self):
        """Defaulting to the cautious value keeps a garbled response from
        presenting an invented ceiling as if it came from the source text."""

        validated, _ = _validate_group(self._group(max_value_confidence="certain"), self.ALLOWED)
        assert validated["max_value_confidence"] == "unstated"

    def test_blank_period_becomes_null(self):
        validated, _ = _validate_group(self._group(period="   "), self.ALLOWED)
        assert validated["period"] is None
