"""Second pass over the formed logic.

Written the way the first double-tap was: each check must be shown to *fail*
on the defect it exists for, not merely to pass on good input. A validator
that never fires is indistinguishable from one that is broken, and the first
version of `policy_faithfulness` shipped exactly that — a regex that could not
match, reporting success on every document.
"""

from __future__ import annotations

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.infrastructure.extraction.evaluability import (
    Evaluability,
    EvaluabilityAssessment,
    ReferencedAttribute,
    assess_policy,
)
from policy_platform.infrastructure.quality.logic_faithfulness import (
    LogicFindingSeverity,
    check_attributes_are_quoted,
    check_authority_is_a_delegation,
    check_discretion_names_who,
    check_parties_are_quoted,
    judge_logic,
)
from policy_platform.infrastructure.extraction.policy_parties import (
    PartyProvenance,
    PartyRole,
    PolicyParty,
)

_INFLATION_TEXT = (
    "Increase due to inflation with a percentage not exceeding 5% of the employee’s "
    "basic salary, and subject to the judgment and approval of the Board of Trustees."
)


def _inflation_policy() -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text=_INFLATION_TEXT,
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
            subject="Employee basic salary",
            modality="shall",
            predicate="be increased",
            object="Increase due to inflation",
            condition="Increase due to inflation",
            constraint=(
                "with a percentage not exceeding 5% of the employee’s basic salary, "
                "and subject to the judgment and approval of the Board of Trustees"
            ),
            threshold="5% of the employee’s basic salary",
        ),
    )


class TestTheChecksActuallyFire:
    """Each check, shown failing on the defect it exists for."""

    def test_invented_attribute_is_blocking(self) -> None:
        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DECIDABLE,
            reason="stated",
            attributes_referenced=[
                ReferencedAttribute(phrase="the employee’s length of service", role="condition")
            ],
        )
        findings = check_attributes_are_quoted(assessment, _INFLATION_TEXT)
        assert [f.code for f in findings] == ["attribute_not_in_source"]
        assert findings[0].severity is LogicFindingSeverity.BLOCKING

    def test_invented_approver_is_blocking(self) -> None:
        """The worst failure this pass can catch: telling a customer someone
        must sign off when the document never said so."""

        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DECIDABLE,
            reason="stated",
            parties=[
                PolicyParty(
                    name="the Chief Financial Officer",
                    role=PartyRole.AUTHORITY,
                    provenance=PartyProvenance.DELEGATION_PHRASE,
                    source_field="requires the approval of",
                )
            ],
        )
        findings = check_parties_are_quoted(assessment, _INFLATION_TEXT)
        assert [f.code for f in findings] == ["party_not_in_source"]
        assert findings[0].severity is LogicFindingSeverity.BLOCKING

    def test_authority_read_from_a_negated_phrase_is_blocking(self) -> None:
        """The exact defect found on live data: "hospitals that are **not**
        approved by the insurance company" once yielded the insurer as the
        rule's authority. The pattern was narrowed; this keeps a future
        widening from reintroducing it silently."""

        text = (
            "In the case of medical treatment in clinics and hospitals that are not "
            "approved by the insurance company, the original medical invoices must be "
            "submitted to the Human Resources Department."
        )
        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DECIDABLE,
            reason="stated",
            parties=[
                PolicyParty(
                    name="the insurance company",
                    role=PartyRole.AUTHORITY,
                    provenance=PartyProvenance.DELEGATION_PHRASE,
                    source_field="approved by",
                )
            ],
        )
        findings = check_authority_is_a_delegation(assessment, text)
        assert [f.code for f in findings] == ["authority_from_negated_phrase"]

    def test_discretion_without_an_authority_is_review_not_blocking(self) -> None:
        """"may be granted" is a faithful reading of a document that genuinely
        did not say who grants it. The gap belongs to the policy, so it is
        surfaced rather than treated as an extraction failure."""

        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DISCRETIONARY,
            reason="the modality 'may' grants latitude",
        )
        findings = check_discretion_names_who(assessment, "Exceptional Increase may be granted.")
        assert [f.code for f in findings] == ["discretion_without_authority"]
        assert findings[0].severity is LogicFindingSeverity.REVIEW

    def test_malformed_decomposition_is_blocking(self) -> None:
        policy = CanonicalPolicy(
            source_text="Directors of administrative units may also be eligible.",
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ELIGIBILITY,
                subject="Directors of administrative units",
                modality="may",
                predicate="may also be eligible",
                object="“A” Class",
            ),
        )
        verdict = judge_logic(policy)
        assert "decomposition_malformed" in {f.code for f in verdict.findings}
        assert not verdict.passed


class TestInheritedContext:
    """A rule formulated from a governing stem carries fields that are not in
    its own sentence. The canonical record declares this with `source_origin`,
    and the check has to read that signal rather than condemn the enumeration
    handling the platform deliberately performs.

    This case was found by running the pass on the real inflation rule: its
    subject "Employee basic salary" is not a contiguous quotation of its own
    sentence, which says "the employee's basic salary".
    """

    def test_inherited_rule_is_reviewable_not_blocking(self) -> None:
        policy = _inflation_policy()
        policy.rule.source_origin = "inherited_context"
        verdict = judge_logic(policy)
        assert verdict.passed
        assert {f.severity for f in verdict.findings} == {LogicFindingSeverity.REVIEW}

    def test_the_unverifiable_claim_is_still_reported(self) -> None:
        """Downgrading severity must not mean going quiet — a reviewer still
        has to confirm the parent clause actually says it."""

        policy = _inflation_policy()
        policy.rule.source_origin = "inherited_context"
        verdict = judge_logic(policy)
        assert "attribute_not_in_source" in {f.code for f in verdict.findings}
        assert any("governing clause" in f.detail for f in verdict.findings)

    def test_without_inherited_context_the_same_claim_blocks(self) -> None:
        """Guard the exemption: it must be the declared signal doing the work,
        not the check having gone soft."""

        policy = _inflation_policy()
        policy.rule.source_origin = None
        verdict = judge_logic(policy)
        assert not verdict.passed


class TestSoundLogicPasses:
    """Guard against the opposite failure: a check so strict it fires on
    everything trains reviewers to ignore it, which leaves the real defects
    *less* visible than before it existed."""

    def test_the_inflation_rule_passes(self) -> None:
        policy = _inflation_policy()
        policy.rule.source_origin = "inherited_context"
        assert judge_logic(policy).passed

    def test_board_of_trustees_is_accepted(self) -> None:
        assessment = assess_policy(_inflation_policy())
        assert [p.name for p in assessment.parties] == ["the Board of Trustees"]
        assert check_parties_are_quoted(assessment, _INFLATION_TEXT) == []

    def test_negation_elsewhere_does_not_condemn_a_real_delegation(self) -> None:
        """"not exceeding 5%" sits in the same sentence as the delegation. A
        negation check scanning the whole sentence would reject the Board of
        Trustees — a false positive on the single most important rule."""

        assessment = assess_policy(_inflation_policy())
        assert check_authority_is_a_delegation(assessment, _INFLATION_TEXT) == []

    def test_no_policy_is_not_a_failure(self) -> None:
        assert judge_logic(None).passed


class TestQuotationIsNotOverlap:
    def test_reordered_words_are_not_a_quotation(self) -> None:
        """Token overlap would accept a claim assembled from words that appear
        in the sentence in a different order — which is exactly how a
        paraphrase passes for a quotation."""

        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DECIDABLE,
            reason="stated",
            attributes_referenced=[
                ReferencedAttribute(phrase="basic salary of the employee", role="threshold")
            ],
        )
        assert check_attributes_are_quoted(assessment, _INFLATION_TEXT)

    def test_typographic_quotes_do_not_cause_a_false_finding(self) -> None:
        """The PDF text layer and anything retyped from it differ on curly
        quotes. Reporting that as an invented attribute would bury the real
        findings under noise."""

        assessment = EvaluabilityAssessment(
            evaluability=Evaluability.DECIDABLE,
            reason="stated",
            attributes_referenced=[
                ReferencedAttribute(phrase="5% of the employee's basic salary", role="threshold")
            ],
        )
        assert check_attributes_are_quoted(assessment, _INFLATION_TEXT) == []
