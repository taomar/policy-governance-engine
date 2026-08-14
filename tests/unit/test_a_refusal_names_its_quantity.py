"""A refusal must name the quantity it refused, even when a decision was declared.

The gate Stage 5b exists to provide is that a rule carrying a stated quantity
either projects a condition or says why it did not. Saying why is only half the
promise: `no_scope_derived` names a category, and a reviewer holding a category
cannot check anything. The quantity's own words are the evidence, and without
them the refusal has to be believed rather than verified.

The interesting case is the one production actually produces. Every formulated
policy in a real run carries a declared DMN decision, so the branch that adopts
a compiled quantity is correctly skipped — the tree is not this compiler's to
write when another component already declared one. But skipping the *adoption*
had also been skipping the *diagnosis*, which nothing required. Reading a
sentence to explain an empty tree invents nothing; it only reports.

The distinction this pins down:

* a quantity that refused is reported, with its text, whatever else declared;
* a quantity that compiled but was not adopted is NOT reported as derived,
  because the record's condition did not come from it and saying so would
  describe a derivation that is not there.
"""
from __future__ import annotations

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
    DmnProjection,
    PolicyFormulation,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    formulation_to_candidate_rules,
)


def _rules_for(policy: CanonicalPolicy, *, with_decision: bool):
    projection = DmnProjection(
        decisions=[
            DmnDecision(
                key="declared-decision",
                name="A decision the formulator declared",
                source_rule_indexes=[0],
            )
        ]
        if with_decision
        else []
    )
    rules, _ = formulation_to_candidate_rules(
        PolicyFormulation(canonical_policies=[policy], dmn_projection=projection),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )
    return rules


def _states_a_quantity_with_no_comparison() -> CanonicalPolicy:
    """A quantity with no comparative. Refusing it is correct; hiding why is not."""

    return CanonicalPolicy(
        source_text="A standard working week is 48 hours in a week.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject="a standard working week",
            modality="is",
            predicate="worked",
            threshold="48 hours in a week",
            unit="hours",
        ),
    )


def test_a_refusal_names_its_quantity_when_a_decision_was_declared():
    """The gate. Production always declares a decision, so this is the live path."""

    rule = _rules_for(_states_a_quantity_with_no_comparison(), with_decision=True)[0]

    assert rule.condition_provenance.code == "quantity_states_no_comparison"
    assert rule.condition_provenance.unprojected_quantity == "48 hours in a week"


def test_the_refusal_reads_the_same_with_no_decision_declared():
    """The reason does not depend on whether something else spoke."""

    rule = _rules_for(_states_a_quantity_with_no_comparison(), with_decision=False)[0]

    assert rule.condition_provenance.code == "quantity_states_no_comparison"
    assert rule.condition_provenance.unprojected_quantity == "48 hours in a week"


def _states_a_compilable_comparison() -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text="Eligibility requires at least 12 months of continuous service.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject="continuous service",
            modality="must be",
            predicate="completed",
            threshold="at least 12 months",
            unit="months",
        ),
    )


def test_a_declared_decision_still_owns_the_tree():
    """Diagnosing must not become adopting.

    The compiler can read this sentence, but another component already declared
    a decision for it. The condition is not this compiler's to write, and the
    record must not claim a derivation it does not carry.
    """

    rule = _rules_for(_states_a_compilable_comparison(), with_decision=True)[0]

    assert rule.condition_provenance.code != "derived_from_stated_quantity"
    assert not rule.machine_executable


def test_with_nothing_declared_the_same_sentence_still_compiles():
    """The control: the adoption path is unchanged where it was already allowed."""

    rule = _rules_for(_states_a_compilable_comparison(), with_decision=False)[0]

    assert rule.condition_provenance.code == "derived_from_stated_quantity"
    assert rule.machine_executable
