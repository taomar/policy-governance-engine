"""Tests for condition provenance.

An unconditional rule and a rule whose conditions could not be projected both
end up with an empty `all: []` tree. That conflation is the dangerous one:
"applies always" and "has conditions we failed to encode" demand opposite
responses, and reading the second as the first turns a narrow permission into
an open one.

These tests pin the distinction, and pin that an empty tree is never "repaired"
by inventing a placeholder condition the document never stated.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    ExtractionStatus,
)
from policy_platform.infrastructure.formulation_mapping import (
    _ambiguity_for,
    condition_provenance,
)
from policy_platform.contracts.policy import AmbiguityStatus


def _policy(condition: str | None = None, **overrides) -> CanonicalPolicy:
    rule = CanonicalPolicyRule(
        rule_type=CanonicalRuleType.OBLIGATION,
        subject="IT",
        predicate="record",
        object="the grant time",
        condition=condition,
    )
    return CanonicalPolicy(source_text="IT must record the grant time.", rule=rule, **overrides)


class TestProvenanceClassification:
    def test_a_projected_condition_reports_derived(self) -> None:
        provenance = condition_provenance(_policy("when access is granted"), object())
        assert provenance.code == "derived"
        assert "projected" in provenance.message

    def test_stated_conditions_that_were_not_projected_are_distinguished(self) -> None:
        """The dangerous case: the tree says 'always', the document does not."""

        provenance = condition_provenance(_policy("for every emergency grant"), None)

        assert provenance.code == "conditions_not_projected"
        assert "for every emergency grant" in provenance.message
        assert "must not be treated as unconditional" in provenance.message

    def test_a_genuinely_unconditional_rule_is_distinguished(self) -> None:
        provenance = condition_provenance(_policy(None), None)

        assert provenance.code == "no_scope_derived"
        assert "may genuinely be" in provenance.message

    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_whitespace_only_conditions_count_as_absent(self, blank: str) -> None:
        assert condition_provenance(_policy(blank), None).code == "no_scope_derived"

    def test_the_two_empty_tree_cases_never_share_a_code(self) -> None:
        dropped = condition_provenance(_policy("only during business hours"), None).code
        unscoped = condition_provenance(_policy(None), None).code
        assert dropped != unscoped

    def test_a_rule_without_a_canonical_rule_is_handled(self) -> None:
        policy = CanonicalPolicy(source_text="Some narrative text.", rule=None)
        assert condition_provenance(policy, None).code == "no_scope_derived"

    def test_only_a_platform_limitation_reports_itself_as_one(self) -> None:
        """The flag the interface keys its wording on.

        Every other code asks a reviewer to supply something; this one asks
        them to wait for an engineering change, so telling them apart is the
        difference between useful work and a wasted afternoon.
        """

        assert condition_provenance(_policy("only for P1"), None).is_platform_limitation is False
        assert condition_provenance(_policy(None), None).is_platform_limitation is False
        assert condition_provenance(_policy("x"), object()).is_platform_limitation is False


class TestNoFabrication:
    def test_no_placeholder_condition_is_invented(self) -> None:
        """A synthesised always-false node would be a constraint the document
        never stated — the same fabrication the pointer-only design prevents."""

        message = condition_provenance(_policy("only for P1 incidents"), None).message

        assert "reviewer" in message
        # The message explains; it must not smuggle in an encoded condition.
        assert "false" not in message.lower()


class TestReviewRouting:
    def test_dropped_conditions_require_human_judgment(self) -> None:
        """Not merely unconfigured: the stored tree contradicts the source."""

        status = _ambiguity_for(_policy("only for P1"), False, "conditions_not_projected")
        assert status is AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED

    def test_an_unscoped_rule_is_non_blocking_not_a_content_problem(self) -> None:
        """Nothing about the wording is unclear; it simply is not executable."""

        status = _ambiguity_for(_policy(None), False, "no_scope_derived")
        assert status is AmbiguityStatus.NON_BLOCKING

    def test_an_executable_rule_is_unflagged(self) -> None:
        assert _ambiguity_for(_policy("only for P1"), True, "derived") is AmbiguityStatus.NONE

    def test_genuine_source_ambiguity_still_wins(self) -> None:
        """A vague clause is a content problem regardless of projection."""

        policy = _policy("only for P1", extraction_status=ExtractionStatus.AMBIGUOUS)
        assert (
            _ambiguity_for(policy, True, "derived") is AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
        )

    def test_the_default_preserves_prior_behaviour(self) -> None:
        """Callers that predate condition provenance must not change verdict."""

        assert _ambiguity_for(_policy(None), False) is AmbiguityStatus.NON_BLOCKING
        assert _ambiguity_for(_policy("x"), True) is AmbiguityStatus.NONE
