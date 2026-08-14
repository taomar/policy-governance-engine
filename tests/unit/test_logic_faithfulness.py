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
from policy_platform.contracts.policy import Effect, EffectType
from policy_platform.infrastructure.quality.logic_faithfulness import (
    LogicFindingSeverity,
    check_attributes_are_quoted,
    check_authority_is_a_delegation,
    check_discretion_names_who,
    check_parties_are_quoted,
    check_polarity_survives_projection,
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


def _supplied_attribute_policy() -> CanonicalPolicy:
    """A rule whose condition shares no wording at all with its own sentence.

    This is the shape a governing stem produces: the phrase is real, but it
    comes from a clause above rather than from the sentence beside it.
    """

    return CanonicalPolicy(
        source_text=_INFLATION_TEXT,
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
            subject="Employee basic salary",
            modality="shall",
            predicate="be increased",
            object="Increase due to inflation",
            condition="Once confirmed",
            constraint="subject to the judgment and approval of the Board of Trustees",
        ),
    )


def _finding_for_claim(policy: CanonicalPolicy, claim: str):
    """The quotation finding a fixture is built to produce, found by its claim.

    Indexing `findings[0]` would let a fixture that started producing a
    different finding, or an extra one, pass this file silently. Selecting by
    claim rather than by position also keeps the assertion pointed at the
    phrase under test when a neighbouring phrase changes classification.
    """

    findings = [
        f
        for f in judge_logic(policy).findings
        if f.code == "attribute_not_in_source" and f.claim == claim
    ]
    assert len(findings) == 1, (
        f"expected exactly one finding for {claim!r}, got "
        f"{[(f.code, f.claim) for f in judge_logic(policy).findings]}"
    )
    return findings[0]


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
    its own sentence, and the canonical record declares this with
    `source_origin`.

    That signal used to *be* the severity axis: declaring provenance downgraded
    a finding, and omitting it blocked. Measured against the live corpus, that
    ranked findings by whether a record admitted where it came from and not at
    all by what had gone wrong — so it blocked hardest on flattened table
    structure, which no reviewer can repair by editing, and merely noted
    genuinely fabricated phrases. Severity now follows the shape of the
    mismatch, and `source_origin` survives as a modifier on the explanation.

    The original case still stands as a fixture: the subject "Employee basic
    salary" is not a contiguous quotation of a sentence reading "the employee's
    basic salary".
    """

    def test_provenance_no_longer_moves_severity(self) -> None:
        """The axis is gone: the same claim against the same sentence is ranked
        the same whether or not the record declares where it came from.

        The fixture has to be one that actually produces a finding. Run against
        a record whose findings are suppressed this compares two empty lists and
        passes on any implementation whatsoever, which is why the count is
        asserted before the comparison.
        """

        declared = _supplied_attribute_policy()
        declared.rule.source_origin = "inherited_context"
        silent = _supplied_attribute_policy()
        silent.rule.source_origin = None

        declared_findings = judge_logic(declared).findings
        silent_findings = judge_logic(silent).findings
        assert declared_findings, "fixture produced nothing to rank"
        assert silent_findings, "fixture produced nothing to rank"

        assert [(f.code, f.severity) for f in declared_findings] == [
            (f.code, f.severity) for f in silent_findings
        ]

    def test_every_word_present_and_in_order_is_not_a_defect(self) -> None:
        """"Employee basic salary" holds every word of "the employee's basic
        salary" in the order the sentence gives them. That is decomposition
        working, not a faithfulness failure, and it must not be reported at
        all — under either provenance."""

        for origin in ("inherited_context", None):
            policy = _inflation_policy()
            policy.rule.source_origin = origin
            verdict = judge_logic(policy)
            assert verdict.passed
            assert [f.code for f in verdict.findings] == []

    def test_provenance_still_informs_a_phrase_from_outside_the_sentence(self) -> None:
        """Demoting it must not mean discarding it. Where a claim shares no
        wording with its sentence, whether the record declares an inherited
        origin is the most useful thing a reviewer can be told about it."""

        supplied = _supplied_attribute_policy()
        supplied.rule.source_origin = "inherited_context"
        detail = _finding_for_claim(supplied, "Once confirmed").detail
        assert "governing clause" in detail

        undeclared = _supplied_attribute_policy()
        undeclared.rule.source_origin = None
        assert (
            "governing clause"
            not in _finding_for_claim(undeclared, "Once confirmed").detail
        )

    def test_the_modifier_does_not_change_the_rank(self) -> None:
        """Guard the demotion itself: the two details above differ, and the two
        severities do not."""

        declared = _supplied_attribute_policy()
        declared.rule.source_origin = "inherited_context"
        undeclared = _supplied_attribute_policy()
        undeclared.rule.source_origin = None

        assert (
            _finding_for_claim(declared, "Once confirmed").severity
            == _finding_for_claim(undeclared, "Once confirmed").severity
        )


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


class TestPolarityCrossCheck:
    """The check that reads both sides.

    `decomposition_malformed` was expected to catch a dropped negation and
    structurally cannot: it reports `Evaluability.MALFORMED`, a statement about
    the shape of the canonical record alone. A record whose negation was lost in
    projection is perfectly well-formed — subject, modality and predicate all
    present and all quotable. On RUN-83257A81 five records carried an inverted
    or doubled effect and `decomposition_malformed` flagged none of them.

    These cases are the live records, with the effects they actually had.
    """

    @staticmethod
    def _policy(subject: str, modality: str, predicate: str, obj: str | None = None):
        return CanonicalPolicy(
            source_text="No one should use profanity or show disrespect.",
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.RECOMMENDATION,
                subject=subject,
                modality=modality,
                predicate=predicate,
                object=obj,
            ),
        )

    def test_a_negated_sentence_commanding_its_own_conduct_blocks(self) -> None:
        """AI-9b3671e47c as stored: require_action("use profanity")."""

        policy = self._policy("No one", "should", "use", "profanity")
        effect = Effect(type=EffectType.REQUIRE_ACTION, action="use profanity")

        findings = check_polarity_survives_projection(policy, effect)

        assert [f.code for f in findings] == ["polarity_lost_in_projection"]
        assert findings[0].severity is LogicFindingSeverity.BLOCKING

    def test_a_denial_of_a_negated_action_blocks(self) -> None:
        """AI-dd2f1b1d53 as stored: deny("refrain from ... conduct")."""

        policy = self._policy("all its employees", "expects", "refrain from", "misconduct")
        effect = Effect(type=EffectType.DENY, action="refrain from any unethical conduct")

        findings = check_polarity_survives_projection(policy, effect)

        assert [f.code for f in findings] == ["polarity_doubled_in_projection"]
        assert findings[0].severity is LogicFindingSeverity.BLOCKING

    def test_a_negated_sentence_denying_its_conduct_is_silent(self) -> None:
        """The corrected shape. The whole point is that this one passes."""

        policy = self._policy("No one", "should", "use", "profanity")
        effect = Effect(type=EffectType.DENY, action="use profanity")

        assert check_polarity_survives_projection(policy, effect) == []

    def test_a_requirement_to_refrain_is_silent(self) -> None:
        """require_action(refrain from X) carries the negation exactly once."""

        policy = self._policy("employees", "should", "refrain themselves from", "loose talks")
        effect = Effect(type=EffectType.REQUIRE_ACTION, action="refrain themselves from loose talks")

        assert check_polarity_survives_projection(policy, effect) == []

    def test_an_ordinary_positive_rule_is_silent(self) -> None:
        """The control. A check that fired on everything would pass the rest."""

        policy = self._policy("the employee", "shall", "submit", "the form")
        effect = Effect(type=EffectType.REQUIRE_ACTION, action="submit the form")

        assert check_polarity_survives_projection(policy, effect) == []

    def test_no_effect_asserts_nothing(self) -> None:
        """Callers without a projected effect must not be told it is wrong."""

        policy = self._policy("No one", "should", "use", "profanity")

        assert check_polarity_survives_projection(policy, None) == []
        assert judge_logic(policy, None).passed is True

    def test_judge_logic_surfaces_it_when_given_the_effect(self) -> None:
        """The wiring, not just the predicate."""

        policy = self._policy("No one", "should", "use", "profanity")
        effect = Effect(type=EffectType.REQUIRE_ACTION, action="use profanity")

        verdict = judge_logic(policy, effect)

        assert "polarity_lost_in_projection" in [f.code for f in verdict.blocking]
        assert verdict.passed is False
