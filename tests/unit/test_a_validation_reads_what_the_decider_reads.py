"""A validation is given the context the decider reads, not a narrower one.

THE FALSE POSITIVE THIS EXISTS TO PREVENT

On the AIS handbook the evaluation reported, at high severity and as
"confirmed by deterministic check":

    'Salaries are paid' (AI-79fdd7986c) is AI Ready, but the record does not
    say what it requires.

The record's own sentence is:

    "Salaries are paid at AIS on monthly base in Saudi Riyals; transfers are
    made directly to the employee's local bank account on the 30th of each
    month."

That names the payer, the period, the currency, the channel and the date. The
policy says exactly what it requires. What was empty was our decomposition —
`condition` was `{"all": []}`, the effect action was the fragment "are paid",
and `required_facts` was `[]`.

THE GENERAL FAULT, WHICH THIS IS THE SECOND INSTANCE OF

`_states_its_test` read the structured formulation and nothing else. On the AI
Ready route the decider is a judge reading the record's sentence, so the check
was asking whether a record "says" something while looking at strictly less
than the reader sees. Its own docstring records the same mistake once before —
"29 of 46 records were called incomplete by a check looking in one place" —
fixed then by widening from one field to six, which never left the
decomposition.

The sibling instance is `test_a_backpointer_with_its_antecedent_is_not_damage`:
there a pointer was called damage because the check read the record without the
passage the record was cut from, where the antecedent sat one sentence away.
Same shape, different check: **the validation was not given the context the
decider has.**

WHAT IS PINNED HERE

Both directions, because widening a check's context must not make it vacuous:

  * a record whose slots are empty but whose sentence carries operative content
    is not silent — the extraction under-decomposed it, which is a different
    problem and not the reader's;
  * a record whose sentence carries no operative content either is still
    reported, because a judge really is left with nothing.
"""

from __future__ import annotations

import pytest

from policy_platform.contracts.policy import (
    EffectType,
    _sentence_states_a_test,
    _states_its_test,
)


class _Core:
    """The structured slots, as `unanswered_for_judge` sees them."""

    def __init__(self, **fields: str) -> None:
        for name in (
            "condition", "prerequisite", "constraint",
            "trigger", "temporal_constraint", "deadline",
            "predicate", "object", "threshold",
            "subject", "modality",
        ):
            setattr(self, name, fields.get(name, ""))


SALARY_SENTENCE = (
    "Salaries are paid at AIS on monthly base in Saudi Riyals; transfers are "
    "made directly to the employee’s local bank account on the 30th of each month."
)


def test_an_empty_decomposition_with_a_substantive_sentence_is_not_silent() -> None:
    # The live case. Every slot empty, and the sentence states the rule in full.
    assert _states_its_test(_Core(), SALARY_SENTENCE) is True


def test_a_record_whose_sentence_says_nothing_is_still_reported() -> None:
    # The check must keep catching what it was built for. A heading carries no
    # quantity and links nothing to anything, so a judge reading only this has
    # nothing to decide on.
    assert _states_its_test(_Core(), "Salaries and deductions") is False
    assert _states_its_test(_Core(), "Salaries are paid") is False


def test_the_structured_slots_still_answer_first() -> None:
    # Widening the context must not stop the decomposition being read. A record
    # whose slots carry the test is decidable whatever its sentence looks like.
    assert _states_its_test(_Core(condition="if the employee is confirmed"), "") is True
    assert _states_its_test(_Core(threshold="5%", predicate="shall not exceed"), "") is True
    assert _states_its_test(_Core(deadline="within 30 days"), "") is True


def test_no_context_and_no_slots_is_still_silent() -> None:
    assert _states_its_test(_Core(), "") is False
    assert _states_its_test(None, "") is False


class TestACategoricalRuleStatesItsTestByHavingNone:
    """The third instance, and the one that survived the first two fixes.

    "Slippers are strictly not allowed" has no condition, no threshold and no
    object — the forbidden thing *is* the subject — so a shape test written as
    `predicate and (object or threshold)` read it as silent. It is not silent.
    Asked "may I wear slippers?" it answers, every time, without needing a case
    to test against.

    Thirteen prohibitions were reported this way in a single evaluation of the
    AIS handbook, at high severity: "Smoking is not allowed", "Nepotism of any
    degree is not tolerated", "Alcohol and drugs are strictly forbidden",
    "head coverings or head wraps not allowed".

    Same fault as the two above it and the same correction: the check was
    reading less than the decider does.
    """

    #: Verbatim from the AIS handbook, with the decomposition as extracted.
    #: Each names the regulated thing in the subject and the force in the modal
    #: slot, and none carries an object because there is nothing to act upon.
    _BANS_WITH_A_MODAL = [
        ("Slippers", "strictly not allowed", "are allowed"),
        ("Breakfast or lunch gatherings", "are not allowed", "are allowed"),
        ("'Noisy' accessories", "not allowed", "are allowed"),
        ("head coverings or head wraps", "not allowed", "are allowed"),
        ("Smoking", "is not allowed", "is allowed"),
        ("Alcohol and drugs", "strictly forbidden", "are forbidden"),
        ("Any other connections to the AIS internet/network", "strictly forbidden", "are forbidden"),
    ]

    @pytest.mark.parametrize("subject,modality,predicate", _BANS_WITH_A_MODAL)
    def test_a_ban_naming_its_subject_says_what_it_requires(
        self, subject: str, modality: str, predicate: str
    ) -> None:
        core = _Core(subject=subject, modality=modality, predicate=predicate)
        assert _states_its_test(core, f"{subject} {modality}.") is True

    def test_the_force_is_read_from_the_predicate_too(self) -> None:
        """"Nepotism of any degree is not tolerated" writes no modal word.

        The negation is in the predicate, where `states_a_negation` already
        looks — it reads the modal word, the predicate and the subject, because
        policy prose uses all three. Reading only the modal slot here left this
        record reported after the other twelve were cleared, which is the same
        one-slot narrowness in miniature.

        Rather than re-derive the negation with a second vocabulary, the
        projection's own conclusion is read: a DENY effect is only ever reached
        by determining that the source forbids something.
        """

        core = _Core(subject="Nepotism of any degree", predicate="is not tolerated")
        source = "Nepotism of any degree is not tolerated at Arab International Schools."

        assert _states_its_test(core, source) is False, (
            "without the effect there is nothing here to read force from — "
            "this is the honest answer for the slots alone"
        )
        assert _states_its_test(core, source, EffectType.DENY) is True

    def test_require_action_is_not_evidence_of_force(self) -> None:
        """The guard that stops this widening swallowing the check.

        DENY and ALLOW are conclusions. REQUIRE_ACTION is the fallback for
        obligation and conditional_outcome, so accepting it as force would
        clear every record that reaches this point and leave the check with
        nothing to say.
        """

        core = _Core(subject="The Foundation", predicate="operates")
        assert _states_its_test(core, "The Foundation operates.", EffectType.REQUIRE_ACTION) is False

    def test_a_subject_and_predicate_without_force_is_still_reported(self) -> None:
        """The anti-vacuity case, and the reason force is required at all.

        "X does Y" is a description. Without a deontic operator nothing has been
        put under an obligation, a permission or a ban, and a judge is left with
        a statement of fact rather than a rule.
        """

        assert _states_its_test(_Core(subject="The Foundation", predicate="operates"), "") is False

    def test_a_request_is_not_force(self) -> None:
        """"Please" asks. A record whose only modal is a courtesy states no rule.

        Such records are marked informational at extraction and
        `unanswered_for_judge` returns early for them, so this can only be
        reached by calling the function directly — but it must be sound on its
        own terms, or the next caller inherits a hole.
        """

        core = _Core(subject="you", modality="Please", predicate="check with")
        assert _states_its_test(core, "Please check with HR") is False


class TestWhatCountsAsOperativeContent:
    """The discriminator is a shape, not a vocabulary."""

    def test_a_quantity_counts(self) -> None:
        assert _sentence_states_a_test("Payment is made on the 30th.") is True

    def test_a_subordinating_link_counts(self) -> None:
        assert _sentence_states_a_test("Leave is granted if the manager approves.") is True
        assert _sentence_states_a_test("Notice is given upon termination.") is True

    def test_a_period_counts_even_without_a_digit(self) -> None:
        # The two records this widening was made for. Both state when a thing
        # happens; neither carries a digit.
        assert _sentence_states_a_test(
            "Therefore, all employees undergo an ongoing performance evaluation "
            "process, which is officially documented once a year."
        ) is True
        assert _sentence_states_a_test(
            "Manpower planning is finalized by the respective Colleges annually."
        ) is True

    def test_a_named_delegation_counts(self) -> None:
        # `assess()` treats a named authority as DISCRETIONARY rather than
        # UNDERSPECIFIED: saying who decides is not saying nothing.
        assert _sentence_states_a_test(
            "The request is approved by the Board of Trustees."
        ) is True

    def test_a_bare_assertion_does_not(self) -> None:
        assert _sentence_states_a_test("Salaries are paid.") is False

    def test_a_heading_does_not(self) -> None:
        assert _sentence_states_a_test("Working hours") is False
        assert _sentence_states_a_test("Salaries and deductions") is False
        # Longer headings still read as headings because they carry no signal.
        assert _sentence_states_a_test("Documents required to be on file") is False

    def test_absent_text_does_not(self) -> None:
        assert _sentence_states_a_test("") is False
        assert _sentence_states_a_test("   ") is False
