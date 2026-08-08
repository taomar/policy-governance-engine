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
from policy_platform.contracts.policy import AmbiguityStatus
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
