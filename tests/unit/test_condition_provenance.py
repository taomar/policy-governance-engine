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
from policy_platform.infrastructure.extraction.formulation_mapping import (
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

    def test_stated_conditions_that_were_not_projected_are_distinguished(self) -> None:
        """The dangerous case: the tree says 'always', the document does not."""

        provenance = condition_provenance(_policy("for every emergency grant"), None)

        assert provenance.code == "conditions_not_projected"

    def test_a_genuinely_unconditional_rule_is_distinguished(self) -> None:
        provenance = condition_provenance(_policy(None), None)

        assert provenance.code == "no_scope_derived"

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
        never stated — the same fabrication the pointer-only design prevents.

        Checked on the record rather than on wording: the provenance reports a
        code, and the rule it describes keeps whatever tree it actually had.
        Nothing here may manufacture one.
        """

        provenance = condition_provenance(_policy("only for P1 incidents"), None)

        assert provenance.code == "conditions_not_projected"
        assert provenance.unsupported_expression == ""
        assert not hasattr(provenance, "message")


class TestReviewRouting:
    def test_the_projection_never_reaches_ambiguity(self) -> None:
        """Whether a rule compiles says nothing about whether it is clear.

        These were once folded together, so a plainly worded rule carried the
        same flag as a genuinely vague one purely because nothing mapped its
        terms — true of nearly every rule, which left the flag with no signal
        while still demanding attention on every row.
        """

        for code in ("conditions_not_projected", "conditions_not_representable",
                     "no_scope_derived", "derived"):
            assert _ambiguity_for(_policy("only for P1"), False, code) is AmbiguityStatus.NONE

    def test_an_executable_rule_is_unflagged(self) -> None:
        assert _ambiguity_for(_policy("only for P1"), True, "derived") is AmbiguityStatus.NONE

    def test_genuine_source_ambiguity_still_wins(self) -> None:
        """A vague clause is a content problem regardless of projection."""

        policy = _policy("only for P1", extraction_status=ExtractionStatus.AMBIGUOUS)
        assert (
            _ambiguity_for(policy, True, "derived") is AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
        )

    def test_an_incomplete_extraction_is_still_reported(self) -> None:
        """The extractor saying it could not finish is about the document."""

        policy = _policy("x", extraction_status=ExtractionStatus.INCOMPLETE)
        assert _ambiguity_for(policy, True, "derived") is AmbiguityStatus.NON_BLOCKING

    def test_the_default_argument_carries_no_verdict(self) -> None:
        """Callers that pass no provenance get the same answer as any other."""

        assert _ambiguity_for(_policy(None), False) is AmbiguityStatus.NONE
        assert _ambiguity_for(_policy("x"), True) is AmbiguityStatus.NONE
