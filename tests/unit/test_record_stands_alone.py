"""A record decided by reading has to be readable on its own.

The two halves of that promise, and both are properties of the *slice* the
extractor took rather than of the document it was taken from:

* a record must carry the wording its own operative fields point at, and
* a record must be a whole decision, not one fragment of one.

The fixtures below state those two shapes and nothing else. They are not copies
of the records that prompted the checks: a fixture that reproduced a real
record would pass the moment the check learned that record's words, which is
the failure mode both checks are built to avoid.
"""
from __future__ import annotations

import re

import pytest

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    RuleFormulation,
)
from policy_platform.infrastructure.correlation.relationship_discovery import (
    RuleAnchor,
    discover_referent_relationships,
    discover_split_decision_relationships,
)
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
    promoted_qualifiers,
)
from policy_platform.infrastructure.extraction import self_containment
from policy_platform.infrastructure.extraction.evaluability import Evaluability, assess
from policy_platform.infrastructure.extraction.self_containment import (
    _THE_DOCUMENT_ITSELF,
    _carries_a_preceding_sentence,
    unresolved_referents,
)
from policy_platform.infrastructure.prompt_assets import PROMPTS_DIR
from policy_platform.infrastructure.quality import ai_quality
from tests.fixtures.factories import make_rule


def _core(**fields) -> CanonicalPolicyRule:
    fields.setdefault("rule_type", CanonicalRuleType.OBLIGATION)
    return CanonicalPolicyRule(**fields)


def _record(rule_id: str, sentence: str, core: CanonicalPolicyRule):
    rule = make_rule(
        rule_id,
        FactComparisonCondition(fact="f", operator=ConditionOperator.EXISTS, value=None),
    )
    return rule.model_copy(
        update={
            "formulation": RuleFormulation(
                canonical=CanonicalPolicy(source_text=sentence, rule=core),
                source_index=0,
            )
        }
    )


def _assert_self_containment_saw(records) -> None:
    """The scan's verdict on a population where the answer is known.

    Held in one place so the healthy run and the blinded run assert exactly the
    same thing, and the blinded run is a real demonstration rather than a
    second, weaker claim.
    """

    findings = ai_quality._self_containment_findings(records)
    named = {rule_id for f in findings for rule_id in f["affected_rule_ids"]}

    assert named == {"R-DANGLES"}, (
        f"expected the record that points outward to be flagged and the one that "
        f"resolves locally to be left alone; actual: flagged {sorted(named)} out of "
        f"{len(records)} records examined"
    )


def _assert_split_scan_saw(records) -> None:
    findings = ai_quality._split_decision_findings(records)
    named = {frozenset(f["affected_rule_ids"]) for f in findings}

    assert named == {frozenset({"R-A", "R-B"})}, (
        f"expected the two fragments of one obligation to be grouped and the two "
        f"genuine obligations to be left apart; actual: grouped "
        f"{[sorted(g) for g in named]} out of {len(records)} records examined"
    )


def _assert_the_split_saw(records) -> None:
    """The verdict on a population holding one of each condition.

    One record whose evidence is a single sentence, so its antecedent cannot be
    inside it; one whose evidence carries the sentence before the pointer. A
    check that reported them alike would put both under one category here, which
    is exactly what this check did before the two were told apart.
    """

    findings = ai_quality._self_containment_findings(records)
    by_category = {f["category"]: sorted(f["affected_rule_ids"]) for f in findings}

    assert by_category == {
        "record_does_not_stand_alone": ["R-LOST"],
        "record_reference_is_opaque": ["R-KEPT"],
    }, (
        f"expected the cut that lost its antecedent and the cut that kept it to be "
        f"reported as different findings; actual: {by_category} out of "
        f"{len(records)} records examined"
    )


# --------------------------------------------------------------------------
# A pointer that resolves inside the record, and one that does not.
#
# The pair is the whole point. Both records use a demonstrative; only one of
# them names what it points at. A check that fires on the word rather than on
# the reference would flag both and be worthless.
# --------------------------------------------------------------------------

_RESOLVES = _core(
    subject="the applicant",
    modality="must",
    predicate="submit",
    object="the renewal form",
    condition="within the notice period stated in the notice, and no later than "
    "the end of that period",
)
_RESOLVES_SENTENCE = (
    "The applicant must submit the renewal form within the notice period stated "
    "in the notice, and no later than the end of that period."
)

_DANGLES = _core(
    subject="the applicant",
    modality="must",
    predicate="submit",
    object="the renewal form",
    condition="before the end of that period",
)
_DANGLES_SENTENCE = "The applicant must submit the renewal form before the end of that period."

# --------------------------------------------------------------------------
# A pointer whose antecedent is inside the record under another form.
#
# "7:05 AM" is what "this time" points at, and the check tests resolution by
# recurrence of the head noun, so this record is reported however well it was
# cut. What separates it from the pair above is not the pointer but the cut:
# its evidence carries the sentence that answers it.
# --------------------------------------------------------------------------

_KEPT = _core(
    subject="the minutes",
    modality="must",
    predicate="be counted",
    object="as tardiness",
    condition="after this time",
)
_KEPT_SENTENCE = (
    "The cut off point for late attendance is 7:05 AM. After this time, the "
    "minutes will be counted as tardiness."
)

#: The resolving record with a neighbour in front of it, so that a record which
#: meets the condition for the quieter finding and has nothing wrong with it
#: still produces no finding at all.
_RESOLVES_TWO_SENTENCES = f"A renewal notice states a notice period. {_RESOLVES_SENTENCE}"


class TestAPointerIsOnlyADefectWhenItPointsOutward:
    def test_a_reference_answered_by_the_record_is_left_alone(self) -> None:
        assert unresolved_referents(
            {"condition": _RESOLVES.condition}, _RESOLVES_SENTENCE
        ) == []

    def test_a_reference_the_record_never_answers_is_reported(self) -> None:
        found = unresolved_referents({"condition": _DANGLES.condition}, _DANGLES_SENTENCE)

        assert [(item.field, item.phrase) for item in found] == [("condition", "that period")]

    def test_the_two_records_use_the_same_words(self) -> None:
        """The discriminating property is the antecedent, not the vocabulary.

        If this ever fails, the fixtures have drifted into testing two
        different phrasings and the pair no longer proves anything.
        """

        assert "that period" in _RESOLVES.condition
        assert "that period" in _DANGLES.condition

    def test_a_grammatical_use_that_points_nowhere_is_not_a_pointer(self) -> None:
        """`that` as a complementiser introduces a clause, not a reference."""

        assert (
            unresolved_referents(
                {"condition": "provided that the applicant has paid the fee"},
                "The applicant may renew provided that the applicant has paid the fee.",
            )
            == []
        )


class TestAPointerAtTheDocumentIsNotADanglingOne:
    """Records the extraction prompt requires, which this check must not report.

    The prompt excludes sentences *about* the document — its enactment,
    approval, effective date, supersession — while requiring that a sentence
    which merely names the document and states a real rule be extracted. A
    finding against one of those penalises the system for obeying its own
    specification, and a measure that does that will, over enough revisions,
    train the instruction out of the system: a later prompt change would be
    scored an improvement for suppressing output the prompt asks for.

    So the two have to agree, and the last test here is what keeps them
    agreeing rather than leaving it to whoever next edits either file.
    """

    def test_a_sentence_naming_the_document_while_stating_a_rule_is_left_alone(self) -> None:
        """The prompt's own worked example of what to extract."""

        sentence = "This policy applies to all full-time employees in the United States."

        assert unresolved_referents({"subject": "This policy"}, sentence) == []

    def test_the_noun_is_what_carries_it(self) -> None:
        """The same shape with a noun naming content is still reported.

        The pair is the whole point. If this test ever passes, the exclusion
        has widened from "the document carrying this record" to "anything a
        record calls `this`", and the check has stopped doing its job.
        """

        found = unresolved_referents(
            {"subject": "This stipulation"},
            "This stipulation applies to all full-time employees.",
        )

        assert [item.phrase for item in found] == ["This stipulation"]

    def test_a_plural_is_a_set_of_rules_rather_than_the_document(self) -> None:
        found = unresolved_referents(
            {"subject": "These policies"},
            "These policies apply to all full-time employees.",
        )

        assert [item.phrase for item in found] == ["These policies"]

    def test_the_noun_set_still_covers_every_form_the_prompt_names(self) -> None:
        """The prompt is the specification, so it decides this vocabulary.

        Harvested from the sentence stating what "merely names the document"
        means rather than from the whole file, because a quoted "this X"
        elsewhere in the prompt may be an example of something else entirely,
        and treating one as a document noun would widen the exclusion until it
        swallowed real defects.
        """

        prompt = (PROMPTS_DIR / "passage_extractor_v1.md").read_text(encoding="utf-8")
        lines = prompt.splitlines()

        anchors = [i for i, line in enumerate(lines) if "merely names the document" in line]
        assert anchors, (
            "the extraction prompt no longer states what 'merely names the document' "
            "means, so this test harvested nothing and the assertion below would pass "
            "having compared no forms at all"
        )

        window = " ".join(lines[anchors[0] : anchors[0] + 3])
        named = {m.group(1).casefold() for m in re.finditer(r'"this ([A-Za-z]+)"', window, re.I)}

        assert len(named) >= 3, (
            f"expected that sentence to name several document types; harvested "
            f"{sorted(named)} from {window!r}. A reformatting that breaks the quoting "
            f"would otherwise leave this test asserting nothing."
        )

        missing = named - _THE_DOCUMENT_ITSELF
        assert not missing, (
            f"the extraction prompt now names {sorted(missing)} among the forms that "
            f"merely name the document and must be extracted, but the self-containment "
            f"check still reads those as pointers at content and will report every such "
            f"record as a defect. Add them to _THE_DOCUMENT_ITSELF."
        )


class TestACutThatKeptItsContextIsADifferentFinding:
    """Two conditions with two remedies, told apart by one question.

    The check resolves a pointer by literal recurrence of its head noun, so a
    record can carry its own antecedent and still be reported: "7:05 AM" answers
    "this time" and is not the token "time". That record's cut is not at fault.
    A record whose evidence is a single sentence is a different matter — nothing
    precedes the pointer, so the antecedent cannot be inside it at all.

    Reported as one finding, repairing a cut moves a record from the first
    condition to the second and the count does not change, which makes the
    measure unable to register the improvement it exists to drive.
    """

    def test_a_single_sentence_cut_is_reported_as_an_extraction_defect(self) -> None:
        findings = ai_quality._self_containment_findings(
            [_record("R-LOST", _DANGLES_SENTENCE, _DANGLES)]
        )

        assert [f["category"] for f in findings] == ["record_does_not_stand_alone"]
        assert findings[0]["severity"] == "high"

    def test_a_cut_that_kept_the_preceding_sentence_is_not(self) -> None:
        findings = ai_quality._self_containment_findings(
            [_record("R-KEPT", _KEPT_SENTENCE, _KEPT)]
        )

        assert [f["category"] for f in findings] == ["record_reference_is_opaque"]
        assert findings[0]["severity"] == "medium"
        assert "this time" in findings[0]["finding"]

    def test_the_two_conditions_are_reported_apart(self) -> None:
        _assert_the_split_saw(
            [
                _record("R-LOST", _DANGLES_SENTENCE, _DANGLES),
                _record("R-KEPT", _KEPT_SENTENCE, _KEPT),
            ]
        )

    def test_a_blind_discriminator_is_caught_by_that_assertion(self, monkeypatch) -> None:
        """Proof the assertion above can fail, and the before-state exactly.

        Blinding the discriminator to always answer "nothing precedes it" is
        precisely what this check did before the two conditions were separated:
        every pointer reported as a lost antecedent, at one severity, under one
        category. So this is both the blindness control and the demonstration
        that the previous behaviour does not satisfy the assertion.
        """

        monkeypatch.setattr(
            self_containment, "_carries_a_preceding_sentence", lambda _: False
        )

        with pytest.raises(AssertionError, match=r"record_does_not_stand_alone"):
            _assert_the_split_saw(
                [
                    _record("R-LOST", _DANGLES_SENTENCE, _DANGLES),
                    _record("R-KEPT", _KEPT_SENTENCE, _KEPT),
                ]
            )

    def test_a_record_that_resolves_is_still_reported_under_neither(self) -> None:
        """The split must not have invented a finding on healthy records.

        The resolving fixture carries a second sentence, so it meets the
        condition that routes to the quieter finding. It must still produce
        nothing at all: the discriminator chooses between findings, it does not
        create them.
        """

        assert _carries_a_preceding_sentence(_RESOLVES_TWO_SENTENCES)
        assert (
            ai_quality._self_containment_findings(
                [_record("R-RESOLVES", _RESOLVES_TWO_SENTENCES, _RESOLVES)]
            )
            == []
        )

    def test_a_pointer_at_the_document_is_still_excluded_either_way(self) -> None:
        """The earlier exclusion must not depend on the sentence count."""

        for source in (_KEPT_SENTENCE, _DANGLES_SENTENCE):
            assert not unresolved_referents(
                {"subject": "this policy"}, "this policy applies", source
            )

    def test_an_abbreviation_does_not_pass_for_a_second_sentence(self) -> None:
        """The discriminator decides which finding is raised, so it must not guess.

        A full stop inside "No. 5" or "e.g." would otherwise route a genuine
        single-sentence cut to the quieter finding, which is the one direction
        of error that hides a defect.
        """

        assert not _carries_a_preceding_sentence("Form No. 5 must be filed on entry.")
        assert not _carries_a_preceding_sentence("Carry a pass, e.g. the visitor card.")
        assert not _carries_a_preceding_sentence(_DANGLES_SENTENCE)
        assert _carries_a_preceding_sentence(_KEPT_SENTENCE)


class TestEvaluabilityWillNotClaimARecordStandsAlone:
    def test_a_record_whose_reference_resolves_is_still_decidable(self) -> None:
        assert assess(_RESOLVES, _RESOLVES_SENTENCE).evaluability is Evaluability.DECIDABLE

    def test_a_record_that_points_outward_is_not_decidable(self) -> None:
        verdict = assess(_DANGLES, _DANGLES_SENTENCE)

        assert verdict.evaluability is not Evaluability.DECIDABLE
        assert "that period" in verdict.reason


class TestTheFindingNamesTheRecordAndTheWording:
    def test_a_dangling_reference_is_reported_against_the_extraction(self) -> None:
        findings = ai_quality._self_containment_findings(
            [_record("R-DANGLES", _DANGLES_SENTENCE, _DANGLES)]
        )

        assert [f["category"] for f in findings] == ["record_does_not_stand_alone"]
        assert findings[0]["affected_rule_ids"] == ["R-DANGLES"]
        assert "that period" in findings[0]["finding"]

    def test_a_record_that_stands_alone_produces_nothing(self) -> None:
        assert (
            ai_quality._self_containment_findings(
                [_record("R-RESOLVES", _RESOLVES_SENTENCE, _RESOLVES)]
            )
            == []
        )

    def test_the_check_examined_both_records(self) -> None:
        """A scan that reads nothing finds nothing and passes on silence.

        `assert not findings` cannot tell "examined two, flagged none" from
        "examined none". So the guard asserts the verdict on a known population
        instead: one record that must be flagged and one that must not.
        """

        _assert_self_containment_saw(
            [
                _record("R-RESOLVES", _RESOLVES_SENTENCE, _RESOLVES),
                _record("R-DANGLES", _DANGLES_SENTENCE, _DANGLES),
            ]
        )

    def test_a_blind_scan_is_caught_by_that_assertion(self, monkeypatch) -> None:
        """Proof the assertion above can fail, by blinding the scan for real.

        Both checks read the canonical decomposition and skip any record
        without one, so a record arriving with no decomposition is examined by
        nothing. That is how this would go blind in production, and it is
        silent: the scan still returns an empty list and still looks healthy.
        """

        monkeypatch.setattr(ai_quality, "_canonical_core", lambda rule: None)

        with pytest.raises(AssertionError, match=r"actual: flagged \[\]"):
            _assert_self_containment_saw(
                [
                    _record("R-RESOLVES", _RESOLVES_SENTENCE, _RESOLVES),
                    _record("R-DANGLES", _DANGLES_SENTENCE, _DANGLES),
                ]
            )

    def test_with_the_floor_in_place_a_new_offender_is_still_named(self) -> None:
        """The volume floor must not become the thing that fails.

        Adding a second record that points outward has to be reported by
        rule id, not swallowed into a count that happens to still be above a
        threshold.
        """

        second = _core(
            subject="the reviewer",
            modality="must",
            predicate="record",
            object="the outcome",
            condition="in each of those cases",
        )
        findings = ai_quality._self_containment_findings(
            [
                _record("R-RESOLVES", _RESOLVES_SENTENCE, _RESOLVES),
                _record("R-DANGLES", _DANGLES_SENTENCE, _DANGLES),
                _record("R-INJECTED", "The reviewer must record the outcome in each of those cases.", second),
            ]
        )

        named = {rule_id for f in findings for rule_id in f["affected_rule_ids"]}
        assert named == {"R-DANGLES", "R-INJECTED"}
        assert any("those cases" in f["finding"] for f in findings)


# --------------------------------------------------------------------------
# One obligation cut into fragments, and two obligations correctly kept apart.
# --------------------------------------------------------------------------

_ONE_SENTENCE = (
    "The applicant must submit the renewal form on joining and again on renewal."
)
_FRAGMENT_A = _core(
    subject="the applicant",
    modality="must",
    predicate="submit",
    object="the renewal form",
    temporal_constraint="on joining",
)
_FRAGMENT_B = _core(
    subject="the applicant",
    modality="must",
    predicate="submit",
    object="the renewal form",
    temporal_constraint="on renewal",
)

_TWO_OBLIGATIONS_SENTENCE = (
    "The applicant must submit the renewal form and the reviewer must approve it."
)
_OBLIGATION_ONE = _core(
    subject="the applicant", modality="must", predicate="submit", object="the renewal form"
)
_OBLIGATION_TWO = _core(
    subject="the reviewer", modality="must", predicate="approve", object="the renewal form"
)

# A ladder: one obligation whose outcome is selected by the occasion. Each
# fragment states which case it covers, so a reader can tell them apart and
# decide each on its own. The source states it this way; the extraction did not
# invent the shape.
_LADDER_SENTENCE = (
    "A breach draws a warning on the first occasion and suspension on the second."
)
_LADDER_RUNG_ONE = _core(
    subject="a breach",
    predicate="draws",
    object="a warning",
    condition="the first occasion",
)
_LADDER_RUNG_TWO = _core(
    subject="a breach",
    predicate="draws",
    object="suspension",
    condition="the second occasion",
)

# The same shape with the selector missing. Nothing says which outcome applies,
# so the records are indistinguishable as stored.
_UNSELECTED_SENTENCE = "A breach draws a warning and suspension."
_UNSELECTED_ONE = _core(subject="a breach", predicate="draws", object="a warning")
_UNSELECTED_TWO = _core(subject="a breach", predicate="draws", object="suspension")


def _members(*pairs) -> list[FamilyMember]:
    return [
        FamilyMember(rule_id=rule_id, sentence=sentence, core=core)
        for rule_id, sentence, core in pairs
    ]


class TestOneDecisionPerRecord:
    def test_fragments_of_one_obligation_form_a_family(self) -> None:
        families = decision_families(
            _members(
                ("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                ("R-B", _ONE_SENTENCE, _FRAGMENT_B),
            )
        )

        assert len(families) == 1
        assert set(families[0].rule_ids) == {"R-A", "R-B"}
        assert families[0].varying == ("temporal_constraint",)

    def test_two_obligations_in_one_sentence_are_not_a_family(self) -> None:
        assert (
            decision_families(
                _members(
                    ("R-A", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                    ("R-B", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
                )
            )
            == []
        )

    def test_the_same_obligation_in_two_sentences_is_not_a_family(self) -> None:
        """Two sentences saying the same thing is the document repeating itself."""

        assert (
            decision_families(
                _members(
                    ("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                    ("R-B", "A different sentence entirely.", _FRAGMENT_A),
                )
            )
            == []
        )

    def test_identical_fragments_are_left_to_the_duplicate_check(self) -> None:
        assert (
            decision_families(
                _members(
                    ("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                    ("R-B", _ONE_SENTENCE, _FRAGMENT_A),
                )
            )
            == []
        )


class TestAnOutcomeSelectedByItsOccasionIsOneDecision:
    """A ladder is the source's own shape, not a split of it.

    Where the fragments differ in the outcome *and* in the circumstance that
    selects it, each one says which case it covers. A reader can tell them
    apart and decide each alone, so nothing was cut apart and there is nothing
    to report. Reporting it would send a reviewer to undo the document.
    """

    def test_a_ladder_is_not_reported(self) -> None:
        assert (
            decision_families(
                _members(
                    ("R-ONE", _LADDER_SENTENCE, _LADDER_RUNG_ONE),
                    ("R-TWO", _LADDER_SENTENCE, _LADDER_RUNG_TWO),
                )
            )
            == []
        )

    def test_the_same_outcomes_without_a_selector_are_still_reported(self) -> None:
        """Remove what distinguishes the rungs and the defect is back."""

        families = decision_families(
            _members(
                ("R-ONE", _UNSELECTED_SENTENCE, _UNSELECTED_ONE),
                ("R-TWO", _UNSELECTED_SENTENCE, _UNSELECTED_TWO),
            )
        )

        assert len(families) == 1
        assert families[0].varying == ("object",)

    def test_one_outcome_over_several_occasions_is_still_reported(self) -> None:
        """A selector alone does not excuse a split.

        Same outcome, different occasions, is one obligation whose condition
        should have carried both — the case this module was built for. Only a
        selector that picks *between different outcomes* makes a ladder.
        """

        families = decision_families(
            _members(
                ("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                ("R-B", _ONE_SENTENCE, _FRAGMENT_B),
            )
        )

        assert len(families) == 1
        assert families[0].varying == ("temporal_constraint",)


class TestTheSplitFindingSaysWhatWasCutApart:
    def test_a_family_is_reported_with_every_member(self) -> None:
        findings = ai_quality._split_decision_findings(
            [
                _record("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                _record("R-B", _ONE_SENTENCE, _FRAGMENT_B),
            ]
        )

        assert [f["category"] for f in findings] == ["decision_split_across_records"]
        assert sorted(findings[0]["affected_rule_ids"]) == ["R-A", "R-B"]
        assert "temporal_constraint" in findings[0]["finding"]

    def test_a_correct_split_is_not_reported(self) -> None:
        assert (
            ai_quality._split_decision_findings(
                [
                    _record("R-A", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                    _record("R-B", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
                ]
            )
            == []
        )

    def test_the_check_examined_both_populations(self) -> None:
        """One family found among records that also contain a correct split."""

        _assert_split_scan_saw(
            [
                _record("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                _record("R-B", _ONE_SENTENCE, _FRAGMENT_B),
                _record("R-C", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                _record("R-D", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
            ]
        )

    def test_a_blind_scan_is_caught_by_that_assertion(self, monkeypatch) -> None:
        monkeypatch.setattr(ai_quality, "_canonical_core", lambda rule: None)

        with pytest.raises(AssertionError, match=r"actual: grouped \[\]"):
            _assert_split_scan_saw(
                [
                    _record("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                    _record("R-B", _ONE_SENTENCE, _FRAGMENT_B),
                    _record("R-C", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                    _record("R-D", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
                ]
            )

    def test_with_the_floor_in_place_a_new_family_is_still_named(self) -> None:
        other_sentence = "The reviewer may waive the fee for a first application or a transfer."
        waive_a = _core(
            rule_type=CanonicalRuleType.PERMISSION,
            subject="the reviewer",
            modality="may",
            predicate="waive",
            object="the fee",
            condition="for a first application",
        )
        waive_b = waive_a.model_copy(update={"condition": "for a transfer"})

        findings = ai_quality._split_decision_findings(
            [
                _record("R-A", _ONE_SENTENCE, _FRAGMENT_A),
                _record("R-B", _ONE_SENTENCE, _FRAGMENT_B),
                _record("R-C", other_sentence, waive_a),
                _record("R-D", other_sentence, waive_b),
            ]
        )

        named = {frozenset(f["affected_rule_ids"]) for f in findings}
        assert named == {frozenset({"R-A", "R-B"}), frozenset({"R-C", "R-D"})}


# --------------------------------------------------------------------------
# A qualifier promoted to a rule of its own.
#
# The pair is again the point. Both populations put the same noun phrase in two
# records; only one of them makes that phrase the *subject* of a second rule. A
# check keyed on a shared noun would flag both and be worthless.
# --------------------------------------------------------------------------

_QUALIFIED_SENTENCE = (
    "The applicant submits a renewal form, which is retained for five years."
)
_THE_OBLIGATION = _core(
    subject="the applicant",
    predicate="submits",
    object="a renewal form",
)
# The relative clause, cut out and made a rule. Its subject is the thing the
# obligation above lands on, so nothing a case can be about is named here.
_THE_QUALIFIER = _core(
    subject="a renewal form",
    predicate="is retained",
    temporal_constraint="for five years",
)

# The control shares an *object* across both records and is a correct split.
# Nothing is promoted, because neither subject is the other's object. It is
# `_TWO_OBLIGATIONS_SENTENCE`, reused deliberately: the same pair that proves
# the family check keys on the right thing proves this one does too.


def _assert_promotion_scan_saw(records) -> None:
    findings = ai_quality._promoted_qualifier_findings(records)
    named = {frozenset(f["affected_rule_ids"]) for f in findings}

    assert named == {frozenset({"R-A", "R-B"})}, (
        f"expected the record made about the thing the obligation lands on to be "
        f"paired with it, and the correct split sharing an object to be left alone; "
        f"actual: paired {[sorted(g) for g in named]} out of {len(records)} records "
        f"examined"
    )


class TestAQualifierIsNotADecision:
    def test_a_subject_that_is_another_records_object_is_reported(self) -> None:
        promotions = promoted_qualifiers(
            _members(
                ("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                ("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
            )
        )

        assert len(promotions) == 1
        assert promotions[0].antecedent_rule_ids == ("R-A",)
        assert promotions[0].qualifier_rule_id == "R-B"
        assert promotions[0].phrase == "a renewal form"

    def test_several_records_acting_on_the_thing_raise_one_report(self) -> None:
        """A reviewer reads the defect once, with everything it touches named."""

        approve = _core(subject="the reviewer", predicate="approves", object="a renewal form")
        promotions = promoted_qualifiers(
            _members(
                ("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                ("R-C", _QUALIFIED_SENTENCE, approve),
                ("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
            )
        )

        assert len(promotions) == 1
        assert promotions[0].qualifier_rule_id == "R-B"
        assert sorted(promotions[0].antecedent_rule_ids) == ["R-A", "R-C"]

    def test_records_merely_sharing_an_object_are_left_alone(self) -> None:
        assert (
            promoted_qualifiers(
                _members(
                    ("R-A", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                    ("R-B", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
                )
            )
            == []
        )

    def test_the_same_phrase_across_two_sentences_is_not_a_promotion(self) -> None:
        """A document reusing a noun is not a decision cut in two."""

        assert (
            promoted_qualifiers(
                _members(
                    ("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                    ("R-B", "Some other sentence entirely.", _THE_QUALIFIER),
                )
            )
            == []
        )

    def test_a_reflexive_record_is_not_reported_against_itself(self) -> None:
        reflexive = _core(subject="the register", predicate="lists", object="the register")

        assert (
            promoted_qualifiers(
                _members(
                    ("R-A", _QUALIFIED_SENTENCE, reflexive),
                    ("R-B", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                )
            )
            == []
        )

    def test_two_reflexive_records_are_not_reported_against_each_other(self) -> None:
        """Real shape: 'Overtime should be approved and controlled' cut in two,
        each record repeating the noun in both slots. Malformed on its own
        account, and neither is a qualifier of the other."""

        approved = _core(subject="overtime", predicate="be approved", object="overtime")
        controlled = _core(subject="overtime", predicate="be controlled", object="overtime")

        assert (
            promoted_qualifiers(
                _members(
                    ("R-A", "Overtime should be approved and controlled.", approved),
                    ("R-B", "Overtime should be approved and controlled.", controlled),
                )
            )
            == []
        )


class TestThePromotionFindingSaysWhichRecordWasPromoted:
    def test_the_finding_names_both_records_and_the_phrase(self) -> None:
        findings = ai_quality._promoted_qualifier_findings(
            [
                _record("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                _record("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
            ]
        )

        assert [f["category"] for f in findings] == ["qualifier_promoted_to_record"]
        assert sorted(findings[0]["affected_rule_ids"]) == ["R-A", "R-B"]
        assert "a renewal form" in findings[0]["finding"]

    def test_it_is_reported_apart_from_the_split_family_shape(self) -> None:
        """The two shapes have different remedies, so they are different findings."""

        records = [
            _record("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
            _record("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
        ]

        assert ai_quality._split_decision_findings(records) == []
        assert len(ai_quality._promoted_qualifier_findings(records)) == 1

    def test_the_check_examined_both_populations(self) -> None:
        _assert_promotion_scan_saw(
            [
                _record("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                _record("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
                _record("R-C", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                _record("R-D", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
            ]
        )

    def test_a_blind_scan_is_caught_by_that_assertion(self, monkeypatch) -> None:
        monkeypatch.setattr(ai_quality, "_canonical_core", lambda rule: None)

        with pytest.raises(AssertionError, match=r"actual: paired \[\]"):
            _assert_promotion_scan_saw(
                [
                    _record("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                    _record("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
                    _record("R-C", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_ONE),
                    _record("R-D", _TWO_OBLIGATIONS_SENTENCE, _OBLIGATION_TWO),
                ]
            )

    def test_with_the_floor_in_place_a_new_promotion_is_still_named(self) -> None:
        other_sentence = "The school issues a certificate, which is signed by the head."
        issues = _core(subject="the school", predicate="issues", object="a certificate")
        signed = _core(subject="a certificate", predicate="is signed by the head")

        findings = ai_quality._promoted_qualifier_findings(
            [
                _record("R-A", _QUALIFIED_SENTENCE, _THE_OBLIGATION),
                _record("R-B", _QUALIFIED_SENTENCE, _THE_QUALIFIER),
                _record("R-C", other_sentence, issues),
                _record("R-D", other_sentence, signed),
            ]
        )

        named = {frozenset(f["affected_rule_ids"]) for f in findings}
        assert named == {frozenset({"R-A", "R-B"}), frozenset({"R-C", "R-D"})}


# --------------------------------------------------------------------------
# The links. A record is never rewritten to carry a neighbour's words; it is
# connected to the neighbour instead.
# --------------------------------------------------------------------------


def _anchor(rule_id: str, order: int, *, sentence: str = "", core=None, unresolved=None):
    return RuleAnchor(
        rule_id=rule_id,
        text=sentence,
        order=order,
        canonical_fields=(
            {
                name: value
                for name in type(core).model_fields
                if isinstance(value := getattr(core, name, None), str)
                or hasattr(value, "value")
            }
            if core is not None
            else {}
        ),
        unresolved_phrases=list(unresolved or []),
    )


class TestFragmentsAreLinkedRatherThanMerged:
    def test_a_family_is_linked_to_its_first_fragment(self) -> None:
        edges = discover_split_decision_relationships(
            [
                _anchor("R-A", 0, sentence=_ONE_SENTENCE, core=_FRAGMENT_A),
                _anchor("R-B", 1, sentence=_ONE_SENTENCE, core=_FRAGMENT_B),
            ]
        )

        assert len(edges) == 1
        assert (edges[0].source_rule_id, edges[0].target_rule_id) == ("R-B", "R-A")
        assert edges[0].relationship_type.value == "same_decision"
        assert edges[0].state == "confirmed"
        assert "temporal_constraint" in edges[0].evidence.detail

    def test_a_correct_split_is_not_linked(self) -> None:
        assert (
            discover_split_decision_relationships(
                [
                    _anchor("R-A", 0, sentence=_TWO_OBLIGATIONS_SENTENCE, core=_OBLIGATION_ONE),
                    _anchor("R-B", 1, sentence=_TWO_OBLIGATIONS_SENTENCE, core=_OBLIGATION_TWO),
                ]
            )
            == []
        )


class TestADanglingRecordIsPointedAtItsNeighbour:
    def test_the_preceding_record_is_proposed_as_the_supplier(self) -> None:
        edges = discover_referent_relationships(
            [
                _anchor("R-SUPPLIER", 0, sentence=_RESOLVES_SENTENCE),
                _anchor("R-DANGLES", 1, sentence=_DANGLES_SENTENCE, unresolved=["that period"]),
            ]
        )

        assert len(edges) == 1
        assert (edges[0].source_rule_id, edges[0].target_rule_id) == (
            "R-DANGLES",
            "R-SUPPLIER",
        )
        assert edges[0].state == "candidate", (
            "which neighbour supplies the referent is a proposal; recording it as "
            "established would put a positional guess into the field consumers read "
            "as fact"
        )
        assert "that period" in edges[0].evidence.detail

    def test_a_record_that_stands_alone_gets_no_link(self) -> None:
        assert (
            discover_referent_relationships(
                [
                    _anchor("R-SUPPLIER", 0, sentence=_RESOLVES_SENTENCE),
                    _anchor("R-FINE", 1, sentence=_RESOLVES_SENTENCE),
                ]
            )
            == []
        )

    def test_the_link_does_not_alter_the_records_text(self) -> None:
        """The repair is a connection, never a rewrite.

        Splicing a neighbour's words into a record would produce text the
        document does not contain, which is the defect class this platform
        exists to prevent.
        """

        anchors = [
            _anchor("R-SUPPLIER", 0, sentence=_RESOLVES_SENTENCE),
            _anchor("R-DANGLES", 1, sentence=_DANGLES_SENTENCE, unresolved=["that period"]),
        ]
        before = [anchor.text for anchor in anchors]

        discover_referent_relationships(anchors)

        assert [anchor.text for anchor in anchors] == before
