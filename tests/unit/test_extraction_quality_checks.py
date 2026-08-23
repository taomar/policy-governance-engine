"""Quality checks that look at the extraction, because that is where the defect is.

A finding here always points upstream. Nothing downstream can repair a sentence
that was read twice, read two ways, or read differently by two runs — a search
API will return both records, and a judge handed either one has no way to know
the other exists.

Each check is exercised in both directions. A check only ever seen passing is
indistinguishable from one that cannot fire, and this file already caught that:
the contradiction check grouped records by a signature that included the
extractor's own classification, so two records that split one sentence
identically and then labelled it differently never compared as the same
reading — which is precisely the case it exists to find. It could not fire at
all, on any input.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition, FactComparisonCondition
from policy_platform.contracts.conditions import ConditionOperator
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    RuleFormulation,
)
from policy_platform.contracts.policy import (
    Effect,
    EffectType,
    EvaluationMode,
    RequiredFact,
    RuleLineage,
    RuleType,
)
from policy_platform.infrastructure.quality import ai_quality
from tests.fixtures.factories import make_rule


def _record(
    rule_id: str,
    *,
    sentence: str,
    predicate: str = "requires",
    obj: str = "the approval of the reviewer",
    effect_type: EffectType = EffectType.REQUIRE_ACTION,
    rule_type: CanonicalRuleType = CanonicalRuleType.OBLIGATION,
    run: str = "run-1",
    action: str = "requires the approval of the reviewer",
):
    """One extracted record, with the parts these checks compare."""

    rule = make_rule(rule_id, AllCondition(all=[]), effect_type=effect_type, effect_action=action)
    return rule.model_copy(
        update={
            "lineage": RuleLineage(extraction_run_id=run),
            "formulation": RuleFormulation(
                source_index=0,
                canonical=CanonicalPolicy(
                    source_text=sentence,
                    rule=CanonicalPolicyRule(
                        rule_type=rule_type,
                        subject="the exceptional increase",
                        predicate=predicate,
                        object=obj,
                    ),
                ),
            ),
        }
    )


def _categories(rules) -> list[str]:
    return [f["category"] for f in ai_quality._deterministic_findings(rules)]


SENTENCE = "The exceptional increase requires the approval of the reviewer."


# --------------------------------------------------------------------------
# One sentence read the same way twice
# --------------------------------------------------------------------------


def test_the_same_reading_stored_twice_is_reported():
    records = [_record("R1", sentence=SENTENCE), _record("R2", sentence=SENTENCE)]

    assert "duplicate_extraction" in _categories(records)


def test_one_sentence_carrying_two_policies_is_not_a_duplicate():
    """The case that must not be swept up.

    "shall not exceed 10% …, and the increase is associated with the appraisal"
    is two policies in one sentence, and they decompose differently. Reporting
    that as a duplicate would ask a reviewer to delete half a policy.
    """

    records = [
        _record("R1", sentence=SENTENCE, predicate="shall not exceed", obj="10% of the base"),
        _record("R2", sentence=SENTENCE, predicate="is associated with", obj="the appraisal"),
    ]

    assert "duplicate_extraction" not in _categories(records)


def test_two_different_sentences_are_never_duplicates_of_each_other():
    """Grouping is by sentence first, and that is load-bearing.

    Two policies from different clauses can decompose into the same shape —
    "the reviewer approves the request" appears in many documents — and
    matching on shape alone would report unrelated policies as copies of one
    another.
    """

    records = [
        _record("R1", sentence="The first clause says one thing."),
        _record("R2", sentence="A wholly different clause says another."),
    ]

    assert "duplicate_extraction" not in _categories(records)


def test_one_record_alone_is_never_a_duplicate():
    assert "duplicate_extraction" not in _categories([_record("R1", sentence=SENTENCE)])


# --------------------------------------------------------------------------
# One sentence, one reading, opposing outcomes
# --------------------------------------------------------------------------


def test_the_same_reading_with_opposing_effects_is_reported():
    """The check that could not fire before, on the signature that hid it."""

    records = [
        _record("R1", sentence=SENTENCE, effect_type=EffectType.REQUIRE_ACTION),
        _record("R2", sentence=SENTENCE, effect_type=EffectType.INFORMATIONAL),
    ]

    assert "contradictory_reading" in _categories(records)


def test_a_contradiction_is_not_also_reported_as_a_duplicate():
    """Two findings for one problem is noise; the stronger one wins."""

    records = [
        _record("R1", sentence=SENTENCE, effect_type=EffectType.REQUIRE_ACTION),
        _record("R2", sentence=SENTENCE, effect_type=EffectType.INFORMATIONAL),
    ]
    categories = _categories(records)

    assert "contradictory_reading" in categories
    assert "duplicate_extraction" not in categories


def test_a_differing_classification_does_not_hide_a_contradiction():
    """The signature bug, pinned.

    Two records that split one sentence identically and were then typed
    differently are the disagreement worth reporting. Grouping on the
    classification meant they never compared as the same reading.
    """

    records = [
        _record(
            "R1",
            sentence=SENTENCE,
            rule_type=CanonicalRuleType.OBLIGATION,
            effect_type=EffectType.REQUIRE_ACTION,
        ),
        _record(
            "R2",
            sentence=SENTENCE,
            rule_type=CanonicalRuleType.DEFINITION,
            effect_type=EffectType.INFORMATIONAL,
        ),
    ]

    assert "contradictory_reading" in _categories(records)


# --------------------------------------------------------------------------
# Two runs, two readings
# --------------------------------------------------------------------------


def test_two_runs_reading_one_sentence_differently_is_reported():
    records = [
        _record("R1", sentence=SENTENCE, run="run-1"),
        _record("R2", sentence=SENTENCE, run="run-2").model_copy(
            update={"rule_type": RuleType.PERMISSION}
        ),
    ]

    assert "unstable_extraction" in _categories(records)


def test_an_inverted_action_between_runs_is_reported():
    """Observed: one run stored an action, the next stored its negation."""

    records = [
        _record("R1", sentence=SENTENCE, run="run-1", action="be considered as promotion"),
        _record("R2", sentence=SENTENCE, run="run-2", action="cannot be considered as promotion"),
    ]

    assert "unstable_extraction" in _categories(records)


def test_two_readings_from_one_run_are_not_called_unstable():
    """Instability is a difference *between* runs.

    One run splitting a sentence into two policies is ordinary and correct.
    """

    records = [
        _record("R1", sentence=SENTENCE, run="run-1"),
        _record("R2", sentence=SENTENCE, run="run-1").model_copy(
            update={"rule_type": RuleType.PERMISSION}
        ),
    ]

    assert "unstable_extraction" not in _categories(records)


def test_agreeing_runs_are_not_reported():
    records = [
        _record("R1", sentence=SENTENCE, run="run-1"),
        _record("R2", sentence=SENTENCE, run="run-2"),
    ]

    assert "unstable_extraction" not in _categories(records)


# --------------------------------------------------------------------------
# Fit for the runner it is routed to
# --------------------------------------------------------------------------


def test_a_deterministic_record_naming_an_undeclared_fact_is_reported():
    """The defect that only appears at run time.

    The record looks complete; evaluation reaches the comparison, finds the
    fact absent, and reports a missing input.
    """

    rule = make_rule(
        "R1", FactComparisonCondition(fact="salary", operator=ConditionOperator.EXISTS, value=None)
    ).model_copy(update={"evaluation_mode": EvaluationMode.DETERMINISTIC, "required_facts": []})

    assert "not_runnable_as_stored" in _categories([rule])


def test_a_deterministic_record_declaring_its_facts_is_not_reported():
    rule = make_rule(
        "R1", FactComparisonCondition(fact="salary", operator=ConditionOperator.EXISTS, value=None)
    ).model_copy(
        update={
            "evaluation_mode": EvaluationMode.DETERMINISTIC,
            "required_facts": [RequiredFact(name="salary", data_type="number")],
        }
    )

    assert "not_runnable_as_stored" not in _categories([rule])


def test_a_record_decided_by_reading_that_answers_nothing_is_reported():
    """A judge sees this record and nothing else."""

    rule = make_rule("R1", AllCondition(all=[])).model_copy(
        update={
            "evaluation_mode": EvaluationMode.AI_READY,
            "effect": Effect(type=EffectType.REQUIRE_ACTION, action=""),
            "formulation": None,
            "fact_model": [],
            "evidence": [],
        }
    )

    assert "not_decidable_as_written" in _categories([rule])


def test_a_declared_fact_does_not_excuse_an_undeclared_one():
    """The narrow case, and the one that reaches evaluation.

    A record that declares *some* facts passes the coarse check. If its
    condition also names one it never declared, the engine still stops at that
    comparison — and the record looked complete right up until it ran.
    """

    rule = make_rule(
        "R1",
        AllCondition(
            all=[
                FactComparisonCondition(
                    fact="salary", operator=ConditionOperator.EXISTS, value=None
                ),
                FactComparisonCondition(
                    fact="tenure", operator=ConditionOperator.EXISTS, value=None
                ),
            ]
        ),
    ).model_copy(
        update={
            "evaluation_mode": EvaluationMode.DETERMINISTIC,
            "required_facts": [RequiredFact(name="salary", data_type="number")],
        }
    )

    findings = ai_quality._deterministic_findings([rule])
    reported = [f for f in findings if f["category"] == "not_runnable_as_stored"]

    assert reported, "an undeclared fact inside a compiled condition went unreported"
    assert "tenure" in reported[0]["finding"]


def test_a_record_missing_only_its_operative_content_is_reported():
    """Everything else present, so only the one check can be firing.

    A record with a sentence, facts, an outcome and evidence, whose
    decomposition states no test at all, cannot be decided by anyone — and it
    is the case a coarser check misses, because every other question has an
    answer.

    The sentence is deliberately operatively empty as well as the slots. This
    check reads what a judge reads, and a judge reads the sentence: the fixture
    used to strip the slots while leaving "requires the approval of the
    reviewer" in place, which states a test perfectly well and is decidable by
    anyone reading it. That record's problem is an empty extraction, not a
    silent policy, and reporting it as "the record does not say what it
    requires" told a reader their document was deficient when it was not. See
    `test_a_validation_reads_what_the_decider_reads`.
    """

    from policy_platform.contracts.policy import EvidenceReference
    from policy_platform.infrastructure.extraction.policy_facts import facts_for

    rule = _record("R1", sentence="The exceptional increase applies.")
    silent = rule.formulation.model_copy(
        update={
            "canonical": rule.formulation.canonical.model_copy(
                update={
                    "rule": CanonicalPolicyRule(
                        rule_type=CanonicalRuleType.OBLIGATION,
                        subject="the exceptional increase",
                    )
                }
            )
        }
    )
    rule = rule.model_copy(
        update={
            "evaluation_mode": EvaluationMode.AI_READY,
            "formulation": silent,
            "fact_model": facts_for(silent.canonical.rule),
            "evidence": [
                EvidenceReference(document_version_id="doc-1", source_hash="h", section="1")
            ],
        }
    )

    findings = ai_quality._deterministic_findings([rule])
    reported = [f for f in findings if f["category"] == "not_decidable_as_written"]

    assert reported, "a record stating no test at all went unreported"
    assert "what it requires" in reported[0]["finding"]


def test_a_complete_record_decided_by_reading_is_not_reported():
    """Guards the check above: silence has to mean something."""

    from policy_platform.contracts.policy import EvidenceReference
    from policy_platform.infrastructure.extraction.policy_facts import facts_for

    rule = _record("R1", sentence=SENTENCE)
    rule = rule.model_copy(
        update={
            "evaluation_mode": EvaluationMode.AI_READY,
            "fact_model": facts_for(rule.formulation.canonical.rule),
            "evidence": [
                EvidenceReference(document_version_id="doc-1", source_hash="h", section="1")
            ],
        }
    )

    assert "not_decidable_as_written" not in _categories([rule])
