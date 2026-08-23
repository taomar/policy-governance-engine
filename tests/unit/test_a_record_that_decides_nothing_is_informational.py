"""A record that decides nothing is informational; everything else still decides.

The user showed a quality report flagging this record:

    Please check with the HR department about the latest Covid regulations as
    these are subject to change as per the Ministry of Health

with "the record does not say what it requires" and "the source uses
conditional language and the decomposition records no condition". Both true.
Neither a defect. The sentence states no proposition a case can satisfy or
fail, so asking whether it decides *well* is asking the wrong question of it.

The fix marks such records `informational` at extraction, and the decidability
checks then skip them. The danger in a fix shaped like that is obvious and it
bit twice while this was being written: anything that quietly reclassifies a
rule as "not a decision" can disarm real prohibitions. Two whole designs were
discarded for exactly that, and both were discarded by measurement rather than
by review:

  * routing on `Evaluability` — the guidance record assesses `decidable` while
    "Alcohol and drugs are strictly forbidden" assesses `underspecified`, so it
    is backwards; it would have stripped DENY from eleven live prohibitions.
  * routing on `rule_type == recommendation` — "No one should use profanity" is
    a recommendation that decides, and it disarmed nine negated-subject
    prohibitions.

So the negative cases below are the point of this file, not an afterthought.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    states_no_testable_proposition,
)
from policy_platform.contracts.policy import EffectType, yields_no_verdict


def _rule(
    rule_type: CanonicalRuleType,
    *,
    subject: str = "employees",
    modality: str | None = None,
    predicate: str = "comply",
    obj: str | None = None,
) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(
        rule_type=rule_type,
        subject=subject,
        modality=modality,
        predicate=predicate,
        object=obj,
    )


# --------------------------------------------------------------------------
# What it fires on
# --------------------------------------------------------------------------


#: Verbatim from the AIS staff handbook, both records the user reported.
_COURTESY = [
    ("you", "Please", "check with", "the HR department about the latest Covid regulations"),
    ("you", "Please", "check", "with the HR department about the latest Covid regulations"),
]


@pytest.mark.parametrize("subject,modality,predicate,obj", _COURTESY)
def test_a_courtesy_modality_states_no_proposition(subject, modality, predicate, obj):
    """"Please" asks. It does not oblige, permit or forbid."""

    rule = _rule(
        CanonicalRuleType.RECOMMENDATION,
        subject=subject,
        modality=modality,
        predicate=predicate,
        obj=obj,
    )
    assert states_no_testable_proposition(rule)


def test_an_ambiguous_rule_states_no_proposition():
    """The extraction is telling us it could not settle what the sentence decides.

    A record carrying that admission must not then contribute a decision:
    doing so asserts downstream exactly the thing the extraction declined to
    determine.
    """

    rule = _rule(CanonicalRuleType.AMBIGUOUS, modality="shall")
    assert states_no_testable_proposition(rule)


# --------------------------------------------------------------------------
# What it must never fire on
#
# Every modality below is taken from the live corpus, with the rule type the
# formulator gave it. All 76 distinct non-courtesy modalities in that corpus
# carry force; these are the ones most likely to be mistaken for guidance.
# --------------------------------------------------------------------------


#: (modality, rule_type) — soft deontic operators. The whole trap: these look
#: advisory and decide anyway. Asked "did the employee do it?", each answers.
_SOFT_BUT_DECIDES = [
    ("should", CanonicalRuleType.RECOMMENDATION),
    ("should not", CanonicalRuleType.RECOMMENDATION),
    ("are expected to", CanonicalRuleType.RECOMMENDATION),
    ("are expected not to", CanonicalRuleType.RECOMMENDATION),
    ("is expected", CanonicalRuleType.RECOMMENDATION),
    ("will be expected to", CanonicalRuleType.RECOMMENDATION),
    ("expects", CanonicalRuleType.RECOMMENDATION),
    ("will endeavor to", CanonicalRuleType.RECOMMENDATION),
]


@pytest.mark.parametrize("modality,rule_type", _SOFT_BUT_DECIDES)
def test_a_soft_modality_still_decides(modality, rule_type):
    rule = _rule(rule_type, modality=modality)
    assert not states_no_testable_proposition(rule), (
        f"{modality!r} was read as stating no proposition — it is soft, not absent, "
        "and a case can satisfy or fail it"
    )


#: The hard operators, one per force. Nothing here should ever be in doubt;
#: they are pinned because a regression that reached them would be severe.
_HARD = [
    ("shall", CanonicalRuleType.OBLIGATION),
    ("must", CanonicalRuleType.OBLIGATION),
    ("will", CanonicalRuleType.OBLIGATION),
    ("are required to", CanonicalRuleType.OBLIGATION),
    ("is responsible for", CanonicalRuleType.OBLIGATION),
    ("mandatory", CanonicalRuleType.OBLIGATION),
    ("may", CanonicalRuleType.PERMISSION),
    ("can", CanonicalRuleType.PERMISSION),
    ("reserves the right to", CanonicalRuleType.PERMISSION),
    ("is entitled to", CanonicalRuleType.ENTITLEMENT),
    ("shall not", CanonicalRuleType.PROHIBITION),
    ("may not", CanonicalRuleType.PROHIBITION),
    ("must not", CanonicalRuleType.PROHIBITION),
    ("will not", CanonicalRuleType.PROHIBITION),
    ("are not allowed", CanonicalRuleType.PROHIBITION),
    ("strictly forbidden", CanonicalRuleType.PROHIBITION),
    ("is strictly prohibited", CanonicalRuleType.PROHIBITION),
]


@pytest.mark.parametrize("modality,rule_type", _HARD)
def test_a_deontic_operator_decides(modality, rule_type):
    rule = _rule(rule_type, modality=modality)
    assert not states_no_testable_proposition(rule)


#: Verbatim prohibitions that `Evaluability` calls `underspecified` — the
#: design this file exists to prevent. Each names a subject and a verb and
#: nothing else, which is all a categorical ban needs.
_CATEGORICAL_BANS = [
    ("Slippers", "strictly not allowed", "are allowed"),
    ("Alcohol and drugs", "strictly forbidden", "are forbidden"),
    ("Deliberate reckless or careless damage to GMU's property", "will not", "be tolerated"),
    ("'Noisy' accessories", "are not allowed", "are allowed"),
]


@pytest.mark.parametrize("subject,modality,predicate", _CATEGORICAL_BANS)
def test_a_categorical_ban_decides_without_a_test_to_apply(subject, modality, predicate):
    """No condition, no threshold, no authority — and a verdict every time.

    `Evaluability` reports every one of these `underspecified`, because it
    measures whether the rule gives you something to test *against*. That is a
    different question from whether it decides, and conflating the two would
    have stripped DENY from eleven live prohibitions.
    """

    rule = _rule(
        CanonicalRuleType.PROHIBITION,
        subject=subject,
        modality=modality,
        predicate=predicate,
    )
    assert not states_no_testable_proposition(rule)


def test_no_modality_at_all_is_not_a_courtesy():
    """354 of 1,150 corpus records populate no modality. None become guidance.

    Absence is not politeness. "Emergency leave of absence is granted to an
    employee due to death of his/her first relatives" writes no modal word and
    grants an entitlement.
    """

    rule = _rule(CanonicalRuleType.ENTITLEMENT, modality=None, predicate="is granted")
    assert not states_no_testable_proposition(rule)


def test_please_elsewhere_in_the_sentence_is_not_read():
    """The match is on the modality field, never on the sentence.

    "Employees shall please the customer" is an obligation whose predicate
    happens to contain the word. A check that read the sentence would void it.
    """

    rule = _rule(
        CanonicalRuleType.OBLIGATION,
        modality="shall",
        predicate="please",
        obj="the customer",
    )
    assert not states_no_testable_proposition(rule)


# --------------------------------------------------------------------------
# The consumer side: what an informational effect buys
# --------------------------------------------------------------------------


def test_yields_no_verdict_reads_the_effect_not_the_type():
    """The predicate the decidability checks consult is about force, not label.

    `HUMAN_JUDGMENT_REQUIREMENT` is kept on guidance records because it is the
    honest description of what they are *for*. It is the effect that says
    whether the record takes part in a determination, so that is what is read.
    """

    from policy_platform.contracts.conditions import AllCondition

    from tests.fixtures.factories import make_rule

    def _record(effect_type: EffectType):
        return make_rule(
            rule_id="AI-test",
            condition=AllCondition(all=[]),
            rule_type="human_judgment_requirement",
            effect_type=effect_type,
            effect_action="check with HR",
        )

    assert yields_no_verdict(_record(EffectType.INFORMATIONAL))
    assert not yields_no_verdict(_record(EffectType.REQUIRE_ACTION))
    assert not yields_no_verdict(_record(EffectType.DENY))


def test_the_courtesy_list_can_only_hold_politeness_markers():
    """A structural guard on the list, not on its current contents.

    The list is safe because of what it may contain. If a future entry names a
    topic, an actor or a deontic operator it stops being a closed function-word
    class and becomes a content classifier, which is how this kind of check
    goes wrong quietly.
    """

    from policy_platform.contracts.formulation import _COURTESY_MODALITIES

    forbidden = {
        "shall", "must", "may", "will", "should", "can", "expected", "required",
        "entitled", "forbidden", "prohibited", "allowed", "responsible", "not",
    }
    for entry in _COURTESY_MODALITIES:
        assert entry == entry.casefold(), f"{entry!r} is not folded"
        words = set(entry.split())
        overlap = words & forbidden
        assert not overlap, (
            f"{entry!r} contains {sorted(overlap)} — that is a deontic operator, "
            "not a politeness marker, and it would void real rules"
        )


# --------------------------------------------------------------------------
# The two checks that reported the record, each shown silent on guidance and
# still firing on an otherwise-identical record that does decide.
#
# One field differs between the pair. That is the point: it proves the
# exoneration is the informational effect and not some other difference in the
# fixture, and it proves widening the check did not make it vacuous.
# --------------------------------------------------------------------------


#: Verbatim. The sentence the user's report named.
COVID_GUIDANCE = (
    "Please check with the HR department about the latest Covid regulations as "
    "these are subject to change as per the Ministry of Health"
)


def _extracted(modality: str | None, rule_type=CanonicalRuleType.RECOMMENDATION):
    """Drive the real mapping and return the record it produces.

    `formulation_to_candidate_rules` is the function extraction actually calls,
    so its `Effect.type` is the value that reaches the stored JSON, the
    evaluator, the XACML projection and every badge in the interface. Asserting
    on the predicate alone would prove the judgement is correct without proving
    it is ever applied.
    """

    from policy_platform.contracts.formulation import PolicyFormulation
    from policy_platform.infrastructure.extraction.formulation_mapping import (
        formulation_to_candidate_rules,
    )

    policy = CanonicalPolicy(
        source_text=COVID_GUIDANCE,
        rule=CanonicalPolicyRule(
            rule_type=rule_type,
            subject="you",
            modality=modality,
            predicate="check with",
            object="the HR department about the latest Covid regulations",
        ),
    )
    rules, _ = formulation_to_candidate_rules(
        PolicyFormulation(canonical_policies=[policy]),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )
    return rules[0] if rules else None


def test_extraction_writes_informational_into_the_record():
    """The user asked for this in the JSON, at extraction. This is that.

    The effect is the single place the judgement is recorded. Everything
    downstream — the engine's combining algorithm, the XACML projection, the
    decidability checks — reads it rather than re-deriving it, so one rule
    cannot be guidance in one view and an obligation in another.
    """

    record = _extracted("Please")
    assert record is not None
    assert record.effect.type is EffectType.INFORMATIONAL

    # The rule type is deliberately untouched: it is the honest description of
    # what the record is for, and reviewers filter on it.
    assert record.rule_type.value == "human_judgment_requirement"


def test_extraction_leaves_a_real_modal_deciding():
    """The control. Same sentence, same empty decomposition, a real modal."""

    record = _extracted("shall")
    assert record is not None
    assert record.effect.type is EffectType.REQUIRE_ACTION


def test_the_condition_check_is_silent_on_what_extraction_marked_informational():
    """`source_condition_not_captured`, end to end.

    "subject to change" is conditional language and nothing captured it. Both
    halves are true and the finding was still wrong: the record's whole content
    is "go and ask", so there is no dependency it failed to record.

    Driven from the extraction output rather than a hand-built record, so a
    regression anywhere along that path fails here.
    """

    from policy_platform.infrastructure.quality.policy_faithfulness import (
        check_source_conditions_reached_canonical,
    )

    assert check_source_conditions_reached_canonical(_extracted("Please")) is None

    finding = check_source_conditions_reached_canonical(_extracted("shall"))
    assert finding is not None, (
        "widening the check made it vacuous — the control record states a "
        "conditional its decomposition never recorded and must still be reported"
    )
    assert finding.code == "source_condition_not_captured"


def test_the_judge_check_is_silent_on_what_extraction_marked_informational():
    """`not_decidable_as_written`, via `unanswered_for_judge`, end to end.

    The record declares no fact model, so a judge is indeed told nothing about
    what a case must establish. There is no case to establish anything about.
    """

    from policy_platform.contracts.policy import unanswered_for_judge

    assert unanswered_for_judge(_extracted("Please")) == []

    # The control is not exonerated. Which question it leaves open depends on
    # what this fixture supplies, so the guarantee pinned here is the one that
    # matters: a record that decides is still asked whether it decides well.
    assert unanswered_for_judge(_extracted("shall")), (
        "widening the check made it vacuous — a record with a real modal must "
        "still be examined"
    )
