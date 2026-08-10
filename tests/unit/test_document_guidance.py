"""Statements about the document itself, kept out of the enforceable rule set.

A policy statement's subject is an actor or thing the document regulates. When
the subject is the document — "This template is provided as a tool for
community foundations to develop policies" — the sentence describes what the
document is and how to read it. It governs nobody.

Left unhandled, such a sentence became an enforceable rule: "Those policies
will be so noted at the beginning of each policy" mapped to a routing rule with
REQUIRE_ACTION, instructing a decision point to carry out a drafting
convention.

These tests pin both the detection and, more importantly, its boundary: the
signal is grammatical, and the cost of widening it is real rules being demoted.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import CanonicalPolicy, CanonicalPolicyRule
from policy_platform.contracts.formulation import CanonicalRuleType
from policy_platform.contracts.policy import EffectType, RuleType
from policy_platform.infrastructure.formulation_mapping import (
    DOCUMENT_GUIDANCE_TAG,
    is_document_guidance,
)


def _rule(subject: str, rule_type: CanonicalRuleType = CanonicalRuleType.OBLIGATION):
    return CanonicalPolicyRule(rule_type=rule_type, subject=subject)


class TestIsDocumentGuidance:
    @pytest.mark.parametrize(
        "subject",
        [
            "This template",
            "This policy",
            "These policies",
            "Those policies",
            "This document",
            "This Handbook",
            "The present agreement",
            "this section",
            "This Appendix",
        ],
    )
    def test_document_as_subject_is_guidance(self, subject: str):
        assert is_document_guidance(_rule(subject)) is True

    @pytest.mark.parametrize(
        "subject",
        [
            "An employee",
            "The Foundation",
            "Security incidents",
            "The ED/CEO",
            "Employees",
            "The policy owner",
        ],
    )
    def test_actors_are_not_guidance(self, subject: str):
        assert is_document_guidance(_rule(subject)) is False

    @pytest.mark.parametrize(
        "subject",
        [
            # The document noun must END the subject. Otherwise the document
            # only qualifies a real actor, and demoting these would take actual
            # rules out of the enforceable set.
            "This policy owner",
            "This policy's approver",
            "These policy administrators",
            "This document custodian",
            # Not a determiner + document noun at all.
            "Thistle Corp",
            "The policyholder",
        ],
    )
    def test_document_qualifying_an_actor_is_not_guidance(self, subject: str):
        assert is_document_guidance(_rule(subject)) is False

    def test_missing_subject_is_not_guidance(self):
        assert is_document_guidance(_rule("")) is False

    def test_missing_rule_is_not_guidance(self):
        assert is_document_guidance(None) is False


class TestGuidanceProjection:
    """The rule is kept, tagged, and made non-enforcing — never dropped."""

    def _project(self, subject: str, rule_type: CanonicalRuleType):
        from policy_platform.contracts.formulation import (
            DmnProjection,
            PolicyFormulation,
        )
        from policy_platform.infrastructure.formulation_mapping import (
            formulation_to_candidate_rules,
        )

        formulation = PolicyFormulation(
            canonical_policies=[
                CanonicalPolicy(
                    source_text=f"{subject} states something.",
                    rule=_rule(subject, rule_type),
                )
            ],
            dmn_projection=DmnProjection(decisions=[]),
        )
        rules, skipped = formulation_to_candidate_rules(
            formulation,
            policy_set_id="ps",
            extraction_run_id="run",
            deployment_name="d",
            prompt_version="p",
            parser_version="v",
        )
        return rules, skipped

    def test_guidance_is_kept_for_review_not_skipped(self):
        rules, skipped = self._project("This template", CanonicalRuleType.OBLIGATION)

        # Deciding a sentence carries no policy is the reviewer's call. Skipping
        # would remove it from their view entirely.
        assert len(rules) == 1
        assert skipped == []

    def test_guidance_is_tagged(self):
        rules, _ = self._project("This template", CanonicalRuleType.OBLIGATION)

        assert DOCUMENT_GUIDANCE_TAG in rules[0].tags

    def test_guidance_does_not_require_action(self):
        # The defect: an obligation about the document told a decision point to
        # carry out a drafting convention.
        rules, _ = self._project("Those policies", CanonicalRuleType.OBLIGATION)

        assert rules[0].effect.type == EffectType.INFORMATIONAL
        assert rules[0].rule_type == RuleType.DEFINITION

    def test_guidance_never_denies(self):
        rules, _ = self._project("This policy", CanonicalRuleType.PROHIBITION)

        assert rules[0].effect.type == EffectType.INFORMATIONAL

    def test_real_rule_keeps_its_effect(self):
        rules, _ = self._project("An employee", CanonicalRuleType.OBLIGATION)

        assert rules[0].effect.type == EffectType.REQUIRE_ACTION
        assert DOCUMENT_GUIDANCE_TAG not in rules[0].tags


class TestCalculationIsNotAnObligation:
    """A rule that derives a value does not oblige anyone to act.

    "The housing allowance is calculated as twice the monthly basic salary up to
    a maximum of..." became an Obligation whose action was the sentence fragment
    "is calculated as twice the monthly basic salary up to a maximum of" — an
    instruction no decision point can carry out. Under XACML §7.18 an Obligation
    is work a PEP must discharge, and a derived amount is not work.
    """

    def _project(self, rule_type: CanonicalRuleType):
        from policy_platform.contracts.formulation import DmnProjection, PolicyFormulation
        from policy_platform.infrastructure.formulation_mapping import (
            formulation_to_candidate_rules,
        )

        formulation = PolicyFormulation(
            canonical_policies=[
                CanonicalPolicy(
                    source_text="The allowance is calculated as twice the basic salary.",
                    rule=CanonicalPolicyRule(
                        rule_type=rule_type,
                        subject="The housing allowance",
                        predicate="is calculated as",
                        object="twice the monthly basic salary",
                    ),
                )
            ],
            dmn_projection=DmnProjection(decisions=[]),
        )
        rules, _ = formulation_to_candidate_rules(
            formulation,
            policy_set_id="ps",
            extraction_run_id="run",
            deployment_name="d",
            prompt_version="p",
            parser_version="v",
        )
        return rules

    def test_calculation_is_informational(self):
        rules = self._project(CanonicalRuleType.CALCULATION)

        assert rules[0].effect.type == EffectType.INFORMATIONAL
        assert rules[0].rule_type == RuleType.CALCULATION

    def test_obligation_still_requires_action(self):
        # The boundary: correcting calculation must not quietly disarm the rules
        # that genuinely do oblige a decision point to act.
        rules = self._project(CanonicalRuleType.OBLIGATION)

        assert rules[0].effect.type == EffectType.REQUIRE_ACTION
