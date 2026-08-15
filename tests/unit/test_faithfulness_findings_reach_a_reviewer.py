"""The faithfulness pass runs on every extraction and reached only a log file.

`policy_faithfulness.validate_rules` re-reads each drafted rule against the
sentence it cites. It is the check that catches an inverted obligation --
"shall not exceed 10%" formulated as an obligation *to* exceed 10%, which its
own module calls "not a degraded answer, it is the opposite one, delivered with
the same confidence and the same citation".

`ai_extraction` called it, iterated its findings, and wrote each one to
`logger.info`. Nothing was persisted and nothing was served, so no reviewer has
ever seen one. Its sibling `logic_faithfulness` reaches the reviewer through
`ai_quality._logic_faithfulness_findings`; the two were built together and only
one was wired up.

The repair routes it the same way its sibling goes: through the quality report,
which already holds exactly `list[CanonicalRule]` -- the argument
`validate_rules` takes. No migration, no new endpoint, no second copy of the
detector.

WHY THE POSITIVE CONTROLS ARE HERE. The verdict of the important test is "this
code appears in the report", and a detector that silently stopped firing would
make that fail loudly -- but a report assembled from an empty rule list would
make it fail for the wrong reason and invite the wrong fix. So each test proves
the detector saw its own case first, then that the report carries it.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EffectType, RuleFormulation
from policy_platform.infrastructure.quality import ai_quality
from policy_platform.infrastructure.quality.policy_faithfulness import validate_rules
from tests.fixtures.factories import make_rule


def _rule(
    rule_id: str,
    *,
    source: str,
    action: str,
    subject: str = "Annual increase",
    condition: str = "",
):
    """A rule carrying the formulation the faithfulness pass reads."""

    rule = make_rule(
        rule_id,
        AllCondition(all=[]),
        effect_type=EffectType.REQUIRE_ACTION,
        effect_action=action,
    )
    rule.formulation = RuleFormulation(
        source_index=0,
        canonical=CanonicalPolicy(
            source_text=source,
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject=subject,
                predicate="exceed",
                condition=condition,
            ),
        ),
        dmn_decisions=[],
    )
    return rule


#: The inversion, verbatim from the extracted handbook that prompted the check.
_INVERTED = _rule(
    "R-INVERTED",
    source="3.2.1. Annual increase which shall not exceed 10% of the current basic salary.",
    action="exceed 10% of the current basic salary",
)

#: A limit the source states and the rule does not carry.
_DROPPED_QUANTITY = _rule(
    "R-DROPPED",
    source="Increase due to inflation with a percentage not exceeding 5% of basic salary.",
    action="be increased due to inflation",
)


def _categories(rules) -> set[str]:
    return {f["category"] for f in ai_quality._deterministic_findings(rules)}


def test_the_detector_still_sees_the_inversion():
    """Positive control. If this fails the check itself has been broken."""

    codes = {f.code for f in validate_rules([_INVERTED])}
    assert "negation_dropped" in codes, (
        "the faithfulness pass no longer reports a stripped negation, so the "
        f"test below would pass on silence; it reported {codes!r}"
    )


def test_the_detector_still_sees_a_dropped_limit():
    """Positive control for the second code the report must carry."""

    codes = {f.code for f in validate_rules([_DROPPED_QUANTITY])}
    assert "quantity_dropped" in codes, (
        "the faithfulness pass no longer reports a dropped limit; "
        f"it reported {codes!r}"
    )


def test_an_inverted_obligation_reaches_the_quality_report():
    """The finding a reviewer most needs, on a surface a reviewer reads.

    This is the whole point. The extraction already knew this rule instructs
    the opposite of its source, and said so to a log file.
    """

    assert "negation_dropped" in _categories([_INVERTED])


def test_a_dropped_limit_reaches_the_quality_report():
    assert "quantity_dropped" in _categories([_DROPPED_QUANTITY])


def test_a_faithful_rule_raises_no_faithfulness_finding():
    """The check must stay quiet on a rule that is faithful to its source.

    A detector that fires on everything is the failure mode this repository
    keeps rediscovering: a finding raised against nearly every record teaches a
    reviewer to ignore findings.
    """

    faithful = _rule(
        "R-OK",
        source="Annual increase shall not exceed 10% of the current basic salary.",
        action="not exceed 10% of the current basic salary",
    )

    codes = {f.code for f in validate_rules([faithful])}
    assert codes == set(), f"the faithfulness pass fired on a faithful rule: {codes!r}"


def test_the_ordinary_route_is_not_reported_as_a_finding():
    """`condition_not_compiled` is deliberately kept out of the report.

    It fires when a source states a condition that no fact model compiles --
    the ordinary outcome on prose, and the route most records correctly take.
    A finding raised for it would fire on a large share of every run, and the
    per-record route note already tells the reviewer this in wording that does
    not treat the outcome as a shortfall.

    Pinned because it is a judgement, and a judgement left implicit reads later
    as an oversight.
    """

    stated_in_words = _rule(
        "R-WORDS",
        source=(
            "Where an employee has completed the probation period, the manager "
            "shall record the outcome."
        ),
        action="record the outcome",
        subject="Manager",
        condition="the employee has completed the probation period",
    )

    codes = {f.code for f in validate_rules([stated_in_words])}
    assert "condition_not_compiled" in codes, (
        "the detector no longer raises this code, so the exclusion below proves "
        f"nothing; it reported {codes!r}"
    )
    assert "condition_not_compiled" not in _categories([stated_in_words])


def test_every_faithfulness_finding_carries_what_the_report_renders():
    """A finding missing a field renders as a blank row rather than an absence.

    The report's consumers read `severity`, `category`, `finding`,
    `affected_rule_ids` and `recommendation`. A finding that reached the
    surface without one of them would be visible and unreadable, which is a
    worse outcome than the log line it replaced.
    """

    findings = [
        f
        for f in ai_quality._deterministic_findings([_INVERTED, _DROPPED_QUANTITY])
        if f["category"] in {"negation_dropped", "quantity_dropped"}
    ]
    assert findings, "no faithfulness finding reached the report at all"
    for finding in findings:
        for field in ("severity", "category", "finding", "recommendation"):
            assert finding.get(field), f"{finding['category']} has no {field}"
        assert finding["affected_rule_ids"], f"{finding['category']} names no rule"
        assert finding["source"] == "deterministic"
