"""A negated sentence must never project as a permission.

The most dangerous output this system can produce is not a missing rule or an
unreadable one. It is a confident statement of the opposite of what the
document said — a record telling a reader that conduct the policy forbids is
permitted.

This has now been found twice, in two different places, from the same cause:
the rule *type* was read and the *modal word* was not. A sentence forbidding
something is frequently typed `conditional_outcome` or `obligation`, because
what it is about is an outcome or a duty; the "not" lives in the modality.
Classification that ignores the modality therefore loses the negation
entirely, and does so silently, because the result is well-formed either way.

Measured before the guard below existed, every rule in a live extraction
projected to Permit — including three whose source text reads "shall not
exceed…", "will not be enrolled…" and "will not bear any responsibility".

These tests are written against the projection's own contract rather than any
document, so they hold for whatever a customer uploads.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.xacml_projection import NormativeModality, RuleEffect
from policy_platform.infrastructure.xacml_projection import build_xacml_view


def _rule(rule_type: CanonicalRuleType, modality: str | None, **fields) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(rule_type=rule_type, modality=modality, **fields)


def _view(rule_type: CanonicalRuleType, modality: str | None, **fields):
    policy = CanonicalPolicy(
        source_text=fields.pop("source_text", "A stated rule."),
        rule=CanonicalPolicyRule(rule_type=rule_type, modality=modality, **fields),
    )
    return build_xacml_view(policy)


#: Every rule type that carries a positive normative force. A negation has to
#: overturn all of them, not the one that happened to be under test.
_POSITIVE_TYPES = [
    CanonicalRuleType.OBLIGATION,
    CanonicalRuleType.PERMISSION,
    CanonicalRuleType.ENTITLEMENT,
    CanonicalRuleType.ELIGIBILITY,
    CanonicalRuleType.CONDITIONAL_OUTCOME,
    CanonicalRuleType.CALCULATION,
]

#: Negations as policy prose writes them, across registers.
_NEGATIONS = ["shall not", "must not", "may not", "will not", "cannot", "shall never"]


@pytest.mark.parametrize("rule_type", _POSITIVE_TYPES)
@pytest.mark.parametrize("modality", _NEGATIONS)
def test_a_negated_modality_projects_as_deny(rule_type, modality):
    """The negation wins over the type, whatever the type is."""

    view = _view(rule_type, modality, subject="the party", predicate="exceed", object="the limit")

    assert view is not None
    assert view.source_semantics.normative_modality is NormativeModality.PROHIBITION
    assert view.xacml_projection.effect is RuleEffect.DENY


@pytest.mark.parametrize("rule_type", _POSITIVE_TYPES)
def test_an_unnegated_rule_is_unaffected(rule_type):
    """The control. A guard that denied everything would also pass the test above."""

    view = _view(rule_type, "shall", subject="the party", predicate="submit", object="the form")

    assert view is not None
    assert view.source_semantics.normative_modality is not NormativeModality.PROHIBITION
    assert view.xacml_projection.effect is not RuleEffect.DENY


@pytest.mark.parametrize("modality", [None, "", "   "])
def test_an_absent_modality_asserts_nothing(modality):
    """No modal word is not a negation, and must not be read as one."""

    view = _view(CanonicalRuleType.OBLIGATION, modality, subject="the party", predicate="submit")

    assert view is not None
    assert view.source_semantics.normative_modality is not NormativeModality.PROHIBITION


def test_a_definition_is_never_turned_into_a_prohibition():
    """"X does not mean Y" still defines; it forbids nothing.

    A definition is not a XACML Rule at all, so reading its negation as a
    prohibition would manufacture a decision the document never made.
    """

    view = _view(
        CanonicalRuleType.DEFINITION,
        "does not",
        subject="a term",
        predicate="mean",
        object="the other thing",
    )

    assert view is not None
    assert view.source_semantics.normative_modality is NormativeModality.DEFINITION
    assert view.xacml_projection.effect is None


def test_a_prohibition_type_stays_deny_without_a_modal_word():
    """The type is still evidence when the modality says nothing."""

    view = _view(CanonicalRuleType.PROHIBITION, None, subject="the party", predicate="disclose")

    assert view is not None
    assert view.xacml_projection.effect is RuleEffect.DENY


def test_the_negation_test_is_shared_with_the_rest_of_the_platform():
    """One definition of what counts as a negation, not two.

    `Effect.type` and this projection both have to answer the same question,
    and they answered it in different places once already. Two definitions is
    how one of them ends up not counting "may not".
    """

    from policy_platform.infrastructure.formulation_mapping import states_a_negation

    for modality in _NEGATIONS:
        assert states_a_negation(_rule(CanonicalRuleType.OBLIGATION, modality)) is True
        view = _view(CanonicalRuleType.OBLIGATION, modality, subject="a", predicate="do")
        assert view is not None
        assert view.xacml_projection.effect is RuleEffect.DENY


@pytest.mark.parametrize("predicate", ["not exceeding", "never granted", "not to be paid"])
def test_a_negation_written_into_the_predicate_still_forbids(predicate):
    """The sentence chooses the slot; the meaning is the same either way.

    "shall not exceed 10% of the base" and "not exceeding 5% of the base" state
    bounds of identical force. Reading only the modal word classified the first
    as a prohibition and the second as an obligation, so two such rules were
    badged "Prohibits" and "Requires" in one list — and the second told a
    decision point to carry out the very thing the document limits.
    """

    view = _view(
        CanonicalRuleType.CONDITIONAL_OUTCOME, None, subject="the increase", predicate=predicate
    )

    assert view is not None
    assert view.xacml_projection.effect is RuleEffect.DENY


@pytest.mark.parametrize(
    "predicate",
    ["no less than three months", "no later than the first working day", "no more than"],
)
def test_a_comparative_no_is_not_read_as_a_prohibition(predicate):
    """A floor obliges; it does not forbid.

    "no less than three months" requires at least three months. Reading its
    "no" as a negation would turn a requirement into a ban — the same inversion
    this module exists to prevent, arrived at from the opposite direction.
    """

    from policy_platform.infrastructure.formulation_mapping import states_a_negation

    assert states_a_negation(_rule(CanonicalRuleType.OBLIGATION, None, predicate=predicate)) is (
        False
    )
