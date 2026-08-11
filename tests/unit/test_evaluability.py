"""Evaluability assessment — can an LLM decide this rule?

The fixtures are real canonical decompositions taken from the AD-103 Benefits
Policy extraction, not invented shapes. Every one of them is
`machine_executable=False`, which is why a second, honest answer is needed:
they are not equally undecidable, and the tests pin that difference.
"""

from __future__ import annotations

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.evaluability import (
    Evaluability,
    assess,
    referenced_attributes,
)


def _inflation_rule() -> CanonicalPolicyRule:
    """AI-7b1169642f, verbatim from the live extraction.

    "Increase due to inflation with a percentage not exceeding 5% of the
    employee's basic salary, and subject to the judgment and approval of the
    Board of Trustees."

    The document answers the question completely: up to 5%, Board of Trustees
    must approve. Nothing is missing except a mapping into a customer schema,
    which the evaluating LLM supplies from the case.
    """

    return CanonicalPolicyRule(
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
        source_origin="inherited_context",
    )


class TestDecidable:
    def test_inflation_increase_is_decidable(self) -> None:
        """The rule this whole distinction exists for.

        `machine_executable=False` on this rule says only that no FEEL tree
        could be built. The source states subject, modality, predicate,
        threshold and constraint — an LLM has everything the document offers.
        """

        result = assess(_inflation_rule())
        assert result.evaluability is Evaluability.DECIDABLE

    def test_reason_names_the_fields_that_carried_the_test(self) -> None:
        result = assess(_inflation_rule())
        assert "'object'" in result.reason
        assert "'threshold'" in result.reason
        assert "'constraint'" in result.reason

    def test_board_approval_survives_into_the_attribute_list(self) -> None:
        """The approval requirement is the answer, not decoration.

        "subject to the judgment and approval of the Board of Trustees" is
        carried in `constraint`. If the attribute list dropped it, an evaluator
        would answer "up to 5%" and omit that anyone has to approve.
        """

        phrases = [a.phrase for a in referenced_attributes(_inflation_rule())]
        assert any("Board of Trustees" in p for p in phrases)

    def test_threshold_is_quoted_never_converted(self) -> None:
        """`5%` stays `5%`. Normalising it to 0.05 would assert a unit the
        document did not state, which is the same fabrication pointer-only
        selection exists to prevent."""

        attrs = referenced_attributes(_inflation_rule())
        threshold = next(a for a in attrs if a.role == "threshold")
        assert threshold.phrase == "5% of the employee’s basic salary"

    def test_prohibition_with_threshold_is_decidable(self) -> None:
        """"Annual increase shall not exceed 10% of the employee's current
        basic salary" — the other rule the user pointed at."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PROHIBITION,
                subject="Annual increase",
                modality="shall not",
                predicate="exceed",
                object="10% of the employee’s current basic salary",
                threshold="10% of the employee’s current basic salary",
            )
        )
        assert result.evaluability is Evaluability.DECIDABLE

    def test_temporal_constraint_alone_is_decidable(self) -> None:
        """"Medical benefits begin on the employee's first working day."

        Found by running the assessment over the live 45 rules and reading the
        result: this was reported UNDERSPECIFIED because the testable-field
        list only looked for *how much*. Asked "when do my benefits start?",
        the sentence answers completely. A document can be specific about
        time, place or frequency without naming a value.
        """

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
                subject="Medical benefits",
                predicate="begin",
                temporal_constraint="on the employee’s first working day",
            )
        )
        assert result.evaluability is Evaluability.DECIDABLE

    def test_location_alone_is_decidable(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The receipt",
                modality="shall",
                predicate="be submitted",
                location="at the Human Resources Department",
            )
        )
        assert result.evaluability is Evaluability.DECIDABLE


class TestDiscretionary:
    """A delegated decision is a decision.

    "Exceptional Increase may be granted" states no threshold because the
    document *withheld* one — it delegated. Reporting that as incomplete asks
    a reviewer to invent a limit the policy deliberately left open.
    """

    def test_permissive_modality_alone_is_discretionary(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                modality="may",
                predicate="be granted",
            )
        )
        assert result.evaluability is Evaluability.DISCRETIONARY

    def test_unnamed_authority_is_said_out_loud(self) -> None:
        """"who decides?" is the actionable question for a reviewer, so the
        reason has to say the source never answered it."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                modality="may",
                predicate="be granted",
            )
        )
        assert "names no authority" in result.reason

    def test_named_authority_from_the_sentence(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PERMISSION,
                subject="Exceptional Increase",
                modality="may",
                predicate="be granted",
            ),
            "Exceptional Increase may be granted at the discretion of the President.",
        )
        assert result.evaluability is Evaluability.DISCRETIONARY
        assert "the President" in result.reason
        assert [p.name for p in result.parties] == ["the President"]

    def test_authority_without_a_permissive_modality_still_counts(self) -> None:
        """Delegation is the signal, not the modal word. A rule that names an
        approver and states no test is delegated however it is phrased."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
                subject="The recommendations of the director",
                modality="are",
                predicate="submitted",
            ),
            "The recommendations of the director on allowances and benefits are "
            "subject to the approval of the President.",
        )
        assert result.evaluability is Evaluability.DISCRETIONARY

    def test_may_not_is_a_prohibition_not_discretion(self) -> None:
        """Reading "may not" as latitude turns a ban into an option."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PROHIBITION,
                subject="An employee",
                modality="may not",
                predicate="claim",
            )
        )
        assert result.evaluability is Evaluability.UNDERSPECIFIED

    def test_stated_test_outranks_a_delegation(self) -> None:
        """The inflation rule carries both a 5% limit and Board approval.

        XACML models this as a Permit with an Obligation, so the approval
        rides along in `parties` and the verdict stays DECIDABLE. Downgrading
        it to discretionary would hide the 5% limit that is actually stated.
        """

        result = assess(
            _inflation_rule(),
            "Increase due to inflation with a percentage not exceeding 5% of the "
            "employee’s basic salary, and subject to the judgment and approval of "
            "the Board of Trustees.",
        )
        assert result.evaluability is Evaluability.DECIDABLE
        assert [p.name for p in result.parties] == ["the Board of Trustees"]


class TestUnderspecified:
    def test_no_test_and_no_discretion_signal(self) -> None:
        """Neither a value to test against nor any sign the decision was
        delegated. The document genuinely says nothing actionable."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The procedure",
                modality="shall",
                predicate="be followed",
            )
        )
        assert result.evaluability is Evaluability.UNDERSPECIFIED

    def test_underspecified_is_distinct_from_decidable(self) -> None:
        """The whole point: these are both `machine_executable=False` and must
        not be reported as the same situation."""

        vague = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The procedure",
                modality="shall",
                predicate="be followed",
            )
        )
        assert vague.evaluability is not assess(_inflation_rule()).evaluability


class TestMalformed:
    def test_predicate_repeating_modality(self) -> None:
        """"Directors of administrative units **may may** also be eligible" —
        modality "may", predicate "may also be eligible". The duplicate proves
        the sentence was mis-split, so the verb cannot be trusted."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.ELIGIBILITY,
                subject="Directors of administrative units",
                modality="may",
                predicate="may also be eligible",
                object="“A” Class",
            )
        )
        assert result.evaluability is Evaluability.MALFORMED
        assert "may" in result.reason

    def test_predicate_beginning_with_same_word_as_modality_only(self) -> None:
        """The check compares the modality's *last* token to the predicate's
        first, so a multi-word modality still catches its own repetition."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The employee",
                modality="shall not",
                predicate="not submit",
                object="the receipt",
            )
        )
        assert result.evaluability is Evaluability.MALFORMED

    def test_normal_negated_rule_is_not_flagged_as_malformed(self) -> None:
        """Guard against the check firing on every prohibition. "shall not" +
        "exceed" is correct decomposition, not a mis-split."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.PROHIBITION,
                subject="Annual increase",
                modality="shall not",
                predicate="exceed",
                threshold="10%",
            )
        )
        assert result.evaluability is Evaluability.DECIDABLE

    def test_missing_subject(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                predicate="be submitted",
                object="the receipt",
            )
        )
        assert result.evaluability is Evaluability.MALFORMED
        assert "subject" in result.reason

    def test_missing_predicate(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The employee",
                object="the receipt",
            )
        )
        assert result.evaluability is Evaluability.MALFORMED
        assert "predicate" in result.reason

    def test_no_decomposition_at_all(self) -> None:
        assert assess(None).evaluability is Evaluability.MALFORMED


class TestNotADecision:
    def test_definition_states_no_decision(self) -> None:
        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.DEFINITION,
                subject="Basic salary",
                predicate="means",
                object="the monthly salary before allowances",
            )
        )
        assert result.evaluability is Evaluability.NOT_A_DECISION

    def test_definition_still_reports_its_attributes(self) -> None:
        """A definition is not evaluated, but the terms it defines are exactly
        what an evaluator must recognise elsewhere, so the list is still
        populated."""

        result = assess(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.DEFINITION,
                subject="Basic salary",
                predicate="means",
                object="the monthly salary before allowances",
            )
        )
        assert [a.phrase for a in result.attributes_referenced] == [
            "Basic salary",
            "the monthly salary before allowances",
        ]


class TestReferencedAttributes:
    def test_duplicate_phrase_across_fields_is_listed_once(self) -> None:
        """`object` and `condition` both hold "Increase due to inflation".
        One thing to find in the case, so one entry — a duplicate would make
        the extraction pass look for it twice and report it twice."""

        attrs = referenced_attributes(_inflation_rule())
        phrases = [a.phrase for a in attrs]
        assert phrases.count("Increase due to inflation") == 1

    def test_first_field_in_declaration_order_wins_the_duplicate(self) -> None:
        attrs = referenced_attributes(_inflation_rule())
        entry = next(a for a in attrs if a.phrase == "Increase due to inflation")
        assert entry.role == "object"

    def test_order_is_stable_across_calls(self) -> None:
        """A set would make the shipped JSON differ run to run for identical
        input, which breaks the repeat-run stability the extraction is
        measured on."""

        first = [(a.role, a.phrase) for a in referenced_attributes(_inflation_rule())]
        second = [(a.role, a.phrase) for a in referenced_attributes(_inflation_rule())]
        assert first == second

    def test_outcome_fields_are_not_listed_as_inputs(self) -> None:
        """`consequence` is what follows from a decision, not something to look
        for in the case. Listing it would send the extraction pass hunting for
        the answer it is supposed to compute."""

        attrs = referenced_attributes(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The employee",
                predicate="submit",
                object="the receipt",
                consequence="the claim is rejected",
                remedy="resubmit within 30 days",
            )
        )
        assert [a.phrase for a in attrs] == ["The employee", "the receipt"]

    def test_modality_and_predicate_are_not_attributes(self) -> None:
        attrs = referenced_attributes(_inflation_rule())
        roles = {a.role for a in attrs}
        assert "modality" not in roles
        assert "predicate" not in roles

    def test_empty_when_nothing_decomposed(self) -> None:
        assert referenced_attributes(None) == []

    def test_whitespace_only_field_is_not_an_attribute(self) -> None:
        attrs = referenced_attributes(
            CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject="The employee",
                predicate="submit",
                object="   ",
            )
        )
        assert [a.phrase for a in attrs] == ["The employee"]
