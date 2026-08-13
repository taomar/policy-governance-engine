"""Severity has to describe what went wrong, not who admitted it.

`judge_logic` originally ranked a quotation mismatch by whether the record
declared `source_origin`. Measured against the live corpus that correlated 100%
with provenance and 0% with the nature of the mismatch, which meant it blocked
hardest on flattened table structure — a defect produced by the extractor that
no reviewer can repair by editing wording — while merely noting phrases the
document does not contain at all. A reviewer taught that blocking findings are
unfixable stops reading them, and a check nobody trusts is worse than no check.

So the axis now follows the shape of the mismatch. These fixtures are synthetic
and structural: no sentence here is copied from any corpus, and none of them
depend on a language, a layout or a document. Each states a shape in the
smallest text that expresses it.
"""

from __future__ import annotations

import pytest

from policy_platform.infrastructure.quality.logic_faithfulness import (
    LogicFindingSeverity,
    MismatchShape,
    classify_mismatch,
)

#: (source, claim, shape). One row per shape the classifier can return, each
#: written to express only that shape.
_SHAPES: list[tuple[str, str, MismatchShape]] = [
    # Several cells welded into one value. The separator is the evidence: a
    # value holding a cell boundary came from more than one cell.
    (
        "Column A Column B Column C",
        "first value | second value | third value",
        MismatchShape.CONCATENATED,
    ),
    (
        "Any heading at all",
        "first value\nsecond value",
        MismatchShape.CONCATENATED,
    ),
    (
        "Any heading at all",
        "first value; second value",
        MismatchShape.CONCATENATED,
    ),
    # Every word present, in the order the sentence gives them, with other
    # words between. This is decomposition working.
    (
        "the reporting and the recording of incidents is required",
        "recording of incidents",
        MismatchShape.DECOMPOSED,
    ),
    (
        "each request must be submitted, reviewed and then approved",
        "request must be approved",
        MismatchShape.DECOMPOSED,
    ),
    # An in-order subsequence that steps over the sentence's negation. This is
    # the dangerous one: it looks exactly like decomposition.
    (
        "a member may not enter the restricted area",
        "a member may enter the restricted area",
        MismatchShape.INVERTED,
    ),
    (
        "such a request is never granted",
        "such a request is granted",
        MismatchShape.INVERTED,
    ),
    # A phrase with no wording in common with the sentence beside it.
    (
        "the reporting of incidents is required",
        "Once confirmed",
        MismatchShape.SUPPLIED,
    ),
    # Words in common, but the phrase itself is not something the sentence
    # says. This is the shape that means fabrication.
    (
        "the process is documented once a year",
        "annual documentation process reviewed by a manager",
        MismatchShape.UNSUPPORTED,
    ),
]


class TestEachShapeIsRecognised:
    """The classifier, shown returning each shape on text expressing it."""

    @pytest.mark.parametrize(
        ("source", "claim", "shape"),
        [pytest.param(s, c, k, id=f"{k.value}-{c[:24]}") for s, c, k in _SHAPES],
    )
    def test_shape(self, source: str, claim: str, shape: MismatchShape) -> None:
        assert classify_mismatch(claim, source) is shape


class TestTheRankingSaysWhatItMeans:
    """The ordering the recalibration exists to produce."""

    def test_a_phrase_the_document_does_not_contain_outranks_a_flattened_cell(
        self,
    ) -> None:
        """Fabrication is the most serious thing this check can find. Flattening
        is serious too, but it is an extraction artefact and ranking it above a
        claim the document never makes is what taught reviewers to ignore the
        top of the list."""

        from policy_platform.infrastructure.quality.logic_faithfulness import (
            _SHAPE_SEVERITY,
        )

        assert _SHAPE_SEVERITY[MismatchShape.UNSUPPORTED] is (
            LogicFindingSeverity.BLOCKING
        )
        assert _SHAPE_SEVERITY[MismatchShape.CONCATENATED] is (
            LogicFindingSeverity.REEXTRACTION
        )
        assert (
            _SHAPE_SEVERITY[MismatchShape.UNSUPPORTED]
            is not _SHAPE_SEVERITY[MismatchShape.CONCATENATED]
        )

    def test_a_reversed_claim_ranks_with_fabrication(self) -> None:
        """A record stating the opposite of its sentence is worse than one
        missing something: it reads as clean and confident and survives review
        for that reason."""

        from policy_platform.infrastructure.quality.logic_faithfulness import (
            _SHAPE_SEVERITY,
        )

        assert _SHAPE_SEVERITY[MismatchShape.INVERTED] is LogicFindingSeverity.BLOCKING

    def test_every_shape_has_a_rank(self) -> None:
        """A shape added later without a severity would raise at the moment a
        reviewer needed the finding, not here.

        `DECOMPOSED` is deliberately absent: it is suppressed rather than
        ranked, because every word is present and in order. Naming it here
        rather than relaxing the comparison keeps a genuinely unranked shape
        from slipping in beside it.
        """

        from policy_platform.infrastructure.quality.logic_faithfulness import (
            _SHAPE_SEVERITY,
        )

        assert set(_SHAPE_SEVERITY) == set(MismatchShape) - {MismatchShape.DECOMPOSED}


class TestNegationIsNotWavedThroughAsDecomposition:
    """The hole this shape exists to close.

    Suppressing in-order subsequences is right — that population is correct
    decomposition — but a subsequence can drop a word that reverses the clause,
    and `may not enter` -> `may enter` is a perfect subsequence. Blanket
    suppression would have silently accepted the exact inversion class this
    project fixed in the decomposition path, in the one check positioned to
    notice it.
    """

    @pytest.mark.parametrize(
        "reversing",
        ["not", "never", "no", "nor", "cannot", "non", "without", "except", "unless"],
    )
    def test_a_dropped_reversing_word_is_never_suppressed(
        self, reversing: str
    ) -> None:
        source = f"a member may {reversing} enter the area"
        claim = "a member may enter the area"
        shape = classify_mismatch(claim, source)
        assert shape is not MismatchShape.DECOMPOSED, (
            f"dropping {reversing!r} was classified as correct decomposition"
        )
        assert shape is MismatchShape.INVERTED

    def test_the_same_sentence_without_the_negation_is_suppressed(self) -> None:
        """The control. It must be the reversing word doing the work, not the
        classifier having gone strict on every gap.

        Note the argument order: `classify_mismatch(claim, source)`. Written the
        other way round this reads as a claim containing a word its sentence
        lacks, returns UNSUPPORTED, and quietly stops being a control.
        """

        assert (
            classify_mismatch(
                "a member may enter the area", "a member may then enter the area"
            )
            is MismatchShape.DECOMPOSED
        )


class TestTheClassifierStillSees:
    """A check whose verdict is a category can go quiet by returning one
    category for everything. These are the floors that would catch that."""

    def test_the_fixtures_exercise_every_shape(self) -> None:
        assert {shape for _, _, shape in _SHAPES} == set(MismatchShape)

    def test_the_classifier_actually_discriminates(self) -> None:
        """A classifier hardwired to return a single value would satisfy every
        individual assertion above that happened to expect that value."""

        produced = {classify_mismatch(c, s) for s, c, _ in _SHAPES}
        assert len(produced) == len(MismatchShape), (
            f"expected {len(MismatchShape)} distinct shapes, got {sorted(p.value for p in produced)}"
        )

    def test_a_contiguous_quotation_is_not_forced_into_a_shape(self) -> None:
        """`classify_mismatch` is only asked about phrases that already failed
        the quotation test. If it were reachable for a clean quotation it would
        have to have somewhere to put it — and it does not, which is why the
        caller must check quotation first. This pins that contract."""

        assert (
            classify_mismatch("of incidents", "the reporting of incidents is required")
            is MismatchShape.DECOMPOSED
        )
