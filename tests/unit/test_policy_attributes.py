"""The attribute table a record carries: attribute, the document's text, the fact.

This is the shape every consumer reads — a reviewer checking the extraction, a
search API indexing it, a judge deciding a case from it — so the guarantees are
about faithfulness rather than about tidiness.

Two of them matter more than the rest, because breaking either is invisible in
a passing render:

* the text is the document's, unaltered — never trimmed to fit, merged with a
  neighbouring attribute, or paraphrased;
* the attribute name is the record's own, unrenamed.

Both were broken by earlier presentations that read better for it. One glued
`modality` and `predicate` into "shall not exceed", a string no attribute
contains. One renamed `frequency` to "how often" and `assigner` to "decided
by". One dropped a phrase that had already appeared under another attribute,
concealing that one phrase had been assigned to three slots.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.contracts.policy import (
    APPLIES_ATTRIBUTES,
    OUTCOME_ATTRIBUTES,
    CanonicalRule,
    attributes_for,
)
from policy_platform.infrastructure.policy_facts import facts_for

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "ad103_rules.json"


def _rule(**fields) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(rule_type=CanonicalRuleType.OBLIGATION, **fields)


def _table(rule: CanonicalPolicyRule):
    return attributes_for(rule, facts_for(rule))


@pytest.fixture(scope="module")
def corpus() -> list[CanonicalRule]:
    return [
        CanonicalRule.model_validate(payload)
        for payload in json.loads(CORPUS.read_text(encoding="utf-8"))
    ]


# --------------------------------------------------------------------------
# The text is the document's
# --------------------------------------------------------------------------


def test_every_value_is_the_canonical_text_unchanged(corpus):
    """Character for character, over the real corpus.

    The check that catches a paraphrase, a truncation, or a merge — none of
    which look wrong on screen.
    """

    altered: list[tuple[str, str]] = []
    for rule in corpus:
        core = rule.formulation.canonical.rule
        if core is None:
            continue
        table = attributes_for(core, facts_for(core))
        for row in [*table.applies, *table.outcome]:
            if row.text != (getattr(core, row.attribute, "") or "").strip():
                altered.append((rule.rule_id, row.attribute))

    assert not altered, f"attributes whose text differs from the record: {altered}"


def test_modality_and_predicate_stay_separate():
    """The merge that read best and was least true.

    "shall not exceed" is not the value of any attribute; `modality` holds
    "shall not" and `predicate` holds "exceed".
    """

    table = _table(_rule(subject="the increase", modality="shall not", predicate="exceed"))
    values = {row.attribute: row.text for row in table.outcome}

    assert values["modality"] == "shall not"
    assert values["predicate"] == "exceed"
    assert not any(row.text == "shall not exceed" for row in table.outcome)


def test_a_repeated_phrase_is_shown_under_every_attribute_that_holds_it():
    """Hiding the repeat would report the extraction as tidier than it is.

    `object`, `threshold` and `calculation` routinely hold the same bound. A
    reader needs to see that one phrase was assigned to three slots; that is
    the kind of thing this table exists to expose.
    """

    bound = "10% of the base"
    table = _table(_rule(subject="the increase", object=bound, threshold=bound, calculation=bound))

    holding = [row.attribute for row in table.outcome if row.text == bound]
    assert holding == ["object", "threshold", "calculation"]


# --------------------------------------------------------------------------
# The attribute name is the record's
# --------------------------------------------------------------------------


def test_attribute_names_are_the_canonical_field_names(corpus):
    """No friendlier synonyms. A renamed attribute asserts something else."""

    known = set(APPLIES_ATTRIBUTES) | set(OUTCOME_ATTRIBUTES)
    for rule in corpus:
        core = rule.formulation.canonical.rule
        if core is None:
            continue
        table = attributes_for(core, facts_for(core))
        for row in [*table.applies, *table.outcome]:
            assert row.attribute in known
            assert hasattr(core, row.attribute)


def test_an_empty_attribute_produces_no_row():
    """Only what the record carries. Absence is not rendered as a blank."""

    table = _table(_rule(subject="the request"))

    assert [row.attribute for row in table.applies] == ["subject"]
    assert table.outcome == []


# --------------------------------------------------------------------------
# The fact column
# --------------------------------------------------------------------------


def test_a_fact_is_matched_by_role_not_by_text():
    """The bug a sample caught before this shipped.

    Matching by containment attached `per-month`, read from `frequency`, to
    "(200) two hundred SR per month" and "at the rate of (200) two hundred SR
    per month" as well — so three attributes appeared to require a value that
    only one of them names.
    """

    table = _table(
        _rule(
            subject="the allowance",
            predicate="is paid",
            object="(200) two hundred SR per month",
            calculation="at the rate of (200) two hundred SR per month",
            frequency="per month",
        )
    )
    facts = {row.attribute: row.fact for row in table.outcome}

    assert facts["frequency"] == "per-month"
    assert facts["object"] is None
    assert facts["calculation"] is None


def test_an_absent_fact_means_the_document_states_the_value():
    """An empty cell is a statement, not a gap.

    "(200) two hundred SR per month" is what the policy pays. A case supplies
    nothing for it, and the table says so in the same column every time.
    """

    table = _table(_rule(subject="the allowance", object="(200) two hundred SR per month"))

    assert next(row for row in table.outcome if row.attribute == "object").fact is None


def test_a_named_authority_is_matched_through_its_role():
    """`assigner` publishes as `authority`; the pairing must survive that."""

    table = _table(_rule(subject="the request", assigner="the review board"))

    row = next(row for row in table.outcome if row.attribute == "assigner")
    assert row.fact == "review-board"


def test_every_published_fact_is_reachable_from_some_row(corpus):
    """A fact nobody can trace back to an attribute cannot be checked."""

    orphaned: list[tuple[str, str]] = []
    for rule in corpus:
        core = rule.formulation.canonical.rule
        if core is None:
            continue
        facts = facts_for(core)
        table = attributes_for(core, facts)
        named = {row.fact for row in [*table.applies, *table.outcome] if row.fact}
        for fact in facts:
            if fact.name not in named:
                orphaned.append((rule.rule_id, fact.name))

    assert not orphaned, f"facts attached to no attribute row: {orphaned}"


# --------------------------------------------------------------------------
# Order
# --------------------------------------------------------------------------


def test_the_order_is_fixed_so_two_records_read_alike():
    """Declaration order, not dictionary order."""

    first = _table(_rule(subject="a", predicate="b", object="c", threshold="d"))
    assert [row.attribute for row in first.outcome] == ["predicate", "object", "threshold"]

    second = _table(_rule(threshold="d", object="c", predicate="b", subject="a"))
    assert [row.attribute for row in second.outcome] == [
        row.attribute for row in first.outcome
    ]


def test_no_rule_produces_an_empty_table():
    assert attributes_for(None, []).applies == []
    assert attributes_for(None, []).outcome == []
