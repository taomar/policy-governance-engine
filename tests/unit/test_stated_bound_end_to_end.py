"""A sentence that states its own bound produces a decidable policy.

The compiler is unit-tested elsewhere; this checks it is actually reached, and
that everything downstream of it agrees. Wiring is where this kind of change
usually fails: the function is correct, nothing calls it, and every unit test
still passes.

Three things have to line up in the emitted record, or a consumer following the
published contract gets a different answer depending on which field it reads:

* `condition` carries the comparison,
* `required_facts` names what a case must supply,
* `evaluation_mode` says `deterministic`,
* and `fact_model` publishes the same names with the same types.

The extraction path is the only place this runs. A stored rule keeps the
condition it was approved with — re-deriving executable logic on read would
change what an approved rule does without anyone reviewing the change, which is
a different and worse problem than a stale label.
"""
from __future__ import annotations

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    PolicyFormulation,
)
from policy_platform.contracts.policy import EvaluationMode
from policy_platform.infrastructure.formulation_mapping import formulation_to_candidate_rules


def _rules_for(policy: CanonicalPolicy):
    rules, _ = formulation_to_candidate_rules(
        PolicyFormulation(canonical_policies=[policy]),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )
    return rules


def _bounded_policy() -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text="The annual increase shall not exceed 10% of the current base figure.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.PROHIBITION,
            subject="the annual increase",
            modality="shall not",
            predicate="exceed",
            threshold="10% of the current base figure",
        ),
    )


def test_a_stated_bound_reaches_the_emitted_rule():
    """The wiring check. Without it the compiler is dead code."""

    rule = _rules_for(_bounded_policy())[0]

    assert rule.condition.type == "factRelativeComparison"
    assert rule.condition.fact == "annual-increase"
    assert rule.condition.reference.fact == "current-base-figure"
    assert rule.condition.reference.factor == 0.1


def test_a_stated_bound_is_decidable_without_a_judge():
    """The field a consumer routes on."""

    rule = _rules_for(_bounded_policy())[0]

    assert rule.evaluation_mode is EvaluationMode.DETERMINISTIC


def test_the_published_facts_match_the_facts_the_condition_needs():
    """Two fields describing the same names must not disagree.

    `fact_model` is what a consumer reads to know what to supply;
    `required_facts` is what evaluation checks for. A name in one and not the
    other means a caller who followed the contract still fails every call.
    """

    rule = _rules_for(_bounded_policy())[0]

    published = {fact.name: fact.data_type for fact in rule.fact_model}
    for required in rule.required_facts:
        assert required.name in published
        assert published[required.name] == required.data_type


def test_a_compiled_bound_says_where_it_came_from():
    """Distinct from a declared decision, because it is reviewed differently."""

    rule = _rules_for(_bounded_policy())[0]

    assert rule.condition_provenance.code == "derived_from_stated_bound"


def test_a_record_never_claims_a_derivation_its_tree_does_not_have():
    """The read path answers about this record, not about the sentence.

    Re-deriving from the formulation alone answers "what would this sentence
    compile to now", which is a different question from "why does this rule's
    tree look like this". They came apart as soon as the compiler was added:
    candidates extracted before it existed carry an empty tree, and their
    sentences still state a compilable bound, so they reported
    `derived_from_stated_bound` over `all: []`.
    """

    from policy_platform.contracts.conditions import AllCondition
    from policy_platform.infrastructure.formulation_mapping import condition_provenance_for

    rule = _rules_for(_bounded_policy())[0]

    assert condition_provenance_for(rule.formulation, rule.condition).code == (
        "derived_from_stated_bound"
    )
    # The same formulation, read against a record that carries no tree.
    stale = condition_provenance_for(rule.formulation, AllCondition(all=[]))
    assert stale.code != "derived_from_stated_bound"


def test_the_read_path_explains_the_bound_the_same_way():
    """Extraction and read must not contradict each other about one record.

    `condition_provenance` is derived on read, and the read path did not know
    about the stated-bound fallback. So a rule carrying a fully compiled
    comparison was served as `conditions_not_projected` — the record disagreeing
    with itself, in the direction that sends a reviewer to supply a mapping that
    is not missing. Found by re-extracting and reading the served JSON rather
    than by re-reading the code that writes it.
    """

    from policy_platform.infrastructure.formulation_mapping import condition_provenance_for

    rule = _rules_for(_bounded_policy())[0]

    assert condition_provenance_for(rule.formulation, rule.condition).code == (
        rule.condition_provenance.code
    )


def test_a_policy_stating_no_bound_is_left_for_a_judge():
    """The majority case, and it must not be forced into a comparison."""

    rule = _rules_for(
        CanonicalPolicy(
            source_text="Requests are considered on their merits.",
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="requests",
                predicate="are considered",
                object="on their merits",
            ),
        )
    )[0]

    assert rule.evaluation_mode is EvaluationMode.AI_READY
    assert rule.condition_provenance.code != "derived_from_stated_bound"
