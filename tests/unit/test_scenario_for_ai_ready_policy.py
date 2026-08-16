"""Scenario-testing an AI Ready policy must not raise.

`run_rule_scenario` short-circuits before any AI call when the deterministic
engine cannot evaluate the policy, and returns an explanation instead. That
branch covers 53 of the 55 records in the live corpus — nearly every policy a
user would try — and had no test at all.

It broke, silently, when `DecisionReadiness.reason` was removed: the branch read
that field to compose its explanation, so every attempt to scenario-test an
ai_ready policy raised `AttributeError`. Nothing failed in the suite, because
nothing exercised the branch. It was found by grepping for readers of a removed
field, not by running anything.

The tests below are about that branch surviving and saying something true. They
avoid the AI path entirely, which is the point: this route exists so that no AI
call is made.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.policy import DecisionReadiness, EvaluationMode
from policy_platform.infrastructure.assistants.ai_scenario_engine import explain_decided_by_reading
from tests.fixtures.factories import make_package, make_rule


def _decided_by_reading(**overrides):
    """A policy the deterministic engine will not evaluate."""

    rule = make_rule(
        rule_id="RULE-READING",
        condition=AllCondition(all=[]),
        machine_executable=False,
        **overrides,
    )
    return rule.model_copy(
        update={
            "title": "Exceptional increase may be granted",
            "evaluation_mode": EvaluationMode.AI_READY,
            "required_facts": [],
        }
    )


def _run(rule, scenario: str = "An employee asks for an exceptional increase."):
    return explain_decided_by_reading(
        rule=rule,
        package=make_package(rules=[rule]),
        scenario=scenario,
        reasoning_effort="low",
        mapping_statuses=[],
        formulation_requirements=[],
    )


def test_scenario_testing_an_ai_ready_policy_does_not_raise():
    """The regression. This raised on every policy it described."""

    result = _run(_decided_by_reading())

    assert result["rule_id"] == "RULE-READING"
    assert result["overall_evaluation_status"]


def test_it_still_works_when_the_readiness_assessment_is_present():
    """The field that was read is gone; the object it lived on is not."""

    rule = _decided_by_reading()
    rule = rule.model_copy(
        update={"decision_readiness": DecisionReadiness(evaluability="discretionary")}
    )

    result = _run(rule)

    assert "discretionary" in result["explanation"]


def test_it_still_works_when_there_is_no_readiness_assessment():
    """Hand-authored policies carry none."""

    rule = _decided_by_reading().model_copy(update={"decision_readiness": None})

    result = _run(rule)

    assert result["explanation"]


def test_the_explanation_does_not_report_the_policy_as_defective():
    """A route, not a fault.

    Three earlier wordings called it "documentation-only", then reported a DMN
    mapping status and the enrichment codes it "requires", then said
    `machine_executable=false` — a standing request for configuration, on a
    policy whose test the source states in words and which will never become a
    comparison.
    """

    explanation = _run(_decided_by_reading())["explanation"]

    # Said positively rather than denied. A fourth wording opened "This is not a
    # failed policy decision", which was the fix for the three above and was
    # itself worth replacing: a reader told this is not a failure has been told
    # that failure was on the table. What replaces it is not silence. The
    # explanation names the route, says who decides it, and says the engine's
    # NOT_APPLICABLE is the correct answer — so the reassurance is carried
    # without the word being planted.
    #
    # Pinned on the claims rather than on a sentence, because the previous
    # version of this test asserted one phrase and would have passed on an
    # explanation that both denied failure and framed one elsewhere.
    assert "decided by a judge reading the record" in explanation
    assert "correct answer for it to give" in explanation

    for forbidden in (
        "machine_executable",
        "machine-executable",
        "FACT_MODEL_REQUIRED",
        "documentation-only",
        "Configure a fact model",
        # The vocabulary the denial existed to deny. Forbidding it outright is
        # what makes the denial unnecessary rather than merely absent.
        "failed",
        "failure",
        "defective",
    ):
        assert forbidden not in explanation


def test_no_ai_call_is_made_for_a_policy_decided_by_reading():
    """The reason the branch exists: two AI calls saved on a known answer."""

    result = _run(_decided_by_reading())

    assert result["inferred_facts"] == {}
    assert result["assumptions"] == []
    assert result["testability_reason"] == "decided_by_reading"
