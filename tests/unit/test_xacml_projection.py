"""XACML projection — the three layers must never be collapsed again.

Cases A through K are the regression requirements named in the correction that
prompted this module. Each proves a *layer separation*, not a label: the point
is that source semantics, fact-model readiness and PDP runtime results are
independent, and that the previous implementation collapsed all three into one
`Indeterminate · missing-attribute` badge.
"""

from __future__ import annotations

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.xacml_projection import (
    CompilationStatus,
    EntityRole,
    FactModelStatus,
    NormativeModality,
    PredicateStatus,
    RuleEffect,
)
from policy_platform.infrastructure.xacml_projection import (
    build_xacml_view,
    classify_entities,
    is_passive_predicate,
    normalize_action,
    split_conditions,
)


class TestA_ResolvedPredicateSurvivesAMissingFactModel:
    """"after the trial period has expired" produces a resolved Boolean
    predicate regardless of whether the fact model contains that attribute."""

    def _view(self):
        return build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "The allowance is paid after the trial period has expired."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="The allowance",
                    predicate="is paid",
                    condition="after the trial period has expired",
                ),
            )
        )

    def test_predicate_is_resolved(self) -> None:
        condition = self._view().source_semantics.conditions[0]
        assert condition.predicate_status is PredicateStatus.RESOLVED

    def test_predicate_is_a_boolean_equality_on_the_named_concept(self) -> None:
        condition = self._view().source_semantics.conditions[0]
        assert condition.concept == "trial-period"
        assert condition.operator == "boolean-equal"
        assert condition.value == "true"

    def test_fact_model_is_missing_and_that_does_not_change_the_semantics(self) -> None:
        """The two axes are independent. A perfectly stated condition we
        cannot yet supply an attribute for is `resolved` + `missing`."""

        condition = self._view().source_semantics.conditions[0]
        assert condition.predicate_status is PredicateStatus.RESOLVED
        assert condition.fact_model_status is FactModelStatus.MISSING

    def test_readiness_reports_the_gap_separately(self) -> None:
        readiness = self._view().fact_model_readiness
        assert [a.attribute_id for a in readiness.missing] == ["trial-period"]
        assert not readiness.ready


class TestB_DependencyWithoutAStatedTest:
    """"depending on the financial position of the University" produces a
    source-stated dependency with an unresolved predicate."""

    def _view(self):
        return build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "Employee basic salary shall be increased depending on the "
                    "financial position of the University."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
                    subject="Employee basic salary",
                    modality="shall",
                    predicate="be increased",
                    condition="depending on the financial position of the University",
                ),
            )
        )

    def test_predicate_is_unresolved(self) -> None:
        condition = self._view().source_semantics.conditions[0]
        assert condition.predicate_status is PredicateStatus.UNRESOLVED

    def test_no_operator_is_invented(self) -> None:
        """The source never says whether this means a threshold, a boolean or
        a judgement. `financial-position = good` would manufacture the policy."""

        condition = self._view().source_semantics.conditions[0]
        assert condition.operator is None
        assert condition.value is None

    def test_the_dependency_is_still_recorded(self) -> None:
        """Unresolved is not discarded. The source said financial position
        matters, and losing that is as wrong as inventing a test for it."""

        condition = self._view().source_semantics.conditions[0]
        assert condition.concept == "financial-position-of-the-university"
        assert "does not state the qualifying" in (condition.unresolved_reason or "")


class TestC_ApprovalConditionIsStructured:
    """"subject to approval of the President" provides sufficient semantics
    for a structured approval condition."""

    def test_approval_is_a_resolved_boolean(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "The recommendations of the director are subject to the approval "
                    "of the President."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.OBLIGATION,
                    subject="The recommendations of the director",
                    predicate="are submitted",
                    condition="subject to the approval of the President",
                    assigner="the President",
                ),
            )
        )
        condition = view.source_semantics.conditions[0]
        assert condition.predicate_status is PredicateStatus.RESOLVED
        assert condition.operator == "boolean-equal"
        assert condition.value == "true"
        assert "president" in condition.concept


class TestD_ANounPhraseIsNeverAutomaticallyTheSubject:
    """"the allowance" is never assigned to subject.subject-id merely because
    it is the main noun phrase."""

    def _view(self):
        return build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "In the case of a married couple employed by FBSU, the allowance "
                    "will be calculated based on the higher basic salary of the couple."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.CALCULATION,
                    subject="the allowance",
                    predicate="will be calculated",
                    condition="In the case of a married couple employed by FBSU",
                    calculation="based on the higher basic salary of the couple",
                ),
            )
        )

    def test_the_allowance_is_not_a_xacml_subject(self) -> None:
        view = self._view()
        assert "the allowance" not in [s.phrase for s in view.source_semantics.subjects]
        assert view.xacml_projection.target.subject_ids == []

    def test_the_allowance_is_a_resource(self) -> None:
        view = self._view()
        assert [r.phrase for r in view.source_semantics.resources] == ["the allowance"]
        assert view.xacml_projection.target.resource_ids == ["allowance"]

    def test_the_classification_records_why(self) -> None:
        """A reviewer must be able to check the basis of any category."""

        resource = self._view().source_semantics.resources[0]
        assert "passive predicate" in resource.basis


class TestE_AnAllowanceWithAnAmountIsNotASubject:
    """"a work nature allowance of 200 SAR per month" is decomposed into
    resource/outcome properties rather than subject.subject-id."""

    def test_the_whole_phrase_never_becomes_a_subject(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "Each of the security employees and cleaning workers is paid a work "
                    "nature allowance at the rate of (200) two hundred SR per month."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="A work nature allowance at the rate of (200) two hundred SR per month",
                    predicate="is paid",
                    beneficiary="each of the security employees and cleaning workers",
                ),
            )
        )
        subjects = [s.phrase for s in view.source_semantics.subjects]
        assert subjects == ["each of the security employees and cleaning workers"]
        assert "allowance" in view.source_semantics.resources[0].phrase.casefold()

    def test_the_party_is_the_subject_not_the_benefit(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Employees are paid an allowance.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="An allowance",
                    predicate="is paid",
                    beneficiary="Employees",
                ),
            )
        )
        assert view.source_semantics.subjects[0].role is EntityRole.SUBJECT
        assert "canonical 'beneficiary'" in view.source_semantics.subjects[0].basis


class TestF_AClauseIsNeverAnActionId:
    """"will be calculated based on the higher basic salary" is not emitted as
    an action.action-id."""

    def test_the_whole_clause_is_not_an_action_id(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="The allowance will be calculated based on the higher basic salary.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.CALCULATION,
                    subject="the allowance",
                    predicate="will be calculated based on the higher basic salary of the couple",
                ),
            )
        )
        assert view.xacml_projection.target.action_ids == ["calculate"]
        assert all(
            "higher basic salary" not in action for action in view.xacml_projection.target.action_ids
        )

    def test_an_unrecognised_predicate_yields_no_action_id_at_all(self) -> None:
        """No action-id is better than a wrong one: an identifier no request
        can carry makes the Target match nothing, silently."""

        assert normalize_action("shall be so noted at the beginning of each policy") is None
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Those policies will be so noted at the beginning of each policy.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.OBLIGATION,
                    subject="Those policies",
                    predicate="be so noted at the beginning of each policy",
                ),
            )
        )
        assert view.xacml_projection.target.action_ids == []
        assert view.source_semantics.action is None

    def test_the_unmatched_clause_is_kept_and_explained(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Those policies will be so noted.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.OBLIGATION,
                    subject="Those policies",
                    predicate="be so noted at the beginning of each policy",
                ),
            )
        )
        unclassified = [e.phrase for e in view.source_semantics.unclassified]
        assert "be so noted at the beginning of each policy" in unclassified

    def test_normalised_verbs_reach_their_lemma(self) -> None:
        assert normalize_action("grants employee benefits") == "grant"
        assert normalize_action("is paid") == "pay"
        assert normalize_action("shall be increased") == "increase"
        assert normalize_action("is approved by the President") == "approve"

    def test_a_noun_buried_in_the_clause_is_not_the_action(self) -> None:
        """"requires the approval of the President" — the verb is "requires"
        and "approval" is a noun naming a *condition*, not the action the rule
        authorises. Matching the noun is the same failure as reading a whole
        clause: it puts something in action.action-id that the sentence never
        asserted as the operation being performed.

        None is the correct answer, and the approval survives as a condition.
        """

        assert normalize_action("requires the approval of the President") is None


class TestG_RuleEffectIsOnlyPermitOrDeny:
    def test_the_enum_has_exactly_two_members(self) -> None:
        """Enforced by the type, not by a convention. A wider type is what let
        `Effect = NotApplicable` be written down in the first place."""

        assert {e.value for e in RuleEffect} == {"Permit", "Deny"}

    def test_a_prohibition_denies(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Annual increase shall not exceed 10% of basic salary.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.PROHIBITION,
                    subject="Annual increase",
                    modality="shall not",
                    predicate="exceed",
                    threshold="10% of basic salary",
                ),
            )
        )
        assert view.xacml_projection.effect is RuleEffect.DENY

    def test_an_obligation_permits_and_carries_the_duty_as_an_obligation(self) -> None:
        """An obligation is not a third effect. XACML puts the mandatory
        behaviour in an ObligationExpression, not in the Effect."""

        view = build_xacml_view(
            CanonicalPolicy(
                source_text="The receipt shall be submitted within 30 days.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.OBLIGATION,
                    subject="The receipt",
                    modality="shall",
                    predicate="be submitted",
                    constraint="within 30 days",
                ),
            )
        )
        assert view.xacml_projection.effect is RuleEffect.PERMIT
        assert "ObligationExpression" in view.xacml_projection.effect_basis
        assert view.xacml_projection.obligation_expressions[0].attributes == {
            "constraint": "within 30 days"
        }


class TestH_NotApplicableIsNeverADeclaredEffect:
    def test_a_definition_declares_no_effect_rather_than_notapplicable(self) -> None:
        """`None` and NotApplicable are different claims. A definition is not a
        Rule at all; NotApplicable would say it is a Rule that did not apply,
        which only a PDP can determine."""

        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Basic salary means the monthly salary before allowances.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.DEFINITION,
                    subject="Basic salary",
                    predicate="means",
                    object="the monthly salary before allowances",
                ),
            )
        )
        assert view.xacml_projection.effect is None
        assert "not a XACML Rule" in view.xacml_projection.effect_basis

    def test_notapplicable_cannot_be_constructed_as_an_effect(self) -> None:
        assert not hasattr(RuleEffect, "NOT_APPLICABLE")
        assert "NotApplicable" not in {e.value for e in RuleEffect}

    def test_a_definition_names_the_defined_term_as_a_resource(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Basic salary means the monthly salary before allowances.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.DEFINITION,
                    subject="Basic salary",
                    predicate="means",
                    object="the monthly salary before allowances",
                ),
            )
        )
        assert view.source_semantics.resources[0].phrase == "Basic salary"
        assert view.source_semantics.normative_modality is NormativeModality.DEFINITION


class TestI_NoRuntimeResultIsProducedAtExtraction:
    """Indeterminate / missing-attribute is not generated during semantic
    extraction solely because the fact model lacks a mapping."""

    def _views(self):
        cases = [
            CanonicalPolicy(
                source_text="The allowance is paid after the trial period has expired.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="The allowance",
                    predicate="is paid",
                    condition="after the trial period has expired",
                ),
            ),
            CanonicalPolicy(
                source_text="Salary increases depend on the financial position of the University.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
                    subject="Salary increases",
                    predicate="depend",
                    condition="depending on the financial position of the University",
                ),
            ),
        ]
        return [build_xacml_view(c) for c in cases]

    def test_runtime_evaluation_is_always_none(self) -> None:
        for view in self._views():
            assert view.runtime_evaluation is None

    def test_no_layer_carries_a_runtime_decision_word(self) -> None:
        """The words themselves must not appear in extraction output. This is
        the badge that started the correction: a PDP result asserted before any
        PDP had run."""

        for view in self._views():
            blob = view.model_dump_json()
            assert "Indeterminate" not in blob
            assert "NotApplicable" not in blob
            assert "missing-attribute" not in blob

    def test_the_missing_mapping_is_reported_as_readiness_not_as_a_decision(self) -> None:
        for view in self._views():
            assert view.fact_model_readiness.missing
            assert view.xacml_projection.compilation_status in {
                CompilationStatus.NOT_EXECUTABLE,
                CompilationStatus.PARTIALLY_EXECUTABLE,
            }


class TestJ_MissingCoverageStaysVisible:
    """Missing fact-model coverage remains visible in readiness metadata —
    removing the wrong badge must not mean going quiet about the gap."""

    def test_every_condition_produces_a_required_attribute(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "FBSU grants employee benefits based on their functions and depending "
                    "on the recommendation of the director of the concerned Department."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.PERMISSION,
                    subject="FBSU",
                    predicate="grants",
                    object="employee benefits",
                    condition="depending on the recommendation of the director of the concerned Department",
                    assigner="the director of the concerned Department",
                ),
            )
        )
        assert len(view.fact_model_readiness.required_attributes) == 1
        attribute = view.fact_model_readiness.required_attributes[0]
        assert attribute.status is FactModelStatus.MISSING
        assert attribute.source_phrase.startswith("depending on the recommendation")

    def test_readiness_quotes_the_source_phrase(self) -> None:
        """Whoever maps this to a customer schema needs to see what it has to
        mean, not just a slug."""

        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Paid after the trial period has expired.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="The allowance",
                    predicate="is paid",
                    condition="after the trial period has expired",
                ),
            )
        )
        assert (
            view.fact_model_readiness.required_attributes[0].source_phrase
            == "after the trial period has expired"
        )


class TestK_RuntimeIndeterminateRemainsLegitimate:
    """An actual PDP evaluation with a required missing attribute may still
    correctly produce Indeterminate/missing-attribute.

    Nothing here forbids that value; the contract reserves the layer for it and
    leaves it empty until a request has actually been evaluated.
    """

    def test_the_runtime_layer_exists_and_is_explicitly_empty(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Paid after the trial period has expired.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.ENTITLEMENT,
                    subject="The allowance",
                    predicate="is paid",
                    condition="after the trial period has expired",
                ),
            )
        )
        assert "runtime_evaluation" in view.model_dump()
        assert view.model_dump()["runtime_evaluation"] is None


class TestVoiceDecidesTheGrammaticalSubjectsRole:
    """The one structural signal separating a resource from an organisation.

    "the allowance will be calculated" and "FBSU grants employee benefits" are
    both grammatical subjects with no party field. Voice is a property of the
    sentence, not a guess about the world, and it is what tells them apart.
    """

    def test_passive_predicate_makes_the_subject_a_resource(self) -> None:
        _, resources, unclassified = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.CALCULATION,
                subject="the allowance",
                predicate="will be calculated",
            ),
            "",
        )
        assert [r.phrase for r in resources] == ["the allowance"]
        assert unclassified == []

    def test_irregular_participles_are_recognised(self) -> None:
        """"is paid" and "is given" are the commonest constructions in benefits
        prose; an -ed/-en rule alone would miss them and leave the classifier
        firing mostly on the rare case."""

        assert is_passive_predicate("is paid")
        assert is_passive_predicate("are given")
        assert is_passive_predicate("shall be increased")
        assert not is_passive_predicate("grants")
        assert not is_passive_predicate("decides on")

    def test_an_active_organisation_is_not_forced_into_a_category(self) -> None:
        """FBSU may be the policy issuer, the employer, a scope or an actor.
        Nothing available distinguishes them, so neither subject nor resource
        may be asserted — the correction that prompted this module says so
        explicitly."""

        subjects, resources, unclassified = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="FBSU",
                predicate="grants",
                object="employee benefits",
            ),
            "",
        )
        assert "FBSU" not in [s.phrase for s in subjects]
        assert "FBSU" not in [r.phrase for r in resources]
        assert "FBSU" in [u.phrase for u in unclassified]

    def test_the_unclassified_entity_says_why(self) -> None:
        _, _, unclassified = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="FBSU",
                predicate="grants",
            ),
            "",
        )
        assert "issuing organisation" in unclassified[0].basis


class TestChainedConditionsAreSeparated:
    """"based on their functions and depending on the recommendation of the
    director of the concerned Department" states two conditions."""

    def test_two_dependencies_become_two_conditions(self) -> None:
        parts = split_conditions(
            "based on their functions and depending on the recommendation of the "
            "director of the concerned Department"
        )
        assert parts == [
            "based on their functions",
            "depending on the recommendation of the director of the concerned Department",
        ]

    def test_a_party_name_containing_and_is_not_split(self) -> None:
        """Splitting on every "and" would break "the director of the concerned
        Department" apart, or separate a couple from their employers."""

        parts = split_conditions(
            "In the case of a married couple are employed by FBSU or Astra Internal School"
        )
        assert parts == [
            "In the case of a married couple are employed by FBSU or Astra Internal School"
        ]

    def test_each_part_is_assessed_independently(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text=(
                    "FBSU grants employee benefits based on their functions and depending "
                    "on the recommendation of the director of the concerned Department."
                ),
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.PERMISSION,
                    subject="FBSU",
                    predicate="grants",
                    object="employee benefits",
                    condition=(
                        "based on their functions and depending on the recommendation of "
                        "the director of the concerned Department"
                    ),
                ),
            )
        )
        conditions = view.source_semantics.conditions
        assert len(conditions) == 2
        assert conditions[0].concept == "functions"
        assert conditions[1].concept == "recommendation-of-the-director-of-the-concerned-department"

    def test_both_appear_in_readiness(self) -> None:
        view = build_xacml_view(
            CanonicalPolicy(
                source_text="Granted based on their functions and depending on the director's recommendation.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.PERMISSION,
                    subject="Benefits",
                    predicate="are granted",
                    condition="based on their functions and depending on the director's recommendation",
                ),
            )
        )
        assert len(view.fact_model_readiness.required_attributes) == 2


class TestEntityClassificationGeneralises:
    """Beyond the named cases — the rule must hold generally, not by example."""

    def test_a_party_field_outranks_the_grammatical_slot(self) -> None:
        subjects, resources, _ = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ENTITLEMENT,
                subject="Annual travel tickets",
                predicate="are provided to",
                beneficiary="Expatriate employees",
            ),
            "",
        )
        assert [s.phrase for s in subjects] == ["Expatriate employees"]
        assert [r.phrase for r in resources] == ["Annual travel tickets"]

    def test_a_delegation_authority_becomes_a_subject(self) -> None:
        subjects, _, _ = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                predicate="be granted",
            ),
            "Exceptional Increase requires the approval of the President.",
        )
        assert [s.phrase for s in subjects] == ["the President"]

    def test_a_party_named_in_both_places_is_listed_once(self) -> None:
        subjects, _, _ = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                predicate="be granted",
                assigner="the President",
            ),
            "Exceptional Increase requires the approval of the President.",
        )
        assert [s.phrase for s in subjects] == ["the President"]

    def test_the_object_is_not_silently_called_a_resource(self) -> None:
        """The canonical object can be a resource, an outcome, or part of the
        action. Guessing is what produced `resource.resource-id = "is
        replaced"` alongside the identical action-id.

        "FBSU" is unclassified here too, for its own reason — active voice with
        no party evidence — so both appear in the same list.
        """

        _, resources, unclassified = classify_entities(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="FBSU",
                predicate="grants",
                object="employee benefits",
            ),
            "",
        )
        assert "employee benefits" in [u.phrase for u in unclassified]
        assert "employee benefits" not in [r.phrase for r in resources]

    def test_no_canonical_rule_yields_an_empty_view(self) -> None:
        view = build_xacml_view(None)
        assert view.xacml_projection.effect is None
        assert view.runtime_evaluation is None
