"""Tests for the quality-evaluation report.

The property under test throughout is that the report describes what actually
happened. A quality report is read as evidence about a policy set, so a review
that silently failed must not leave behind a report that looks like a clean
bill of health: fewer findings plus an "AI review" label reads as "we looked
and found little", which is the opposite of the truth.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import AmbiguityStatus, EffectType, RuleType
from policy_platform.infrastructure import ai_quality
from tests.fixtures.factories import make_rule


def _rule(rule_id: str = "R1"):
    return make_rule(
        rule_id, FactComparisonCondition(fact="amount", operator=ConditionOperator.EXISTS, value=None)
    )


class _Settings:
    def __init__(self, ai_enabled: bool = True) -> None:
        self.ai_enabled = ai_enabled
        self.azure_openai_deployment = "test-deployment"


class TestAiReviewOutcomeIsReported:
    """`_run_ai_review` reports whether the review happened, not whether it was asked for."""

    @pytest.mark.asyncio
    async def test_successful_review_reports_true_and_tags_its_findings(self, monkeypatch) -> None:
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())

        class _Client:
            def __init__(self, settings) -> None:
                pass

            async def chat(self, *args, **kwargs) -> str:
                return '{"findings": [{"severity": "high", "finding": "overlap"}]}'

        monkeypatch.setattr(ai_quality, "AzureOpenAIClient", _Client)

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([_rule()], findings, "set-a")

        assert used is True
        assert [f["source"] for f in findings] == ["ai_review"]
        assert findings[0]["analysis_status"] == "requires_human_confirmation"
        assert findings[0]["summary"] == "overlap"

    @pytest.mark.asyncio
    async def test_review_discards_findings_that_only_reference_unknown_rules(self, monkeypatch) -> None:
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())

        class _Client:
            def __init__(self, settings) -> None:
                pass

            async def chat(self, *args, **kwargs) -> str:
                return (
                    '{"findings": [{"severity": "high", "finding": "unsupported", '
                    '"affected_rule_ids": ["NOT-A-REAL-RULE"]}]}'
                )

        monkeypatch.setattr(ai_quality, "AzureOpenAIClient", _Client)

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([_rule("R1")], findings, "set-a")

        assert used is True
        assert findings == []

    def test_review_discards_partially_unsupported_rule_references(self) -> None:
        normalized = ai_quality._normalize_ai_finding(
            {
                "severity": "high",
                "finding": "R1 conflicts with a fabricated rule.",
                "affected_rule_ids": ["R1", "NOT-A-REAL-RULE"],
            },
            {"R1"},
        )

        assert normalized is None

    def test_review_discards_non_array_rule_references(self) -> None:
        normalized = ai_quality._normalize_ai_finding(
            {
                "severity": "high",
                "finding": "Malformed evidence reference.",
                "affected_rule_ids": "NOT-A-REAL-RULE",
            },
            {"R1"},
        )

        assert normalized is None

    def test_structured_review_fields_are_preserved_and_bounded(self) -> None:
        normalized = ai_quality._normalize_ai_finding(
            {
                "severity": "medium",
                "category": "decision_gap",
                "summary": "The equality boundary is undecided.",
                "finding": "R1 covers below the boundary while R2 covers above it.",
                "why_it_matters": "The evaluator can return no decision.",
                "acceptable_when": "The equality input cannot occur.",
                "unacceptable_when": "The equality input is reachable.",
                "review_questions": ["Which outcome owns equality?"],
                "affected_rule_ids": ["R1", "R2"],
                "recommendation": "Assign equality to one rule.",
            },
            {"R1", "R2"},
        )

        assert normalized is not None
        assert normalized["affected_rule_ids"] == ["R1", "R2"]
        assert normalized["why_it_matters"] == "The evaluator can return no decision."
        assert normalized["acceptable_when"] == "The equality input cannot occur."
        assert normalized["unacceptable_when"] == "The equality input is reachable."
        assert normalized["review_questions"] == ["Which outcome owns equality?"]
        assert normalized["analysis_status"] == "requires_human_confirmation"

    @pytest.mark.asyncio
    async def test_failed_review_reports_false_and_says_so_in_the_report(self, monkeypatch) -> None:
        """A swallowed failure must still be visible to whoever reads the report.

        Without a finding, the only trace of the failure is a server log line,
        and the report shows fewer findings than a successful run -- which reads
        as a *better* policy set rather than an incomplete review.
        """
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())

        class _Client:
            def __init__(self, settings) -> None:
                pass

            async def chat(self, *args, **kwargs) -> str:
                raise RuntimeError("context window exceeded")

        monkeypatch.setattr(ai_quality, "AzureOpenAIClient", _Client)

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([_rule()], findings, "set-a")

        assert used is False
        assert len(findings) == 1
        assert findings[0]["category"] == "review_coverage"
        assert "context window exceeded" in findings[0]["finding"]

    @pytest.mark.asyncio
    async def test_review_that_finds_nothing_still_counts_as_having_run(self, monkeypatch) -> None:
        """"The AI found no problems" and "the AI never ran" are different facts.

        The return value tracks completion, not finding count, so an genuinely
        clean policy set is not mislabelled as an unreviewed one.
        """
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())

        class _Client:
            def __init__(self, settings) -> None:
                pass

            async def chat(self, *args, **kwargs) -> str:
                return '{"findings": []}'

        monkeypatch.setattr(ai_quality, "AzureOpenAIClient", _Client)

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([_rule()], findings, "set-a")

        assert used is True
        assert findings == []

    @pytest.mark.asyncio
    async def test_ai_disabled_is_surfaced_as_a_coverage_gap(self, monkeypatch) -> None:
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings(ai_enabled=False))

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([_rule()], findings, "set-a")

        assert used is False
        assert findings[0]["category"] == "review_coverage"

    @pytest.mark.asyncio
    async def test_no_rules_is_not_reported_as_a_coverage_gap(self, monkeypatch) -> None:
        """Nothing to review is not the same as a review that should have run.

        An empty policy set would otherwise collect a finding on every
        evaluation, which is noise rather than signal.
        """
        monkeypatch.setattr(ai_quality, "get_settings", lambda: _Settings())

        findings: list[dict] = []
        used = await ai_quality._run_ai_review([], findings, "set-a")

        assert used is False
        assert findings == []


class TestSystemicCausesAreReportedOnce:
    """Findings that share one cause are reported once, with the cause named.

    A quality report is read top-down. Emitting one row per affected rule for a
    systemic cause states the symptom N times, never states the cause, and
    pushes genuinely independent problems off the end of the list.
    """

    def test_non_executable_rules_collapse_to_one_finding(self) -> None:
        rules = [_rule(f"R{i}") for i in range(50)]
        for r in rules:
            r.machine_executable = False

        findings = ai_quality._deterministic_findings(rules)
        exec_findings = [f for f in findings if f["category"] == "not_machine_executable"]

        assert len(exec_findings) == 1
        assert "50 of 50" in exec_findings[0]["finding"]
        assert len(exec_findings[0]["affected_rule_ids"]) == 50

    def test_the_collapsed_finding_names_the_enrichment_the_agent_asked_for(self) -> None:
        """The requirement codes are the actionable half of the finding.

        Their documented purpose is to make a non-executable projection
        "actionable rather than a dead end"; leaving them in the payload while
        the report says only "not executable" discards that.
        """
        from policy_platform.contracts.formulation import (
            CanonicalPolicy,
            DmnDecision,
            RuleFormulation,
        )

        rules = [_rule("R1"), _rule("R2")]
        for r in rules:
            r.machine_executable = False
            r.formulation = RuleFormulation(
                source_index=0,
                canonical=CanonicalPolicy(source_text="x"),
                dmn_decisions=[
                    DmnDecision(
                        source_rule_indexes=[0],
                        dmn_mapping_status="enrichment_required",
                        requirements=["FACT_MODEL_REQUIRED", "OUTPUT_MODEL_REQUIRED"],
                    )
                ],
            )

        findings = ai_quality._deterministic_findings(rules)
        exec_finding = next(f for f in findings if f["category"] == "not_machine_executable")

        assert "FACT_MODEL_REQUIRED" in exec_finding["finding"]
        assert "OUTPUT_MODEL_REQUIRED" in exec_finding["finding"]
        assert "enrichment_required" in exec_finding["finding"]
        assert exec_finding["severity"] == "high"

    def test_blocking_ambiguity_stays_per_rule(self) -> None:
        """Blocking ambiguity is not a backlog; each one halts a specific rule.

        Only the non-blocking queue is collapsed, so a blocking rule keeps its
        own row and its own rule_id.
        """
        blocking = _rule("R-block")
        blocking.ambiguity_status = AmbiguityStatus.BLOCKING
        backlog = [_rule(f"R{i}") for i in range(5)]
        for r in backlog:
            r.ambiguity_status = AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED

        findings = ai_quality._deterministic_findings([blocking, *backlog])
        amb = [f for f in findings if f["category"] == "ambiguity"]

        per_rule = [f for f in amb if f["affected_rule_ids"] == ["R-block"]]
        assert len(per_rule) == 1
        assert per_rule[0]["severity"] == "high"
        collapsed = [f for f in amb if len(f["affected_rule_ids"]) == 5]
        assert len(collapsed) == 1

    def test_a_clean_set_produces_no_systemic_findings(self) -> None:
        findings = ai_quality._deterministic_findings([_rule("R1"), _rule("R2")])
        assert [f for f in findings if f["category"] == "not_machine_executable"] == []
        assert [f for f in findings if f["category"] == "ambiguity"] == []

class TestDefinitionsCarryingEffects:
    """A definition authorizes nothing, and a negative one inverts its source."""

    @staticmethod
    def _rule(rid: str, rule_type: str, effect: str, executable: bool = False):
        return make_rule(
            rid,
            FactComparisonCondition(
                fact="x", operator=ConditionOperator.EQUALS, value=1
            ),
            effect_action="be included",
            effect_type=EffectType(effect),
            rule_type=RuleType(rule_type),
            machine_executable=executable,
        )

    def _findings(self, rules):
        return [
            f
            for f in ai_quality._deterministic_findings(rules)
            if f["category"] == "definition_carries_effect"
        ]

    def test_a_definition_with_an_allow_effect_is_reported(self) -> None:
        found = self._findings([self._rule("R1", "definition", "allow")])

        assert len(found) == 1
        assert "R1" in found[0]["affected_rule_ids"]

    def test_all_offenders_collapse_into_one_finding(self) -> None:
        """Consistent with the rest of this module: name the cause once."""

        rules = [self._rule(f"R{i}", "definition", "allow") for i in range(25)]

        found = self._findings(rules)

        assert len(found) == 1
        assert "25 definition rule(s)" in found[0]["finding"]

    def test_a_latent_defect_is_medium_and_says_so(self) -> None:
        found = self._findings([self._rule("R1", "definition", "allow")])

        assert found[0]["severity"] == "medium"
        assert "None are machine-executable" in found[0]["finding"]

    def test_an_executable_definition_is_high_and_says_so(self) -> None:
        """Executability is what turns the labelling error into a wrong answer."""

        found = self._findings(
            [self._rule("R1", "definition", "allow", executable=True)]
        )

        assert found[0]["severity"] == "high"
        assert "evaluator can" in found[0]["finding"]

    def test_non_definition_rules_are_left_alone(self) -> None:
        """A permission is supposed to allow; only definitions are the concern."""

        found = self._findings(
            [
                self._rule("R1", "permission", "allow"),
                self._rule("R2", "prohibition", "deny"),
            ]
        )

        assert found == []


class TestDegeneratePredicateFindings:
    """A predicate must name a relationship, not echo the source's delimiter."""

    @staticmethod
    def _with_predicate(rid: str, predicate: str | None):
        from policy_platform.contracts.formulation import (
            CanonicalPolicy,
            CanonicalPolicyRule,
            RuleFormulation,
        )

        rule = _rule(rid)
        canonical_rule = CanonicalPolicyRule(rule_type="definition", subject="Minor") if predicate is None else (
            CanonicalPolicyRule(rule_type="definition", subject="Minor", predicate=predicate)
        )
        rule.formulation = RuleFormulation(
            source_index=0,
            canonical=CanonicalPolicy(source_text="Minor: any person of 15 and below 18.", rule=canonical_rule),
        )
        return rule

    def _findings(self, rules):
        return [
            f
            for f in ai_quality._deterministic_findings(rules)
            if f["category"] == "degenerate_predicate"
        ]

    def test_a_colon_predicate_is_reported(self) -> None:
        found = self._findings([self._with_predicate("R1", ":")])

        assert len(found) == 1
        assert "R1" in found[0]["affected_rule_ids"]
        assert found[0]["severity"] == "medium"

    def test_a_dash_predicate_is_reported(self) -> None:
        found = self._findings([self._with_predicate("R1", "-")])

        assert len(found) == 1

    def test_all_offenders_collapse_into_one_finding(self) -> None:
        rules = [self._with_predicate(f"R{i}", ":") for i in range(10)]

        found = self._findings(rules)

        assert len(found) == 1
        assert "10 rule(s)" in found[0]["finding"]

    def test_a_real_predicate_is_not_reported(self) -> None:
        found = self._findings([self._with_predicate("R1", "is defined as")])

        assert found == []

    def test_no_predicate_at_all_is_not_reported(self) -> None:
        """Absent is fine per Section 21; only a present-but-punctuation value is a defect."""

        found = self._findings([self._with_predicate("R1", None)])

        assert found == []


class TestEligibilityPolarityFindings:
    """A `deny` effect that names a grant reads as denying the grant it describes."""

    @staticmethod
    def _rule(rid: str, effect_type: str, action: str, rule_type: str = "eligibility"):
        return make_rule(
            rid,
            FactComparisonCondition(fact="x", operator=ConditionOperator.EQUALS, value=1),
            effect_action=action,
            effect_type=EffectType(effect_type),
            rule_type=RuleType(rule_type),
        )

    def _findings(self, rules):
        return [
            f
            for f in ai_quality._deterministic_findings(rules)
            if f["category"] == "eligibility_polarity_inversion"
        ]

    def test_deny_plus_exemption_action_is_reported(self) -> None:
        found = self._findings(
            [
                self._rule(
                    "R1",
                    "deny",
                    "be exempted from the implementation of the provisions of this Law",
                )
            ]
        )

        assert len(found) == 1
        assert "R1" in found[0]["affected_rule_ids"]
        assert found[0]["severity"] == "high"

    def test_all_offenders_collapse_into_one_finding(self) -> None:
        rules = [self._rule(f"R{i}", "deny", "be exempted from coverage") for i in range(6)]

        found = self._findings(rules)

        assert len(found) == 1
        assert "6 eligibility rule(s)" in found[0]["finding"]

    def test_genuine_ineligibility_is_not_reported(self) -> None:
        """'Not eligible for the bonus' is a real denial — no grant-shaped word present."""

        found = self._findings([self._rule("R1", "deny", "receive the bonus")])

        assert found == []

    def test_allow_side_exemption_is_not_reported(self) -> None:
        """The correctly-classified version of the same rule must not itself be flagged."""

        found = self._findings(
            [
                self._rule(
                    "R1",
                    "allow",
                    "be exempted from the implementation of the provisions of this Law",
                )
            ]
        )

        assert found == []

    def test_non_eligibility_rule_types_are_left_alone(self) -> None:
        found = self._findings(
            [self._rule("R1", "deny", "be exempted from this obligation", rule_type="prohibition")]
        )

        assert found == []
