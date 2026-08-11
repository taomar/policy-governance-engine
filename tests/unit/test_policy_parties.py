"""Party extraction — who a rule concerns.

Fixtures are verbatim sentences from the AD-103 Benefits Policy, because the
defect being fixed is that these exact sentences yielded no party at all.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.policy_parties import (
    PartyProvenance,
    PartyRole,
    authorities,
    extract_parties,
    is_judgement_bounded,
)


class TestDelegationPhrases:
    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            (
                "Increase due to inflation with a percentage not exceeding 5% of the "
                "employee’s basic salary, and subject to the judgment and approval of "
                "the Board of Trustees.",
                "the Board of Trustees",
            ),
            (
                "The exceptional increase requires the approval of the President.",
                "the President",
            ),
            (
                "Exceptional Increase may be granted at the discretion of the Vice President.",
                "the Vice President",
            ),
            (
                "Leave may be taken with the prior approval of the direct manager.",
                "the direct manager",
            ),
            (
                "The allowance is paid as determined by the Human Resources Department.",
                "the Human Resources Department",
            ),
        ],
    )
    def test_named_authority_is_captured(self, sentence: str, expected: str) -> None:
        parties = extract_parties(None, sentence)
        assert [p.name for p in parties] == [expected]
        assert parties[0].role is PartyRole.AUTHORITY

    def test_authority_is_quoted_verbatim(self) -> None:
        """"the Board of Trustees" is what the document says. Normalising it to
        a directory principal or an approval-queue id would assert a customer
        schema this platform cannot see."""

        parties = extract_parties(
            None,
            "subject to the judgment and approval of the Board of Trustees.",
        )
        assert parties[0].name == "the Board of Trustees"

    def test_trailing_clause_is_not_part_of_the_name(self) -> None:
        """A captured span that runs on stops being a quotable entity and
        starts being a paraphrase of the sentence."""

        parties = extract_parties(
            None,
            "This requires the approval of the President for exceptional cases only.",
        )
        assert parties[0].name == "the President"

    def test_two_authorities_in_one_sentence_are_both_reported(self) -> None:
        parties = extract_parties(
            None,
            "Granted with the approval of the Dean, and subject to the approval of "
            "the Board of Trustees.",
        )
        assert [p.name for p in parties] == ["the Dean", "the Board of Trustees"]

    def test_sentence_order_is_preserved(self) -> None:
        """The list ships inside the rule JSON. A set would make identical
        input produce a different document run to run."""

        sentence = (
            "Granted with the approval of the Dean, then subject to the approval of "
            "the Board of Trustees."
        )
        first = [p.name for p in extract_parties(None, sentence)]
        second = [p.name for p in extract_parties(None, sentence)]
        assert first == second == ["the Dean", "the Board of Trustees"]

    def test_no_delegation_yields_no_party(self) -> None:
        assert extract_parties(None, "Annual increase shall not exceed 10%.") == []

    def test_empty_capture_is_not_an_empty_authority(self) -> None:
        """An authority named "" would make the rule look delegated to nobody,
        which reads as a decision having been made when none was."""

        assert extract_parties(None, "This requires the approval of .") == []


class TestFalsePositivesFoundOnRealData:
    """Every case here was produced by an earlier version of this module
    against the live AD-103 extraction, then read rather than counted."""

    def test_qualifying_relative_clause_is_not_a_delegation(self) -> None:
        """The insurer approves *hospitals*; it does not approve this rule.

        A bare passive alternative ("approved by X") matched this relative
        clause and reported the insurance company as the authority deciding
        the rule. The rule's actual obligation is to submit invoices to HR,
        under nobody's approval — and the match also silently dropped the
        "not", inverting the sentence it came from.
        """

        parties = extract_parties(
            None,
            "In the case of medical treatment in clinics and hospitals that are not "
            "approved by the insurance company, the original medical invoices and "
            "reports must be submitted to the Human Resources Department and the "
            "coverage will be in accordance with the health insurance policy.",
        )
        assert authorities(parties) == []

    def test_negated_delegation_is_not_a_delegation(self) -> None:
        """"not subject to the approval of the Board" says the Board does not
        decide. Reporting it as the authority inverts the sentence — the same
        defect that once turned "shall not exceed 10%" into an obligation to
        exceed it."""

        parties = extract_parties(
            None, "Routine purchases are not subject to the approval of the Board."
        )
        assert parties == []

    def test_negation_elsewhere_does_not_suppress_a_real_delegation(self) -> None:
        """Guard against over-correcting: a "not" earlier in a long sentence
        must not suppress a delegation later in it, or the fix for the false
        positive becomes a false negative."""

        parties = extract_parties(
            None,
            "Increase due to inflation with a percentage not exceeding 5% of the "
            "employee’s basic salary, and subject to the judgment and approval of "
            "the Board of Trustees.",
        )
        assert [p.name for p in parties] == ["the Board of Trustees"]


class TestCanonicalFields:
    def test_beneficiary_is_a_recipient_subject(self) -> None:
        """XACML §B.2 recipient-subject is "the subject that receives the
        result". A beneficiary of an allowance receives the decision; calling
        them the access-subject would say the rule governs their conduct."""

        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ENTITLEMENT,
                subject="Annual travel tickets",
                predicate="are provided to",
                beneficiary="Expatriate employees and their eligible family members",
            )
        )
        assert parties[0].role is PartyRole.RECIPIENT_SUBJECT
        assert parties[0].provenance is PartyProvenance.CANONICAL_FIELD

    def test_assigner_is_an_authority(self) -> None:
        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                predicate="be granted",
                assigner="the President",
            )
        )
        assert authorities(parties)[0].name == "the President"

    def test_grammatical_subject_is_never_a_party(self) -> None:
        """"Annual increase", "Employee basic salary" and "The housing
        allowance" are all canonical subjects and none of them is anybody.
        Scraping `subject` would fill the party list with amounts."""

        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PROHIBITION,
                subject="Annual increase",
                modality="shall not",
                predicate="exceed",
                threshold="10% of basic salary",
            )
        )
        assert parties == []

    def test_canonical_field_outranks_delegation_phrase(self) -> None:
        """Both name the same authority. The canonical field is the
        formulator's own decomposition of the sentence, so it is reported and
        the phrase match is deduplicated away."""

        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                predicate="be granted",
                assigner="the President",
            ),
            "Exceptional Increase requires the approval of the President.",
        )
        assert len(parties) == 1
        assert parties[0].provenance is PartyProvenance.CANONICAL_FIELD

    def test_field_and_phrase_naming_different_parties_both_appear(self) -> None:
        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ENTITLEMENT,
                subject="Tuition discount",
                predicate="is granted to",
                beneficiary="Full time employees",
            ),
            "Tuition discount is granted with the approval of the Dean.",
        )
        assert {(p.name, p.role) for p in parties} == {
            ("Full time employees", PartyRole.RECIPIENT_SUBJECT),
            ("the Dean", PartyRole.AUTHORITY),
        }

    def test_no_decomposition_and_no_text(self) -> None:
        assert extract_parties(None, "") == []


class TestSubjectFirstDelegation:
    """"cases that the university deems necessary" — the party comes before
    the verb, which the marker-first pattern structurally cannot reach.
    Found by running extraction over the live 45 rules."""

    def test_deems_necessary_names_the_authority(self) -> None:
        parties = extract_parties(
            None,
            "Exceptional Increase may be granted for specific cases that the "
            "university deems necessary.",
        )
        assert [p.name for p in parties] == ["the university"]
        assert parties[0].role is PartyRole.AUTHORITY

    def test_considers_appropriate(self) -> None:
        parties = extract_parties(
            None, "An amount that the committee considers appropriate may be paid."
        )
        assert [p.name for p in parties] == ["the committee"]

    def test_ordinary_transitive_use_is_not_a_delegation(self) -> None:
        """"deems the policy effective" states a fact, not a delegation.
        Requiring a judgement complement keeps the pattern from matching every
        use of the verb."""

        assert extract_parties(None, "The registrar that deems the policy effective.") == []


class TestJudgementBoundedGrouping:
    def test_rule_with_a_stated_limit_and_an_approver_is_still_bounded(self) -> None:
        """The group is keyed on the authority, not the verdict.

        The inflation rule states a testable 5% limit *and* needs Board
        approval. Grouping only rules with nothing else stated would leave out
        the very rule that most needs a human in the loop.
        """

        parties = extract_parties(
            None,
            "Increase due to inflation with a percentage not exceeding 5% of the "
            "employee’s basic salary, and subject to the judgment and approval of "
            "the Board of Trustees.",
        )
        assert is_judgement_bounded(parties)

    def test_rule_with_only_a_recipient_is_not_bounded(self) -> None:
        parties = extract_parties(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ENTITLEMENT,
                subject="Tuition discount",
                predicate="is granted to",
                beneficiary="Full time employees",
            )
        )
        assert not is_judgement_bounded(parties)
