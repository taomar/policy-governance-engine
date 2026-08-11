"""The second pass that re-reads a rule against the source it cites.

Every check here exists because the corresponding defect was found in real
extracted output, so the tests are written from those cases rather than from
imagined ones — and each records the precision problem that shaped it.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition, FactComparisonCondition, ConditionOperator
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EffectType, RuleFormulation
from policy_platform.infrastructure.policy_faithfulness import find_duplicate_rules, validate_rule
from tests.fixtures.factories import make_rule


def _rule(
    *,
    source: str,
    action: str,
    effect: EffectType = EffectType.REQUIRE_ACTION,
    condition_text: str = "",
    condition=None,
):
    rule = make_rule("R1", condition or AllCondition(all=[]), effect_type=effect, effect_action=action)
    rule.formulation = RuleFormulation(
        source_index=0,
        canonical=CanonicalPolicy(
            source_text=source,
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="Annual increase",
                predicate="exceed",
                condition=condition_text,
            ),
        ),
        dmn_decisions=[],
    )
    return rule


def _codes(rule):
    return {f.code for f in validate_rule(rule)}


class TestNegationPreserved:
    def test_stripped_negation_is_reported(self):
        # The real case: "shall not exceed 10%" became an obligation to exceed
        # 10% — the opposite of the policy, with the same citation.
        rule = _rule(
            source="3.2.1. Annual increase which shall not exceed 10% of the current basic salary.",
            action="exceed 10% of the current basic salary",
        )

        assert "negation_dropped" in _codes(rule)

    def test_negation_inside_a_condition_is_not_reported(self):
        # The precision case. An earlier version flagged any "not" in the first
        # half of the source and was right half the time: here the negation
        # qualifies *which clinics*, while the obligation to submit is real.
        # A check that cries wolf on half its findings teaches a reviewer to
        # skip it, which leaves the true inversions less visible than before.
        rule = _rule(
            source=(
                "In the case of medical treatment in clinics that are not approved by the "
                "insurance company, the original receipt shall be submitted to Human Resources."
            ),
            action="be submitted to the Human Resources Department",
        )

        assert "negation_dropped" not in _codes(rule)

    def test_action_that_keeps_the_negation_is_not_reported(self):
        rule = _rule(
            source="FBSU will not bear any responsibility for excluded coverage.",
            action="will not bear any responsibility",
        )

        assert "negation_dropped" not in _codes(rule)

    def test_deny_effect_is_never_reported(self):
        rule = _rule(
            source="Annual increase shall not exceed 10% of the current basic salary.",
            action="exceed 10% of the current basic salary",
            effect=EffectType.DENY,
        )

        assert "negation_dropped" not in _codes(rule)


class TestQuantitiesPreserved:
    def test_dropped_limit_is_reported(self):
        # "not exceeding 5%" becoming "not exceeding" reads as a complete rule
        # and enforces nothing.
        rule = _rule(
            source="Increase due to inflation with a percentage not exceeding 5% of basic salary.",
            action="be increased due to inflation",
        )

        assert "quantity_dropped" in _codes(rule)

    def test_limit_carried_in_the_action_is_not_reported(self):
        rule = _rule(
            source="Increase due to inflation with a percentage not exceeding 5% of basic salary.",
            action="be increased by no more than 5%",
        )

        assert "quantity_dropped" not in _codes(rule)

    def test_limit_carried_in_the_condition_tree_is_not_reported(self):
        # A quantity is preserved whether it landed in the action or in the
        # compiled condition; demanding one location would report faithful
        # rules as defective.
        rule = _rule(
            source="Annual leave shall be 30 days per year.",
            action="grant annual leave",
            condition=AllCondition(
                all=[
                    FactComparisonCondition(
                        fact="leave.days", operator=ConditionOperator.EQUALS, value=30
                    )
                ]
            ),
        )

        assert "quantity_dropped" not in _codes(rule)

    def test_unit_wording_difference_is_not_reported(self):
        # The source may write "10%" where the rule writes "10 percent".
        rule = _rule(
            source="The increase shall not be more than 10% of basic salary.",
            action="limit the increase to 10 percent",
        )

        assert "quantity_dropped" not in _codes(rule)


class TestConditionsRepresented:
    def test_lost_condition_is_reported(self):
        rule = _rule(
            source="Leave is granted where the employee has completed probation.",
            action="grant leave",
            condition_text="where the employee has completed probation",
        )

        assert "condition_lost" in _codes(rule)

    def test_condition_carried_as_prose_is_not_reported(self):
        # Carried but not compiled is a mapping gap, recorded elsewhere. Nothing
        # was lost, so it is not a faithfulness failure.
        rule = _rule(
            source="Leave is granted where the employee has completed probation.",
            action="grant leave where the employee has completed probation",
            condition_text="where the employee has completed probation",
        )

        assert "condition_lost" not in _codes(rule)


class TestActionIsNotAFragment:
    def test_trailing_preposition_is_reported(self):
        # The tell that a value-deriving rule was projected as an obligation.
        rule = _rule(
            source="The allowance is calculated as twice the basic salary up to a maximum of 15,000 SAR.",
            action="is calculated as twice the monthly basic salary up to a maximum of",
        )

        assert "action_fragment" in _codes(rule)

    def test_complete_action_is_not_reported(self):
        rule = _rule(
            source="The employee shall submit the receipt to Human Resources.",
            action="submit the receipt to Human Resources",
        )

        assert "action_fragment" not in _codes(rule)

    def test_informational_effect_is_never_reported(self):
        rule = _rule(
            source="The allowance is calculated as twice the basic salary up to a maximum of",
            action="is calculated as twice the basic salary up to a maximum of",
            effect=EffectType.INFORMATIONAL,
        )

        assert "action_fragment" not in _codes(rule)


class TestTheProvenanceNoteMustNotSatisfyTheCheck:
    """The note that reports the loss is not evidence against it.

    `formulation_mapping` appends a provenance note to every description, and
    that note quotes the very condition it is reporting as unprojected. The
    surface used by `check_condition_preserved` included `description`, so the
    condition was found every single time and the check returned no finding —
    for exactly the rules it was written to catch.

    It reported zero findings across 47 live rules while three housing-allowance
    rules had each dropped the staff category that distinguished them, leaving
    two of them identical on screen. This test fails if `description` is ever
    let back into that surface.
    """

    _CONDITION = "for administrative, technical and service staff"
    _NOTE = (
        "[Conditions: conditions_not_projected — The source states conditions, but they "
        f"could not be projected into executable bindings: '{_CONDITION}'. The rule must "
        "not be treated as unconditional — a reviewer must supply the missing mapping.]"
    )

    def _housing_rule(self):
        """AI-c4c43499ce, as the live extraction produced it."""

        rule = _rule(
            source="⁃ Fifteen thousand (15,000) SAR for administrative, technical and service staff.",
            action="up to a maximum of Fifteen thousand (15,000) SAR",
            effect=EffectType.INFORMATIONAL,
            condition_text=self._CONDITION,
        )
        rule.description = f"Fifteen thousand (15,000) SAR.\n\n{self._NOTE}"
        return rule

    def test_the_lost_condition_is_reported(self):
        assert "condition_lost" in _codes(self._housing_rule())

    def test_the_note_alone_does_not_count_as_carrying_it(self):
        """The exact regression: with `description` in the surface this passed,
        and the check went silent across the whole corpus."""

        rule = self._housing_rule()
        assert self._CONDITION in rule.description
        assert "condition_lost" in _codes(rule)

    def test_a_condition_genuinely_carried_in_the_action_is_not_reported(self):
        """Guard the other direction: the check must stay quiet when the
        condition really did reach an operative field, or it becomes noise on
        every rule."""

        rule = _rule(
            source="Paid for administrative, technical and service staff.",
            action="pay for administrative, technical and service staff",
            effect=EffectType.REQUIRE_ACTION,
            condition_text="for administrative, technical and service staff",
        )
        rule.description = "unrelated prose"
        assert "condition_lost" not in _codes(rule)


class TestDuplicateDetection:
    """Both directions, from live output.

    A clause boundary fell inside "The housing allowance is limited to one
    employee of the married couple (husband and wife). In the case of…", so the
    second clause begins mid-sentence and the formulator reconstructs the
    governing sentence that the first clause had already produced.
    """

    def _housing(self, *, rule_id, obj, condition, action):
        rule = _rule(
            source="⁃ Fifteen thousand (15,000) SAR for administrative staff.",
            action=action,
            effect=EffectType.INFORMATIONAL,
            condition_text=condition,
        )
        rule.rule_id = rule_id
        rule.formulation.canonical.rule.subject = "The housing allowance per calendar year (12 months)"
        rule.formulation.canonical.rule.predicate = "up to a maximum of"
        rule.formulation.canonical.rule.object = obj
        return rule

    def test_two_staff_categories_at_the_same_amount_are_not_duplicates(self):
        """The false positive this check produced on its first run.

        Both are capped at 15,000 SAR; one is for administrative, technical and
        service staff and the other for lecturers and instructors. Keying
        without the condition dropped the only field that separates them —
        exactly the failure the module exists to catch.
        """

        rules = [
            self._housing(
                rule_id="AI-admin",
                obj="Fifteen thousand (15,000) SAR",
                condition="for administrative, technical and service staff",
                action="up to a maximum of Fifteen thousand (15,000) SAR",
            ),
            self._housing(
                rule_id="AI-lect",
                obj="Fifteen thousand (15,000) SAR",
                condition="for full time lecturers, instructors, assistant instructors",
                action="up to a maximum of Fifteen thousand (15,000) SAR",
            ),
        ]
        assert find_duplicate_rules(rules) == []

    def test_the_same_sentence_split_across_two_clauses_is_reported(self):
        """The genuine pair. One decomposition put "of the married couple" in
        the condition, the other folded it into the object; joined, they read
        identically, which is the truth."""

        a = self._housing(
            rule_id="AI-first",
            obj="one employee",
            condition="of the married couple",
            action="is limited to one employee",
        )
        b = self._housing(
            rule_id="AI-second",
            obj="one employee of the married couple",
            condition="",
            action="is limited to one employee of the married couple",
        )
        for r in (a, b):
            r.formulation.canonical.rule.subject = "The housing allowance"
            r.formulation.canonical.rule.predicate = "is limited to"
        findings = find_duplicate_rules([a, b])
        assert [f.code for f in findings] == ["duplicate_rule"]
        assert findings[0].rule_id == "AI-second"

    def test_a_differing_action_does_not_hide_a_duplicate(self):
        """The action is derived from subject/predicate/object, so including it
        in the key double-counted them — and a difference in that derivation
        was enough to hide the pair above."""

        a = self._housing(
            rule_id="AI-x", obj="one employee", condition="of the married couple", action="A"
        )
        b = self._housing(
            rule_id="AI-y", obj="one employee of the married couple", condition="", action="B"
        )
        for r in (a, b):
            r.formulation.canonical.rule.subject = "The housing allowance"
            r.formulation.canonical.rule.predicate = "is limited to"
        assert len(find_duplicate_rules([a, b])) == 1

    def test_an_empty_decomposition_is_not_a_duplicate_of_another(self):
        rules = [_rule(source="s", action=""), _rule(source="s", action="")]
        for r in rules:
            r.formulation.canonical.rule.subject = ""
            r.formulation.canonical.rule.predicate = ""
            r.formulation.canonical.rule.object = ""
            r.formulation.canonical.rule.condition = ""
            r.effect.action = ""
        assert find_duplicate_rules(rules) == []


class TestDuplicateDetectionIsSlotIndependent:
    """The generalisation that named fields could not reach.

    Keying on named slots lost the same race twice: `object` alone raised a
    false positive on two staff categories, and `object` + `condition` still
    missed a pair whose content had moved into `constraint` and `frequency`.
    A slot assignment is a judgement the formulator makes per run, so no fixed
    list of slots is stable across runs.
    """

    def _rule_with(self, rule_id, **fields):
        rule = _rule(source="s", action=fields.pop("action", ""), effect=EffectType.INFORMATIONAL)
        rule.rule_id = rule_id
        pr = rule.formulation.canonical.rule
        pr.subject = fields.pop("subject", "The housing allowance")
        pr.predicate = fields.pop("predicate", "be paid")
        pr.condition = None
        pr.object = None
        for name, value in fields.items():
            setattr(pr, name, value)
        return rule

    def test_content_moving_between_slots_is_still_one_rule(self):
        """The pair named-field keying missed: "in monthly prorated
        installments" as one object, against the same content split across
        `constraint` and `frequency`."""

        a = self._rule_with("AI-a", object="in monthly prorated installments", frequency="monthly")
        b = self._rule_with("AI-b", constraint="prorated installments", frequency="monthly")
        assert [f.rule_id for f in find_duplicate_rules([a, b])] == ["AI-b"]

    def test_a_seam_connective_does_not_make_two_rules(self):
        """"one employee" + "of the married couple" against "one employee of
        the married couple" — the seam word is the only difference."""

        a = self._rule_with("AI-a", predicate="is limited to", object="one employee",
                            condition="of the married couple")
        b = self._rule_with("AI-b", predicate="is limited to",
                            object="one employee of the married couple")
        assert len(find_duplicate_rules([a, b])) == 1

    def test_different_content_words_are_not_duplicates(self):
        """The false positive the first version produced: same cap, different
        staff categories."""

        a = self._rule_with("AI-admin", predicate="up to a maximum of",
                            object="Fifteen thousand (15,000) SAR",
                            condition="for administrative, technical and service staff")
        b = self._rule_with("AI-lect", predicate="up to a maximum of",
                            object="Fifteen thousand (15,000) SAR",
                            condition="for full time lecturers and instructors")
        assert find_duplicate_rules([a, b]) == []

    def test_a_meaning_inverting_preposition_is_not_a_seam_word(self):
        """"paid by HR" and "paid to HR" name different parties. Stripping
        those would report two real rules as one copy."""

        a = self._rule_with("AI-by", object="by the Human Resources Department")
        b = self._rule_with("AI-to", object="to the Human Resources Department")
        assert find_duplicate_rules([a, b]) == []

    def test_reversing_subject_and_predicate_is_not_a_duplicate(self):
        """Anchors are compared separately so "A limits B" and "B limits A"
        cannot collide through the content bag."""

        a = self._rule_with("AI-a", subject="The allowance", predicate="limits", object="the employee")
        b = self._rule_with("AI-b", subject="The employee", predicate="limits", object="the allowance")
        assert find_duplicate_rules([a, b]) == []

    def test_word_order_within_a_slot_does_not_matter(self):
        a = self._rule_with("AI-a", object="basic salary monthly")
        b = self._rule_with("AI-b", object="monthly basic salary")
        assert len(find_duplicate_rules([a, b])) == 1
