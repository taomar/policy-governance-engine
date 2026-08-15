"""A finding's wording must not assert more than the check behind it established.

The same defect as a run status reading `completed` when coverage was short, and
a comparability version that never moved when comparability did — one sentence
lower down. A reviewer cannot re-run the check; the sentence is the whole of
what they get, so a sentence that reaches past its evidence is not a stylistic
matter but a false report.

Each test here is paired with a positive control that fires the check first, so
that a message assertion can never pass because nothing was produced.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EffectType, RuleFormulation
from policy_platform.infrastructure.quality.policy_faithfulness import (
    find_duplicate_rules,
    validate_rule,
)
from tests.fixtures.factories import make_rule


def _rule(
    *,
    rule_id: str = "R1",
    source: str,
    action: str,
    subject: str = "Annual increase",
    predicate: str = "exceed",
    condition_text: str = "",
    effect: EffectType = EffectType.REQUIRE_ACTION,
):
    rule = make_rule(
        rule_id, AllCondition(all=[]), effect_type=effect, effect_action=action
    )
    rule.formulation = RuleFormulation(
        source_index=0,
        canonical=CanonicalPolicy(
            source_text=source,
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject=subject,
                predicate=predicate,
                condition=condition_text,
            ),
        ),
        dmn_decisions=[],
    )
    return rule


def _finding(rule, code: str):
    for finding in validate_rule(rule):
        if finding.code == code:
            return finding
    raise AssertionError(f"{code} did not fire; the message assertion would be vacuous")


class TestDuplicateRuleClaimsOnlyWhatItCompared:
    """`find_duplicate_rules` keys on subject, predicate and content signature.

    It never reads `source_text`. Two rules drawn from different sentences that
    decompose identically are reported, and the message told the reviewer they
    cite the same sentence — a fact about the document that the check never
    looked at.
    """

    def _pair(self):
        # Deliberately different sentences. Identical subject, predicate and
        # remaining content, which is the whole of what the key compares.
        first = _rule(
            rule_id="R1",
            source="Section 4.1. The allowance is limited to one employee per household.",
            action="be limited to one employee",
        )
        second = _rule(
            rule_id="R2",
            source="Appendix B. Only one employee in a household may claim the allowance.",
            action="be limited to one employee",
        )
        return [first, second]

    def test_the_check_reports_rules_drawn_from_different_sentences(self):
        """Positive control, and the premise of the test below.

        If this stops firing, the check has started comparing source text and
        the message could then honestly speak about the sentence.
        """
        findings = find_duplicate_rules(self._pair())

        assert [f.code for f in findings] == ["duplicate_rule"]

    def test_the_message_does_not_claim_the_two_cite_the_same_sentence(self):
        message = find_duplicate_rules(self._pair())[0].message

        assert "same sentence" not in message.lower(), (
            "the message asserts a shared citation the key never compared: " + message
        )

    def test_the_message_does_not_assert_a_cause_it_did_not_observe(self):
        """"usually because a clause boundary fell inside it" is a claim about
        how the pair arose. The check sees two decompositions and nothing about
        how either was cut."""
        message = find_duplicate_rules(self._pair())[0].message

        assert "clause boundary fell" not in message.lower(), (
            "the message states a cause the check cannot observe: " + message
        )

    def test_the_message_still_names_the_other_rule_and_asks_for_a_decision(self):
        """Correcting an overstatement must not cost the reviewer the finding.

        A message trimmed to nothing is a different way of telling them less
        than the system knows.
        """
        message = find_duplicate_rules(self._pair())[0].message

        assert "R1" in message
        assert "reviewer" in message.lower()


class TestSourceConditionFindingDoesNotSayTheRecordLostIt:
    """The check reads condition-bearing fields and the subject/predicate/object.

    It establishes that the condition reached no field of the decomposition. It
    does not establish that the condition is absent from the record — and the
    finding it returns quotes that very condition out of the record, so the
    claim is contradicted inside the object making it.
    """

    def _rule(self):
        return _rule(
            source=(
                "Subject to the approval of the Dean, a member of staff may attend "
                "one external conference each year."
            ),
            action="attend one external conference",
            subject="A member of staff",
            predicate="may attend",
        )

    def test_the_check_fires(self):
        assert _finding(self._rule(), "source_condition_not_captured") is not None

    def test_the_record_still_holds_the_sentence_the_message_calls_absent(self):
        """Positive control for the correction: the evidence is right there."""
        finding = _finding(self._rule(), "source_condition_not_captured")

        assert "subject to the approval" in finding.source_quote.lower(), (
            "the finding quotes the source out of the canonical record, which is "
            "why 'absent from the record' cannot be said"
        )

    def test_the_message_does_not_claim_the_record_lost_it(self):
        message = _finding(self._rule(), "source_condition_not_captured").message

        assert "absent from the record" not in message.lower(), message
        assert "nothing downstream can carry it" not in message.lower(), message

    def test_the_message_still_quotes_the_marker_the_check_matched(self):
        """The check matches the marker, not the clause it introduces.

        So the message may name 'Subject to' and no more — quoting the whole
        dependency would be the same defect in the other direction.
        """
        message = _finding(self._rule(), "source_condition_not_captured").message

        assert "'subject to'" in message.lower()

    def test_the_message_says_where_the_dependency_is_missing_from(self):
        message = _finding(self._rule(), "source_condition_not_captured").message

        assert "decomposition" in message.lower()


class TestQuantityFindingDoesNotCallEveryNumberALimit:
    """`_QUANTITY_RE` matches durations and counts as well as ceilings.

    "30 days" in a notice period is not a limit, and the check has no way to
    tell one from the other — it matches a number beside a unit word. Calling
    every match a limit tells a reviewer the document says something it may
    not.
    """

    def _rule(self):
        return _rule(
            source=(
                "A member of staff shall give notice of resignation 30 days before "
                "the intended date of departure."
            ),
            action="give notice of resignation",
        )

    def test_the_check_fires_on_a_duration(self):
        """Positive control: the match is a duration, not a ceiling."""
        finding = _finding(self._rule(), "quantity_dropped")

        assert "30 days" in finding.source_quote

    def test_the_message_does_not_call_the_quantity_a_limit(self):
        message = _finding(self._rule(), "quantity_dropped").message

        assert "limit" not in message.lower(), (
            "the check matched a number beside a unit word and cannot tell a "
            "ceiling from a duration: " + message
        )

    def test_the_message_still_names_the_quantity_and_says_it_is_not_carried(self):
        message = _finding(self._rule(), "quantity_dropped").message

        assert "30 days" in message
        assert "does not carry it" in message.lower()
