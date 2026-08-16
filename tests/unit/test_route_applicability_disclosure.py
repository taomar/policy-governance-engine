"""A route-skipped check is disclosed as not-applicable, never dropped or passed.

`_route_applicability_disclosure` is the report half of the route seam: where
`applies_to` decides that a check does not run against a record on the other
route, this states that skip on the run result rather than leaving it as an
absence. The distinction it protects is the one the task turns on -- a check
that was not asked of a route must never read as a check that ran and found
nothing, because that is how a page claims assurance a run never established.

The disclosure feeds both run results (`evaluate_policy_set_quality` and
`evaluate_candidate_quality`). These tests exercise the helper directly and pin
that a skip surfaces as an explicit not-applicable entry and, at the same time,
produces no finding -- neither a defect nor a silent pass. No corpus count is
baked in: every quantity asserted is one these tests construct.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.policy import EvaluationMode, RequiredFact
from policy_platform.infrastructure.quality.ai_quality import (
    _deterministic_findings,
    _route_applicability_disclosure,
)
from tests.fixtures.factories import make_rule

_ENGINE_ONLY = "not_runnable_as_stored"
_JUDGE_ONLY = "not_decidable_as_written"


def _deterministic_rule(rule_id: str):
    """A record routed to the engine, declaring the fact its condition names."""

    return make_rule(
        rule_id,
        FactComparisonCondition(
            fact="salary", operator=ConditionOperator.EXISTS, value=None
        ),
    ).model_copy(
        update={
            "evaluation_mode": EvaluationMode.DETERMINISTIC,
            "required_facts": [RequiredFact(name="salary", data_type="number")],
        }
    )


def _judged_rule(rule_id: str):
    """A record decided by reading."""

    return make_rule(rule_id, AllCondition(all=[])).model_copy(
        update={"evaluation_mode": EvaluationMode.AI_READY}
    )


def _entries_for(disclosure, check):
    return [row for row in disclosure if row["check"] == check]


def test_the_engine_check_is_disclosed_not_applicable_for_judged_records():
    judged = [_judged_rule("A1"), _judged_rule("A2")]

    disclosure = _route_applicability_disclosure(judged)
    engine = _entries_for(disclosure, _ENGINE_ONLY)

    assert len(engine) == 1
    assert engine[0]["route"] == EvaluationMode.AI_READY.value
    assert engine[0]["applicability"] == "not_applicable"
    # The count is taken from the records in hand, not assumed.
    assert engine[0]["records_in_scope"] == len(judged)
    assert engine[0]["applies_to_routes"] == [EvaluationMode.DETERMINISTIC.value]


def test_the_judge_check_is_disclosed_not_applicable_for_engine_records():
    disclosure = _route_applicability_disclosure([_deterministic_rule("D1")])
    judge = _entries_for(disclosure, _JUDGE_ONLY)

    assert len(judge) == 1
    assert judge[0]["route"] == EvaluationMode.DETERMINISTIC.value
    assert judge[0]["applicability"] == "not_applicable"
    assert judge[0]["records_in_scope"] == 1


def test_a_skip_is_disclosed_but_never_also_reported_as_a_finding():
    """The load-bearing pairing: not-applicable in the disclosure, absent from findings.

    A judged record is never run against the engine, so the engine check must
    appear in the disclosure as not-applicable and must produce no finding for
    that record. Were the skip instead read as a clean check, it would leave no
    trace here -- which is the failure the disclosure exists to prevent.
    """

    judged = [_judged_rule("A1")]

    disclosed = {row["check"] for row in _route_applicability_disclosure(judged)}
    reported = {f["category"] for f in _deterministic_findings(judged)}

    assert _ENGINE_ONLY in disclosed
    assert _ENGINE_ONLY not in reported


def test_a_records_own_route_check_is_not_listed_not_applicable():
    """Disclosure is about skips only; a record's own check is not a skip.

    A judged record's own question (`not_decidable_as_written`) applies to it,
    so it must not appear in that record's not-applicable disclosure -- listing
    it would misreport an applicable check as one that could not run.
    """

    disclosure = _route_applicability_disclosure([_judged_rule("A1")])
    disclosed = {row["check"] for row in disclosure}

    assert _JUDGE_ONLY not in disclosed
    assert _ENGINE_ONLY in disclosed


def test_both_routes_present_discloses_each_others_check():
    rules = [_deterministic_rule("D1"), _judged_rule("A1"), _judged_rule("A2")]

    disclosure = _route_applicability_disclosure(rules)

    engine = _entries_for(disclosure, _ENGINE_ONLY)
    judge = _entries_for(disclosure, _JUDGE_ONLY)
    assert engine[0]["records_in_scope"] == 2
    assert judge[0]["records_in_scope"] == 1


def test_an_empty_scope_discloses_nothing():
    assert _route_applicability_disclosure([]) == []
