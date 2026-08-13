"""Tests for the deterministic parts of correlation analysis.

The model call itself is not tested here — what is tested is everything the
application is responsible for: which rules get compared, how the reply is
parsed, how positions become identifiers, and how repeated findings are
collapsed. Those are the parts that decide whether a real contradiction is found
at all, and they are decided before the model is ever asked.
"""
from __future__ import annotations

import json
import sys

import pytest

from policy_platform.contracts.correlation import (
    ACTIONABLE_CLASSIFICATIONS,
    CorrelationAnalysis,
    CorrelationFinding,
)
from policy_platform.infrastructure.correlation.correlation_agent import (
    CorrelationError,
    _render_rule,
    finding_key,
    group_rules_for_comparison,
    groupable_rule_ids,
    parse_analysis,
    resolve_indexes,
    rule_signals,
)


def rule(
    rule_id: str,
    *,
    action: str = "",
    effect_type: str = "",
    personas: list[str] | None = None,
    units: list[str] | None = None,
    processes: list[str] | None = None,
    facts: list[str] | None = None,
    tags: list[str] | None = None,
    group_label: str = "",
    aggregates: list[str] | None = None,
) -> tuple[str, dict]:
    payload: dict = {"rule_id": rule_id}
    if action or effect_type:
        payload["effect"] = {"action": action, "type": effect_type}
    scope: dict = {}
    if personas:
        scope["personas"] = personas
    if units:
        scope["organizational_units"] = units
    if processes:
        scope["processes"] = processes
    if scope:
        payload["scope"] = scope
    if facts:
        payload["required_facts"] = [{"name": f} for f in facts]
    if tags:
        payload["tags"] = tags
    if group_label:
        payload["group_label"] = group_label
    if aggregates:
        payload["aggregate_limits"] = [{"aggregate_id": a} for a in aggregates]
    return rule_id, payload


# --------------------------------------------------------------------------
# rule_signals
# --------------------------------------------------------------------------


class TestRuleSignals:
    def test_action_produces_signal(self) -> None:
        _, payload = rule("R1", action="grant annual leave")
        assert any(s.startswith("action:") for s in rule_signals(payload))

    def test_word_order_does_not_change_the_signal(self) -> None:
        """"manager approval" and "approval of the manager" name one thing.

        If word order changed the signal, the two rules would never be brought
        together and a contradiction between them would go unreported.
        """
        _, a = rule("R1", action="manager approval")
        _, b = rule("R2", action="approval of the manager")
        assert rule_signals(a) & rule_signals(b)

    def test_signals_are_namespaced_by_dimension(self) -> None:
        """An action named "leave" must not collide with a tag named "leave"."""
        _, action_rule = rule("R1", action="leave")
        _, tag_rule = rule("R2", tags=["leave"])
        assert not (rule_signals(action_rule) & rule_signals(tag_rule))

    def test_opposite_effects_on_one_action_still_share_a_signal(self) -> None:
        """Permit-vs-deny on the same action is the likeliest contradiction.

        The typed `effect:` signal separates them, so the untyped `action:`
        signal is what keeps them comparable. Lexical `term:` signals also
        match here — the two rules genuinely describe the same subject — but
        they are a fallback for untagged prose, so the structured signal must
        be present on its own merits and is asserted directly.
        """
        _, permit = rule("R1", action="take annual leave", effect_type="permit")
        _, deny = rule("R2", action="take annual leave", effect_type="deny")
        shared = rule_signals(permit) & rule_signals(deny)
        assert any(s.startswith("action:") for s in shared)
        assert not any(s.startswith("effect:") for s in shared)

    def test_shared_fact_is_a_signal(self) -> None:
        _, a = rule("R1", facts=["employee.tenure_months"])
        _, b = rule("R2", facts=["employee.tenure_months"])
        assert "fact:employee.tenure_months" in rule_signals(a) & rule_signals(b)

    def test_shared_aggregate_is_a_signal(self) -> None:
        _, a = rule("R1", aggregates=["annual_leave_cap"])
        _, b = rule("R2", aggregates=["annual_leave_cap"])
        assert "aggregate:annual_leave_cap" in rule_signals(a) & rule_signals(b)

    def test_empty_payload_yields_no_signals(self) -> None:
        assert rule_signals({}) == set()

    def test_stopwords_alone_yield_no_signal(self) -> None:
        _, payload = rule("R1", action="the of and")
        assert not any(s.startswith("action:") for s in rule_signals(payload))

    def test_untagged_prose_rules_still_share_a_signal(self) -> None:
        """The case the structured signals miss entirely.

        Extracted legislation carries no tags, personas or fact model, and its
        action is a whole clause rather than a normalized phrase. Without
        lexical signals two rules on the same subject share nothing and are
        never compared.
        """
        _, a = rule("R1", action="the employer shall grant annual leave of 21 days")
        _, b = rule("R2", action="annual leave shall not exceed 30 days per year")
        shared = rule_signals(a) & rule_signals(b)
        assert shared
        assert all(s.startswith("term:") for s in shared)

    def test_lexical_signals_use_the_rule_title(self) -> None:
        """Title is often the only populated text on a sparse rule."""
        a = {"rule_id": "R1", "title": "Overtime compensation entitlement"}
        b = {"rule_id": "R2", "title": "Overtime compensation ceiling"}
        assert rule_signals(a) & rule_signals(b)

    def test_lexical_signals_include_word_pairs(self) -> None:
        """"annual leave" identifies a subject; "leave" alone barely does."""
        _, payload = rule("R1", action="grant annual leave")
        assert "term:annual leave" in rule_signals(payload)

    def test_short_words_are_not_lexical_signals(self) -> None:
        """Three-letter tokens match too much to be evidence of anything."""
        _, payload = rule("R1", action="pay tax now")
        assert not any(s == "term:pay" or s == "term:tax" for s in rule_signals(payload))


# --------------------------------------------------------------------------
# group_rules_for_comparison
# --------------------------------------------------------------------------


class TestGrouping:
    def test_rules_sharing_a_signal_are_grouped(self) -> None:
        rules = [
            rule("R1", action="take annual leave", effect_type="permit"),
            rule("R2", action="take annual leave", effect_type="deny"),
        ]
        groups = group_rules_for_comparison(rules)
        assert groups
        assert {"R1", "R2"} <= {rid for g in groups for rid, _ in g}

    def test_unrelated_rules_are_not_grouped(self) -> None:
        rules = [
            rule("R1", action="approve expense claim"),
            rule("R2", action="issue laptop"),
        ]
        assert group_rules_for_comparison(rules) == []

    def test_a_lone_rule_is_never_a_group(self) -> None:
        """A group of one has nothing to compare, so it is not worth a call."""
        assert group_rules_for_comparison([rule("R1", action="grant leave")]) == []

    def test_groups_are_capped(self) -> None:
        rules = [rule(f"R{i}", tags=["payroll"]) for i in range(40)]
        groups = group_rules_for_comparison(rules, max_group_size=12)
        assert groups
        assert all(len(g) <= 12 for g in groups)

    def test_no_rule_is_stranded_by_chunking(self) -> None:
        """A trailing chunk of one must not silently drop that rule.

        13 rules at a cap of 12 used to produce a group of 12 and a group of 1;
        the second was discarded and rule 13 was never compared under that
        signal.
        """
        rules = [rule(f"R{i}", tags=["payroll"]) for i in range(13)]
        groups = group_rules_for_comparison(rules, max_group_size=12)
        grouped = {rid for g in groups for rid, _ in g}
        assert len(grouped) == 13

    def test_overly_common_signals_are_dropped(self) -> None:
        """A signal on 500 rules is a category, not evidence of interaction."""
        rules = [rule(f"R{i}", tags=["policy"]) for i in range(200)]
        assert group_rules_for_comparison(rules, max_rules_per_signal=60) == []

    def test_grouping_is_deterministic(self) -> None:
        """Section 114: the same set must produce the same groups every run."""
        rules = [
            rule("R1", action="grant leave", tags=["hr"]),
            rule("R2", action="grant leave", tags=["hr"]),
            rule("R3", action="deny leave", tags=["hr"]),
        ]
        first = group_rules_for_comparison(rules)
        second = group_rules_for_comparison(list(reversed(rules)))
        as_keys = lambda gs: sorted(tuple(sorted(r for r, _ in g)) for g in gs)  # noqa: E731
        assert as_keys(first) == as_keys(second)

    def test_identical_groups_are_emitted_once(self) -> None:
        """Two rules sharing five signals should not cost five model calls."""
        rules = [
            rule("R1", action="grant leave", tags=["hr"], facts=["x"], group_label="leave"),
            rule("R2", action="grant leave", tags=["hr"], facts=["x"], group_label="leave"),
        ]
        assert len(group_rules_for_comparison(rules)) == 1

    def test_total_groups_are_capped(self) -> None:
        """Cost is bounded by the number of calls, not just their size."""
        # Disjoint pairs: each tag is shared by exactly two rules, so every pair
        # survives the frequency filter and 100 groups are available.
        rules = [rule(f"R{i}", tags=[f"subject{i // 2}"]) for i in range(200)]
        assert len(group_rules_for_comparison(rules)) == 100
        assert len(group_rules_for_comparison(rules, max_groups=10)) == 10

    def test_the_cap_keeps_the_most_specific_groups(self) -> None:
        """When the budget runs out, vague comparisons are what should go.

        A signal shared by three rules says far more about them than one shared
        by twelve, so the narrow group must survive the cap.
        """
        rules = [rule(f"C{i}", tags=["common"]) for i in range(12)]
        rules += [rule(f"N{i}", tags=["common", "narrow"]) for i in range(3)]
        groups = group_rules_for_comparison(rules, max_groups=1)
        assert len(groups) == 1
        assert {rid for rid, _ in groups[0]} == {"N0", "N1", "N2"}


# --------------------------------------------------------------------------
# _render_rule
# --------------------------------------------------------------------------


class TestRenderRule:
    def test_absent_fields_are_omitted_not_blanked(self) -> None:
        """Section 90: a half-populated field invites the model to complete it."""
        record = _render_rule({"rule_id": "R1"})
        assert "priority" not in record
        assert "supersedes" not in record

    def test_present_fields_survive(self) -> None:
        record = _render_rule(
            {"rule_id": "R1", "priority": 10, "supersedes_rule_ids": ["R0"]}
        )
        assert record["priority"] == 10
        assert record["supersedes"] == ["R0"]


# --------------------------------------------------------------------------
# parse_analysis
# --------------------------------------------------------------------------


def _finding(**over) -> dict:
    base = {
        "finding_id": "F1",
        "policy_indexes": [0, 1],
        "classification": "DIRECT_CONTRADICTION",
        "analysis_status": "confirmed",
        "severity": "high",
        "reason": "one permits what the other denies",
    }
    base.update(over)
    return base


class TestParseAnalysis:
    def test_parses_the_specified_envelope(self) -> None:
        raw = json.dumps({"policy_conflict_analysis": {"findings": [_finding()]}})
        analysis = parse_analysis(raw)
        assert len(analysis.findings) == 1
        assert analysis.findings[0].classification == "DIRECT_CONTRADICTION"

    def test_accepts_a_bare_body(self) -> None:
        """A correct analysis should not be discarded over a missing envelope."""
        raw = json.dumps({"findings": [_finding()]})
        assert len(parse_analysis(raw).findings) == 1

    def test_strips_a_code_fence(self) -> None:
        raw = "```json\n" + json.dumps({"findings": [_finding()]}) + "\n```"
        assert len(parse_analysis(raw).findings) == 1

    def test_empty_response_raises(self) -> None:
        with pytest.raises(CorrelationError, match="empty"):
            parse_analysis("   ")

    def test_unparseable_json_raises(self) -> None:
        with pytest.raises(CorrelationError, match="unparseable"):
            parse_analysis("{not json")

    def test_a_json_array_raises(self) -> None:
        with pytest.raises(CorrelationError, match="expected a JSON object"):
            parse_analysis("[1, 2, 3]")

    def test_unknown_classification_is_rejected(self) -> None:
        """The vocabulary is closed: an invented label cannot be triaged."""
        raw = json.dumps({"findings": [_finding(classification="VIBES_MISMATCH")]})
        with pytest.raises(CorrelationError, match="contract validation"):
            parse_analysis(raw)

    def test_confidence_scores_are_ignored(self) -> None:
        """Section 53 bans them; a model that emits one must not smuggle it in."""
        raw = json.dumps({"findings": [_finding(confidence=0.91)]})
        finding = parse_analysis(raw).findings[0]
        assert not hasattr(finding, "confidence")

    def test_no_findings_is_a_valid_analysis(self) -> None:
        """"These rules are consistent" is an answer, not a failure."""
        assert parse_analysis(json.dumps({"findings": []})).findings == []


# --------------------------------------------------------------------------
# resolve_indexes
# --------------------------------------------------------------------------


class TestResolveIndexes:
    def test_indexes_become_rule_ids(self) -> None:
        analysis = CorrelationAnalysis.model_validate({"findings": [_finding()]})
        resolved, problems = resolve_indexes(analysis, ["R1", "R2"])
        assert problems == []
        assert resolved[0].rule_ids == ["R1", "R2"]

    def test_out_of_range_index_drops_the_finding(self) -> None:
        """An unresolvable index accuses a rule that was never sent.

        Clamping it to the nearest valid position would attribute a
        contradiction to an innocent rule, which is worse than losing it.
        """
        analysis = CorrelationAnalysis.model_validate({"findings": [_finding(policy_indexes=[0, 9])]})
        resolved, problems = resolve_indexes(analysis, ["R1", "R2"])
        assert resolved == []
        assert problems and "out-of-range" in problems[0]

    def test_negative_index_drops_the_finding(self) -> None:
        analysis = CorrelationAnalysis.model_validate({"findings": [_finding(policy_indexes=[-1, 0])]})
        resolved, _ = resolve_indexes(analysis, ["R1", "R2"])
        assert resolved == []

    def test_a_finding_referencing_nothing_is_dropped(self) -> None:
        analysis = CorrelationAnalysis.model_validate(
            {"findings": [_finding(policy_indexes=[], evidence=[])]}
        )
        resolved, problems = resolve_indexes(analysis, ["R1", "R2"])
        assert resolved == []
        assert problems

    def test_indexes_fall_back_to_evidence(self) -> None:
        """The specification allows the reference to live on the evidence."""
        analysis = CorrelationAnalysis.model_validate(
            {
                "findings": [
                    _finding(
                        policy_indexes=[],
                        evidence=[{"policy_index": 0}, {"policy_index": 1}],
                    )
                ]
            }
        )
        resolved, _ = resolve_indexes(analysis, ["R1", "R2"])
        assert resolved[0].rule_ids == ["R1", "R2"]

    def test_evidence_gets_its_rule_id(self) -> None:
        analysis = CorrelationAnalysis.model_validate(
            {"findings": [_finding(evidence=[{"policy_index": 1, "source_text": "x"}])]}
        )
        resolved, _ = resolve_indexes(analysis, ["R1", "R2"])
        assert resolved[0].evidence[0].rule_id == "R2"

    def test_one_bad_finding_does_not_lose_the_good_ones(self) -> None:
        analysis = CorrelationAnalysis.model_validate(
            {"findings": [_finding(finding_id="ok"), _finding(finding_id="bad", policy_indexes=[7])]}
        )
        resolved, problems = resolve_indexes(analysis, ["R1", "R2"])
        assert [f.finding_id for f in resolved] == ["ok"]
        assert len(problems) == 1


# --------------------------------------------------------------------------
# finding_key
# --------------------------------------------------------------------------


class TestFindingKey:
    def _f(self, rule_ids: list[str], classification: str = "DIRECT_CONTRADICTION") -> CorrelationFinding:
        return CorrelationFinding(rule_ids=rule_ids, classification=classification)

    def test_order_does_not_matter(self) -> None:
        """"A contradicts B" and "B contradicts A" are one finding."""
        assert finding_key(self._f(["A", "B"])) == finding_key(self._f(["B", "A"]))

    def test_classification_distinguishes_findings(self) -> None:
        """One pair can hold two different relationships worth reporting."""
        assert finding_key(self._f(["A", "B"])) != finding_key(self._f(["A", "B"], "OVERLAP"))

    def test_different_pairs_differ(self) -> None:
        assert finding_key(self._f(["A", "B"])) != finding_key(self._f(["A", "C"]))


# --------------------------------------------------------------------------
# actionable classification set
# --------------------------------------------------------------------------


class TestActionableClassifications:
    def test_contradictions_are_actionable(self) -> None:
        assert "DIRECT_CONTRADICTION" in ACTIONABLE_CLASSIFICATIONS

    def test_benign_relationships_are_not(self) -> None:
        """`INDEPENDENT` is a correct answer that must not bury real findings."""
        assert "INDEPENDENT" not in ACTIONABLE_CLASSIFICATIONS
        assert "COMPATIBLE" not in ACTIONABLE_CLASSIFICATIONS

    def test_is_actionable_agrees_with_the_set(self) -> None:
        assert CorrelationFinding(classification="DIRECT_CONTRADICTION").is_actionable
        assert not CorrelationFinding(classification="INDEPENDENT").is_actionable


# --------------------------------------------------------------------------
# groupable_rule_ids
# --------------------------------------------------------------------------


class TestGroupableRuleIds:
    """Coverage must be attributable to a cause.

    "Not compared" has two causes that call for opposite responses: a rule that
    shares no signal with any other was never comparable and is nothing to act
    on, while a rule dropped by the group budget means the run was truncated and
    a larger budget would cover more. Reporting only the total let a truncated
    run read as a clean one, which is the more dangerous misreading.
    """

    def test_a_lone_rule_is_not_groupable(self) -> None:
        rules = [rule("R1", action="approve", tags=["unique-to-r1"])]

        assert groupable_rule_ids(rules) == set()

    def test_rules_sharing_a_signal_are_groupable(self) -> None:
        rules = [
            rule("R1", action="approve", tags=["expense"]),
            rule("R2", action="deny", tags=["expense"]),
        ]

        assert groupable_rule_ids(rules) == {"R1", "R2"}

    def test_result_is_independent_of_the_group_budget(self) -> None:
        """This is the whole point: the budget must not change the coverage
        denominator, or the two causes collapse back into one number."""

        rules = [
            rule("R1", tags=["alpha"]),
            rule("R2", tags=["alpha"]),
            rule("R3", tags=["beta"]),
            rule("R4", tags=["beta"]),
            rule("R5", tags=["gamma"]),
            rule("R6", tags=["gamma"]),
        ]

        groupable = groupable_rule_ids(rules)
        starved = group_rules_for_comparison(rules, max_groups=1)
        grouped = {rid for group in starved for rid, _ in group}

        assert groupable == {"R1", "R2", "R3", "R4", "R5", "R6"}
        assert len(grouped) < len(groupable)
        # The difference is precisely what the run should report as truncation.
        assert len(groupable - grouped) == 4

    def test_an_overly_common_signal_does_not_make_a_rule_groupable(self) -> None:
        """A signal shared by more rules than the per-signal ceiling is too vague
        for the grouper to use, so counting it as coverage would overstate what
        could ever be compared."""

        rules = [rule(f"R{i}", tags=["everything"]) for i in range(40)]

        assert groupable_rule_ids(rules, max_rules_per_signal=5) == set()

    def test_uncomparable_rules_are_excluded_but_comparable_ones_kept(self) -> None:
        rules = [
            rule("R1", tags=["shared"]),
            rule("R2", tags=["shared"]),
            rule("R3", tags=["alone"]),
        ]

        assert groupable_rule_ids(rules) == {"R1", "R2"}


class TestGroupBudgetIsAdvisory:
    """`max_groups` is checked once per signal, not once per group.

    A single signal can contribute several groups, so a run can finish holding
    more groups than its budget named. This is pinned because the correlation
    service reports `groups_available` from a separate unbounded call rather
    than by slicing the capped result, and that choice is only correct if the
    two are genuinely not interchangeable.
    """

    @staticmethod
    def _many_rules_sharing_one_signal(count: int) -> list[tuple[str, dict]]:
        return [rule(f"R{i}", tags=["shared"]) for i in range(count)]

    def test_a_run_can_hold_more_groups_than_its_budget(self) -> None:
        rules = self._many_rules_sharing_one_signal(30)

        groups = group_rules_for_comparison(rules, max_group_size=4, max_groups=1)

        assert len(groups) > 1

    def test_slicing_a_capped_result_is_not_the_same_as_capping(self) -> None:
        """The reason `groups_available` needs its own unbounded call."""

        rules = self._many_rules_sharing_one_signal(30)

        capped = group_rules_for_comparison(rules, max_group_size=4, max_groups=1)
        unbounded = group_rules_for_comparison(
            rules, max_group_size=4, max_groups=sys.maxsize
        )

        assert unbounded[:1] != capped
        assert len(unbounded) >= len(capped)

    def test_an_unbounded_call_reports_the_full_group_count(self) -> None:
        """What the service stores as `groups_available`."""

        rules = [
            rule("R1", tags=["a"]),
            rule("R2", tags=["a"]),
            rule("R3", tags=["b"]),
            rule("R4", tags=["b"]),
        ]

        unbounded = group_rules_for_comparison(rules, max_groups=sys.maxsize)

        assert len(unbounded) >= len(group_rules_for_comparison(rules, max_groups=1))
