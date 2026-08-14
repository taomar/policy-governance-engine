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

Two places read the negation, and until a mutation run said otherwise only one
of them was covered here. `build_xacml_view` produces the projection; the rule
mapper produces `Effect.type`, which is what the evaluator and every badge in
the interface actually read. Breaking the second changed nothing in this file,
so the more consequential of the two was the untested one.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    PolicyFormulation,
)
from policy_platform.contracts.policy import EffectType, RuleType
from policy_platform.contracts.xacml_projection import NormativeModality, RuleEffect
from policy_platform.infrastructure.extraction.formulation_mapping import formulation_to_candidate_rules
from policy_platform.infrastructure.projection.xacml_projection import build_xacml_view


def _rule(rule_type: CanonicalRuleType, modality: str | None, **fields) -> CanonicalPolicyRule:
    return CanonicalPolicyRule(rule_type=rule_type, modality=modality, **fields)


def _view(rule_type: CanonicalRuleType, modality: str | None, **fields):
    policy = CanonicalPolicy(
        source_text=fields.pop("source_text", "A stated rule."),
        rule=CanonicalPolicyRule(rule_type=rule_type, modality=modality, **fields),
    )
    return build_xacml_view(policy)


def _effect(rule_type: CanonicalRuleType, modality: str | None, **fields):
    """The rule mapper's `Effect.type` for one canonical policy.

    The output the evaluator reads and the interface badges, as distinct from
    the projection above.
    """

    policy = CanonicalPolicy(
        source_text=fields.pop("source_text", "A stated rule."),
        rule=CanonicalPolicyRule(rule_type=rule_type, modality=modality, **fields),
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

    from policy_platform.infrastructure.extraction.formulation_mapping import states_a_negation

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

    from policy_platform.infrastructure.extraction.formulation_mapping import states_a_negation

    assert states_a_negation(_rule(CanonicalRuleType.OBLIGATION, None, predicate=predicate)) is (
        False
    )


# --------------------------------------------------------------------------
# The effect the evaluator reads
# --------------------------------------------------------------------------


#: Rule types whose *effect* is positive, which is what the guard acts on.
#:
#: Narrower than `_POSITIVE_TYPES` by one: a calculation maps to
#: `INFORMATIONAL`, and negating a statement of how something is worked out
#: does not make it a prohibition. The guard deliberately leaves it alone, so
#: asserting DENY there would pin behaviour the mapping does not intend.
_POSITIVE_EFFECT_TYPES = [
    CanonicalRuleType.OBLIGATION,
    CanonicalRuleType.PERMISSION,
    CanonicalRuleType.ENTITLEMENT,
    CanonicalRuleType.ELIGIBILITY,
    CanonicalRuleType.CONDITIONAL_OUTCOME,
]


@pytest.mark.parametrize("rule_type", _POSITIVE_EFFECT_TYPES)
@pytest.mark.parametrize("modality", _NEGATIONS)
def test_a_negated_sentence_never_becomes_a_permission_or_a_duty(rule_type, modality):
    """The output that decides cases, not just the one that describes them.

    `Effect.type` is what the evaluator acts on and what the interface badges.
    A mutation run found this path uncovered: removing its negation guard
    entirely broke nothing, while the projection beside it was tested from
    every angle. The more consequential of the two was the untested one.
    """

    rule = _effect(rule_type, modality, subject="a party", predicate="disclose")

    assert rule is not None
    assert rule.effect.type is EffectType.DENY
    assert rule.rule_type is RuleType.PROHIBITION


def test_a_negation_in_the_predicate_denies_in_the_effect_too():
    """Both places the source writes it, on the path that decides."""

    rule = _effect(
        CanonicalRuleType.CONDITIONAL_OUTCOME,
        None,
        subject="the increase",
        predicate="not exceeding",
        threshold="5% of the base",
    )

    assert rule is not None
    assert rule.effect.type is EffectType.DENY


def test_an_unnegated_sentence_keeps_its_effect():
    """The guard must not fire on everything; a permission stays a permission."""

    rule = _effect(
        CanonicalRuleType.PERMISSION, "may", subject="a party", predicate="request leave"
    )

    assert rule is not None
    assert rule.effect.type is not EffectType.DENY


def test_a_definition_is_never_turned_into_a_denial():
    """"X does not mean Y" still defines rather than forbids."""

    rule = _effect(
        CanonicalRuleType.DEFINITION, "does not", subject="dependant", predicate="mean"
    )

    assert rule is not None
    assert rule.effect.type is not EffectType.DENY


# --------------------------------------------------------------------------
# The negation written into the subject
#
# The third slot, and the one that hid longest, because a negatively
# quantified subject leaves both other slots looking positive: "No one should
# use profanity" has the affirmative modal "should" and the affirmative
# predicate "use". A guard reading only those two saw an ordinary obligation.
#
# Every case below is taken verbatim from RUN-83257A81, a 45-page staff
# handbook, where four records reached the reviewer stating the inverse of
# their source — among them `require_action("use profanity")`.
# --------------------------------------------------------------------------


#: (subject, modality, predicate, object) as the formulator recorded them.
_NEGATED_SUBJECTS = [
    ("No one", "should", "use", "profanity"),
    ("No one", "should", "show", "disrespect"),
    ("No one", "should", "engage in", "any activity that could harm the reputation"),
    ("no concessions or consideration", "shall", "be given", "for records of previous service"),
    ("No candidate", "shall", "be hired", "for a position"),
    ("No students", "will", "be employed", None),
    ("Neither party", "may", "terminate", "the agreement"),
    ("None of the staff", "will", "receive", "an exemption"),
    ("Nobody", "shall", "enter", "the restricted area"),
]


@pytest.mark.parametrize("subject,modality,predicate,obj", _NEGATED_SUBJECTS)
def test_a_negation_in_the_subject_denies(subject, modality, predicate, obj):
    """A negative quantifier negates the proposition, not just the noun."""

    rule = _effect(
        CanonicalRuleType.RECOMMENDATION,
        modality,
        subject=subject,
        predicate=predicate,
        object=obj,
    )

    assert rule is not None
    assert rule.effect.type is EffectType.DENY, (
        f"{subject!r} {modality} {predicate} projected as "
        f"{rule.effect.type.value}({rule.effect.action!r}) — the inverse of the source"
    )


#: Subjects that merely begin with the same letters, or state a bound. None is
#: a negation, and reading any of them as one would invert a live rule — the
#: defect above arrived at from the opposite direction.
_INNOCENT_SUBJECTS = [
    "No-fault termination",
    "Normal working hours",
    "Notice periods",
    "Nothing-to-declare channels",
    "Northern campus staff",
    "no less than three members",
    "no later than the first working day",
    "the employee",
    "all its employees",
]


@pytest.mark.parametrize("subject", _INNOCENT_SUBJECTS)
def test_a_subject_that_merely_looks_negative_is_left_alone(subject):
    """The control. A guard matching "no" as a prefix would fail every one."""

    from policy_platform.infrastructure.extraction.formulation_mapping import (
        has_negative_subject,
    )

    assert has_negative_subject(subject) is False


def test_a_negated_subject_is_shared_with_the_projection_too():
    """One definition of a negation, across all three slots and both readers.

    Uses a `conditional_outcome`, taken from AI-d36d4bd5b1 ("no concessions or
    consideration shall be given for records of previous service"), because a
    `recommendation` deliberately projects no XACML effect at all — it is not a
    XACML Rule, so it could not demonstrate agreement between the two readers.
    """

    from policy_platform.infrastructure.extraction.formulation_mapping import states_a_negation

    fields = dict(
        subject="no concessions or consideration",
        predicate="be given",
        object="for records of previous service",
    )

    assert states_a_negation(_rule(CanonicalRuleType.CONDITIONAL_OUTCOME, "shall", **fields)) is True

    view = _view(CanonicalRuleType.CONDITIONAL_OUTCOME, "shall", **fields)
    assert view is not None
    assert view.xacml_projection.effect is RuleEffect.DENY


# --------------------------------------------------------------------------
# The negation written twice
# --------------------------------------------------------------------------


def test_a_denial_does_not_negate_an_already_negated_action():
    """`deny(refrain from X)` reads as *X is required*.

    Taken from AI-dd2f1b1d53: "expects all its employees ... to refrain from
    any illegal, dishonest, or unethical conduct" is a prohibition, and it was
    typed as one — but the action slot kept the abstaining verb, so the effect
    negated a phrase that had already negated itself. The polarity has to be
    carried exactly once.
    """

    rule = _effect(
        CanonicalRuleType.PROHIBITION,
        "expects",
        subject="all its employees",
        predicate="refrain from",
        object="any illegal, dishonest, or unethical conduct",
    )

    assert rule is not None
    assert rule.effect.type is EffectType.DENY
    assert rule.effect.action == "any illegal, dishonest, or unethical conduct"


def test_a_requirement_to_refrain_keeps_its_words():
    """The control. `require_action(refrain from X)` is already correct.

    Only a denial doubles the negation. Stripping the wrapper here would turn
    a faithful record into an instruction to do the thing the source asks
    employees to avoid.
    """

    rule = _effect(
        CanonicalRuleType.RECOMMENDATION,
        "should",
        subject="employees",
        predicate="refrain themselves from",
        object="loose talks",
    )

    assert rule is not None
    assert rule.effect.type is EffectType.REQUIRE_ACTION
    assert rule.effect.action == "refrain themselves from loose talks"


def test_an_ordinary_denial_keeps_its_action_intact():
    """The other control: a denial whose action does not negate is untouched."""

    rule = _effect(
        CanonicalRuleType.PROHIBITION,
        "may",
        subject="No employee or applicant",
        predicate="falsify",
        object="any application or record",
    )

    assert rule is not None
    assert rule.effect.type is EffectType.DENY
    assert rule.effect.action == "falsify any application or record"
