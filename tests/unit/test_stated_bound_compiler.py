"""Compiling a bound the sentence states in full.

Most policy text states no quantity at all, so nothing here is a general
solution to executability. It covers one construction that appears often enough
to be worth reading exactly: a quantity bounded by a proportion of another
quantity, where the sentence names both operands and the comparison.

What makes it safe to compile is that nothing comes from outside the document.
The fact *names* are the sentence's own phrases; a consumer supplies values for
them exactly as for any other named input. That is a different claim from
inventing a fact path, which asserts that some system holds a field at an
address the document never mentioned.

The direction of the comparison is the part most likely to be got wrong, and
getting it backwards is worse than not compiling: "shall not exceed 10%"
compiled as `greaterThan` would approve exactly the cases the policy forbids.
So both directions are tested, from both places the source writes negation —
the modal word and the predicate.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.conditions import ConditionOperator
from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.extraction.formulation_mapping import condition_from_stated_bound
from policy_platform.infrastructure.extraction.policy_facts import facts_for, parse_proportion


def _rule(**fields) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(rule_type=CanonicalRuleType.OBLIGATION, **fields)


# --------------------------------------------------------------------------
# Reading the phrase
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,factor,base",
    [
        ("10% of the base", 0.1, "the base"),
        ("5 % of the reference figure", 0.05, "the reference figure"),
        ("2.5% of the total", 0.025, "the total"),
        ("100% of the amount", 1.0, "the amount"),
    ],
)
def test_a_proportion_is_read_as_a_factor_and_a_base(phrase, factor, base):
    assert parse_proportion(phrase) == (pytest.approx(factor), base)


@pytest.mark.parametrize(
    "phrase",
    [
        "5000",
        "the base",
        "",
        "10%",
        "10% of",
        "the amount reduced by 10% of the base",
        "at least 10% of the base is required",
    ],
)
def test_anything_that_is_not_a_proportion_is_refused(phrase):
    """Including a phrase that merely contains one.

    A fixed limit and a proportional one are different claims, and a phrase
    where the proportion is only a part states neither on its own.
    """

    assert parse_proportion(phrase) is None


# --------------------------------------------------------------------------
# Direction of the comparison
# --------------------------------------------------------------------------


def test_a_forbidden_excess_compiles_as_staying_within_the_bound():
    """The direction that matters most. Backwards, it approves what is banned."""

    compiled = condition_from_stated_bound(
        _rule(
            subject="the annual increase",
            modality="shall not",
            predicate="exceed",
            threshold="10% of the base",
        )
    )

    assert compiled is not None
    condition, _ = compiled
    assert condition.fact == "annual-increase"
    assert condition.operator is ConditionOperator.LESS_THAN_OR_EQUAL
    assert condition.reference.fact == "base"
    assert condition.reference.factor == pytest.approx(0.1)


def test_negation_written_into_the_predicate_reads_the_same():
    """Source puts it in either place, and reading only the modal inverted one.

    "not exceeding 5% of the base" has no modal word at all; a check that
    looked only at `modality` saw no negation and compiled the opposite test.
    """

    compiled = condition_from_stated_bound(
        _rule(subject="the increase", predicate="not exceeding", threshold="5% of the base")
    )

    assert compiled is not None
    assert compiled[0].operator is ConditionOperator.LESS_THAN_OR_EQUAL


def test_an_asserted_excess_keeps_its_direction():
    """Without negation the comparison is the one the predicate names."""

    compiled = condition_from_stated_bound(
        _rule(subject="the increase", modality="shall", predicate="exceed", threshold="10% of base")
    )

    assert compiled is not None
    assert compiled[0].operator is ConditionOperator.GREATER_THAN


@pytest.mark.parametrize(
    "predicate,operator",
    [
        ("is limited to", ConditionOperator.LESS_THAN_OR_EQUAL),
        ("up to a maximum of", ConditionOperator.LESS_THAN_OR_EQUAL),
        ("no more than", ConditionOperator.LESS_THAN_OR_EQUAL),
        ("at least", ConditionOperator.GREATER_THAN_OR_EQUAL),
        ("a minimum of", ConditionOperator.GREATER_THAN_OR_EQUAL),
    ],
)
def test_each_comparative_predicate_names_its_own_operator(predicate, operator):
    compiled = condition_from_stated_bound(
        _rule(subject="the amount", predicate=predicate, threshold="10% of the base")
    )

    assert compiled is not None
    assert compiled[0].operator is operator


# --------------------------------------------------------------------------
# What is refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"subject": "the amount", "predicate": "exceed"},
        {"subject": "the amount", "threshold": "10% of the base"},
        {"predicate": "exceed", "threshold": "10% of the base"},
        {"subject": "the amount", "predicate": "exceed", "threshold": "5,000"},
        {"subject": "the amount", "predicate": "be paid", "threshold": "10% of the base"},
        {"subject": "the base", "predicate": "exceed", "threshold": "10% of the base"},
    ],
)
def test_an_incomplete_or_uncomparative_statement_is_not_compiled(fields):
    """Refusing is the safe answer; guessing the comparison is not.

    The last case is a phrase compared against itself, which would produce a
    tautology or a contradiction depending on the factor — never the rule.
    """

    assert condition_from_stated_bound(_rule(**fields)) is None


def test_nothing_is_compiled_from_no_rule():
    assert condition_from_stated_bound(None) is None


# --------------------------------------------------------------------------
# Agreement with the published fact model
# --------------------------------------------------------------------------


def test_the_compiled_facts_are_the_ones_the_policy_publishes():
    """A consumer reads `fact_model` and supplies those names.

    If the condition referenced a name the fact model never listed, a caller
    following the published contract would supply the wrong keys and every
    evaluation would report a missing fact.
    """

    rule = _rule(
        subject="the annual increase",
        modality="shall not",
        predicate="exceed",
        threshold="10% of the current base figure",
    )

    compiled = condition_from_stated_bound(rule)
    assert compiled is not None
    _, required = compiled

    published = {fact.name for fact in facts_for(rule)}
    assert {item.name for item in required} <= published
