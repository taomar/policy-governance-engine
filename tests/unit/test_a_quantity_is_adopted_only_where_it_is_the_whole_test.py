"""A stated quantity is adopted only where the sentence is the whole test.

The compiler can read a comparison out of a single sentence. Whether that
comparison is the *whole* of what the provision states is a different question,
and the record cannot tell the difference by looking at the sentence alone.

The formulator answers it structurally. `DmnDecision.source_rule_indexes` names
every canonical rule a decision covers, and the contract is explicit that
"several canonical rules may legitimately collapse into one decision" — so a
decision naming this rule *and others* is the formulator saying these sentences
are clauses of one provision decided together.

Measured on stored output, that distinction is not academic. One decision covered
a graduated schedule: three bands of a measured quantity crossed with four
occurrence counts, each pairing carrying a different consequence. The compiler
reads the first band's sentence and produces a clean comparison against that
band's number. Evaluated on its own it fires for every case in the band and says
nothing about the occurrence count — so a machine acting on it applies one
consequence to cases the document assigns four different ones.

That is not a wrong number. It is a **partial condition presented as complete**,
which is the more dangerous failure of the two: it looks decidable, so nothing
prompts the reader the document assumed.

The rule this file pins down:

* a decision naming this rule alone leaves the sentence as the only statement of
  the test, and adopting its comparison invents nothing;
* a decision naming this rule among others means the condition would not carry
  the provision whole, so the rule is decided by reading — and says so, naming
  the quantity it declined to adopt so the reader can check the judgement rather
  than take it;
* a quantity that could not compile at all still refuses for its own reason.
  Being the whole test is necessary for adoption and not sufficient, and the
  refusal codes must not be masked by this one.

No vocabulary here is taken from any document. The shapes are the measured ones;
the words are not.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
    DmnMappingStatus,
    DmnProjection,
    PolicyFormulation,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    _ROW_CELL_SEPARATOR,
    formulation_to_candidate_rules,
    states_a_flattened_row,
)
from policy_platform.infrastructure.ingestion import document_ingestion


def _compilable(subject: str, threshold: str, unit: str) -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text=f"{subject} must be {threshold}.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject=subject,
            modality="must be",
            predicate="observed",
            threshold=threshold,
            unit=unit,
        ),
    )


def _rules(policies: list[CanonicalPolicy], covered: list[list[int]] | None):
    """Formulate `policies`, with one declared decision per entry in `covered`.

    `covered` of None declares no decision at all. Every declared decision is
    non-executable, which is the only shape observed in stored output and the
    only one that reaches the quantity compiler at all — an executable decision
    compiles earlier and never gets here.
    """

    decisions = [
        DmnDecision(
            source_rule_indexes=list(indexes),
            dmn_mapping_status=DmnMappingStatus.ENRICHMENT_REQUIRED,
        )
        for indexes in (covered or [])
    ]
    rules, _ = formulation_to_candidate_rules(
        PolicyFormulation(
            canonical_policies=policies,
            dmn_projection=DmnProjection(decisions=decisions),
        ),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )
    return rules


def test_a_decision_naming_this_rule_alone_leaves_the_sentence_as_the_whole_test():
    """Nothing else states the test, so reading the sentence invents nothing."""

    rule = _rules([_compilable("the review interval", "at least 6 weeks", "weeks")], [[0]])[0]

    assert rule.condition_provenance.code == "derived_from_stated_quantity"
    assert rule.machine_executable


def test_no_decision_at_all_is_unchanged():
    """The control for the path that was already open."""

    rule = _rules([_compilable("the review interval", "at least 6 weeks", "weeks")], None)[0]

    assert rule.condition_provenance.code == "derived_from_stated_quantity"
    assert rule.machine_executable


def test_a_decision_naming_others_too_means_the_condition_would_not_carry_the_whole():
    """The hazard. The sentence compiles; the provision says more than the sentence."""

    rules = _rules(
        [
            _compilable("the review interval", "at least 6 weeks", "weeks"),
            _compilable("the escalation interval", "at least 9 weeks", "weeks"),
        ],
        [[0, 1]],
    )

    assert not rules[0].machine_executable
    assert rules[0].condition_provenance.code == "stated_quantity_is_one_clause_of_a_provision"


def test_the_withheld_quantity_is_named_so_the_judgement_can_be_checked():
    """A category without its instance is a reason that must be believed."""

    rules = _rules(
        [
            _compilable("the review interval", "at least 6 weeks", "weeks"),
            _compilable("the escalation interval", "at least 9 weeks", "weeks"),
        ],
        [[0, 1]],
    )

    assert rules[0].condition_provenance.unprojected_quantity == "at least 6 weeks"
    assert rules[1].condition_provenance.unprojected_quantity == "at least 9 weeks"


def test_a_graduated_schedule_routes_by_reading_rather_than_by_one_of_its_bands():
    """The measured shape: bands of a quantity crossed with occurrence counts.

    Each sentence compiles on its own and each is one cell of a matrix. Adopting
    any of them would apply that cell's consequence to the whole schedule.
    """

    bands = [
        _compilable("the first band", "up to 10 units", "units"),
        _compilable("the second band", "up to 20 units", "units"),
        _compilable("the third band", "up to 30 units", "units"),
    ]
    rules = _rules(bands, [[0, 1, 2]])

    assert [r.machine_executable for r in rules] == [False, False, False]
    for rule in rules:
        assert rule.condition_provenance.code == "stated_quantity_is_one_clause_of_a_provision"
        assert rule.condition_provenance.unprojected_quantity


def test_being_the_whole_test_is_necessary_and_not_sufficient():
    """The control in the other direction.

    A decision naming this rule alone does not license adoption on its own. The
    quantity must still compile, and where it cannot, its own reason stands —
    otherwise this discriminator would be shipped as though it were the only
    gate.
    """

    states_a_number_with_no_comparison = CanonicalPolicy(
        source_text="The standard interval is 6 weeks.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject="the standard interval",
            modality="is",
            predicate="observed",
            threshold="6 weeks",
            unit="weeks",
        ),
    )
    rule = _rules([states_a_number_with_no_comparison], [[0]])[0]

    assert not rule.machine_executable
    assert rule.condition_provenance.code == "quantity_states_no_comparison"
    assert rule.condition_provenance.unprojected_quantity == "6 weeks"


def test_a_rule_a_wider_decision_does_not_name_is_unaffected_by_it():
    """Coverage is read per rule, not per formulation.

    A document may state a graduated schedule in one place and a self-contained
    limit in another. The second is not made judged by the first's existence.
    """

    rules = _rules(
        [
            _compilable("the first band", "up to 10 units", "units"),
            _compilable("the second band", "up to 20 units", "units"),
            _compilable("the standalone limit", "at least 6 weeks", "weeks"),
        ],
        [[0, 1], [2]],
    )

    assert not rules[0].machine_executable
    assert not rules[1].machine_executable
    assert rules[2].machine_executable
    assert rules[2].condition_provenance.code == "derived_from_stated_quantity"


@pytest.mark.parametrize(
    ("subject", "threshold", "unit", "operand", "value"),
    [
        ("the review interval", "at least 6 weeks", "weeks", "review-interval-weeks", 6.0),
        ("the retention period", "up to 7 years", "years", "retention-period-years", 7.0),
    ],
)
def test_an_adopted_condition_still_compares_the_measured_quantity(
    subject: str, threshold: str, unit: str, operand: str, value: float
):
    """Opening this path must not reopen the operand defect it sits on top of.

    The condition adopted here is the one the quantity compiler produced, so the
    guarantee that it compares what the number counts travels with it.
    """

    rule = _rules([_compilable(subject, threshold, unit)], [[0]])[0]

    assert rule.machine_executable
    assert rule.condition.fact == operand
    assert rule.condition.value == value


def test_the_required_fact_matches_the_operand_on_an_adopted_condition():
    """A case supplies the fact the condition names, or the rule cannot decide."""

    rule = _rules([_compilable("the review interval", "at least 6 weeks", "weeks")], [[0]])[0]

    assert [f.name for f in rule.required_facts] == [rule.condition.fact]


def _flattened_row(cells: list[str], threshold: str, unit: str) -> CanonicalPolicy:
    """A table row as it reaches a record: cells joined, columns no longer marked."""

    return CanonicalPolicy(
        source_text=_ROW_CELL_SEPARATOR.join(cells),
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject="the measured interval",
            modality="must be",
            predicate="observed",
            threshold=threshold,
            unit=unit,
        ),
    )


def test_a_comparison_read_from_a_flattened_row_is_not_adopted():
    """Grouping is necessary and not sufficient, and this is why.

    Measured on stored output, the same table row was grouped with its siblings
    in one run and left ungrouped in another. The hazard is a property of the
    row, not of whether the formulator noticed it, so it is detected from the
    row.
    """

    rule = _rules(
        [_flattened_row(["a measured limit of 10 units", "one consequence", "another consequence"],
                        "up to 10 units", "units")],
        [[0]],
    )[0]

    assert not rule.machine_executable
    assert rule.condition_provenance.code == "stated_quantity_comes_from_a_table_row"
    assert rule.condition_provenance.unprojected_quantity == "up to 10 units"


def test_a_flattened_row_is_recognised_from_the_join_that_makes_one():
    """Pin the marker to its writer, so the two cannot drift apart silently.

    `document_ingestion` is the single place a table row becomes a line of text,
    and it joins the cells with a literal rather than a shared constant. Reading
    it here means that if the join ever changes, this fails loudly rather than
    the gate quietly ceasing to fire on every table in every document.
    """

    source = Path(document_ingestion.__file__).read_text(encoding="utf-8")
    joins = re.findall(r'cell_text = (".*?")\.join\(cells\)', source)

    assert joins, "document_ingestion no longer joins table cells where this test looked"
    assert [ast.literal_eval(j) for j in joins] == [_ROW_CELL_SEPARATOR]


def test_ordinary_prose_is_not_mistaken_for_a_row():
    """The control. A sentence that never sat in a table is unaffected."""

    policy = _compilable("the review interval", "at least 6 weeks", "weeks")

    assert not states_a_flattened_row(policy)
    assert _rules([policy], [[0]])[0].machine_executable
