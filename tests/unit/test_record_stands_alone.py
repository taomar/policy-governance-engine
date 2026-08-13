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
)
from policy_platform.infrastructure.extraction.evaluability import Evaluability, assess
from policy_platform.infrastructure.extraction.self_containment import unresolved_referents
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
