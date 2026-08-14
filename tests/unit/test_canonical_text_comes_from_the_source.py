"""The stored wording must be the document's wording, not merely a faithful copy.

`verify_verbatim` proves the extraction model copied what it was shown.
`verify_fragments` proves each fragment's offsets resolve. Between them sat an
unchecked step: whether `CanonicalElement.text` was actually built from the
fragments it records. A defect there passes both neighbouring checks, because
the fragments still resolve and the model still copies faithfully — both sides
of the verbatim comparison carry the same corruption.

These tests target that step, and every scan asserts it can still see, because
a checker that walks nothing reports success.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.infrastructure.ingestion.canonical_fidelity import (
    rebuild_element_text,
    verify_element_text,
)

DOCUMENTS = Path(__file__).resolve().parents[2] / "data" / "documents"
SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "source-documents"


def _document(page_text: str, elements: list[CanonicalElement]) -> CanonicalDocument:
    return CanonicalDocument(
        document_id="doc",
        page_count=1,
        parser="test",
        pages=[CanonicalPage(page=1, raw_text=page_text)],
        elements=elements,
    )


def _element(
    text: str,
    spans: list[tuple[int, int, str]],
    transformations: list[str],
    *,
    element_id: str = "E1",
    page: int = 1,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type="paragraph",
        logical_order=1,
        text=text,
        transformations=transformations,
        source_fragments=[
            SourceFragment(page=page, start_offset=start, end_offset=end, text=body)
            for start, end, body in spans
        ],
    )


def _assert_the_check_saw(document: CanonicalDocument) -> FidelityReport:
    """Run the check, having first proved it has something to look at.

    Every assertion below depends on the scan reaching an element. A document
    with no elements produces an empty failure list that is indistinguishable
    from a clean one.
    """

    assert document.elements, "nothing to verify — the check would pass blindly"
    return verify_element_text(document)


class TestTextIsItsFragmentsJoinedAsDeclared:
    def test_a_space_join_is_reproduced(self) -> None:
        raw = "the employee may\nrequest leave"
        element = _element(
            "the employee may request leave",
            [(0, len(raw), raw)],
            ["line_join_space"],
        )
        assert _assert_the_check_saw(_document(raw, [element])).failures == []

    def test_a_hyphen_join_keeps_the_hyphen(self) -> None:
        # "employ-" + "ment" becomes "employ-ment", never "employment":
        # _join_lines preserves the hyphen because it cannot tell a real
        # compound from line-break hyphenation.
        raw = "the employ-\nment contract"
        element = _element(
            "the employ-ment contract",
            [(0, len(raw), raw)],
            ["line_break_hyphen_join", "line_join_space"],
        )
        assert _assert_the_check_saw(_document(raw, [element])).failures == []

    def test_a_page_boundary_joins_like_any_other_break(self) -> None:
        # The boundary can fall mid-word: "...leave is" | "requested on..."
        element = CanonicalElement(
            element_id="E1",
            element_type="paragraph",
            logical_order=1,
            text="the leave is requested on this basis",
            transformations=["line_join_space", "cross_page_join"],
            source_fragments=[
                SourceFragment(page=1, start_offset=0, end_offset=13, text="the leave is"),
                SourceFragment(page=2, start_offset=0, end_offset=23, text="requested on this basis"),
            ],
        )
        document = CanonicalDocument(
            document_id="doc",
            page_count=2,
            parser="test",
            pages=[
                CanonicalPage(page=1, raw_text="the leave is"),
                CanonicalPage(page=2, raw_text="requested on this basis"),
            ],
            elements=[element],
        )
        assert _assert_the_check_saw(document).failures == []


class TestAReorderedElementIsCaught:
    """The shape of the right-to-left paint-order defect.

    The fragments still resolve to their offsets and the model still copies
    what it is shown. Only this check can see that the stored text is not the
    order the document reads in.
    """

    def test_reordered_text_fails_even_though_its_fragments_resolve(self) -> None:
        raw = "first clause\nsecond clause"
        honest = _element(
            "first clause second clause", [(0, len(raw), raw)], ["line_join_space"]
        )
        document = _document(raw, [honest])
        assert _assert_the_check_saw(document).failures == []
        assert document.verify_fragments() == []

        # Now paint it in the wrong order, changing nothing else.
        reordered = _element(
            "second clause first clause", [(0, len(raw), raw)], ["line_join_space"]
        )
        corrupt = _document(raw, [reordered])

        # The link that used to carry the guarantee still passes ...
        assert corrupt.verify_fragments() == []
        # ... and this is the check that does not.
        failures = _assert_the_check_saw(corrupt).failures
        assert len(failures) == 1
        assert "not its fragments joined as declared" in failures[0]

    def test_an_inserted_word_is_caught(self) -> None:
        raw = "the employee may not"
        element = _element(
            "the employee may never", [(0, len(raw), raw)], ["line_join_space"]
        )
        failures = _assert_the_check_saw(_document(raw, [element])).failures
        assert len(failures) == 1


class TestTheCheckFailsClosed:
    def test_an_unmodelled_transformation_is_a_failure_not_an_exemption(self) -> None:
        """A kind this module was never taught must not pass unmodelled.

        The joins are re-derived here rather than shared with the code that
        performs them, which is what makes the check independent. The price is
        that a new transformation kind could be tolerated silently, so it is
        refused instead.
        """

        raw = "some text"
        element = _element("anything at all", [(0, len(raw), raw)], ["line_join_space"])
        # Bypass the Literal at construction: the risk being modelled is a
        # future kind reaching this code, not one a test can legally build.
        object.__setattr__(element, "transformations", ["dehyphenate"])
        failures = _assert_the_check_saw(_document(raw, [element])).failures
        assert len(failures) == 1
        assert "cannot reproduce" in failures[0]

    def test_text_with_no_recorded_source_is_reported_not_skipped(self) -> None:
        element = CanonicalElement(
            element_id="E1",
            element_type="paragraph",
            logical_order=1,
            text="a rule with no provenance",
            source_fragments=[],
        )
        failures = _assert_the_check_saw(_document("", [element])).failures
        assert len(failures) == 1
        assert "records no source fragments" in failures[0]


class TestATableRowIsUnprovableNotVerified:
    """The exclusion must never be readable as a pass.

    A table row's text is `" | ".join(cells)` — a separator absent from the
    source — positioned by bounding box, so its fragments interleave cells the
    row does not contain. This check cannot reconstruct it, and says so instead
    of quietly counting it as verified.
    """

    def _row(self) -> CanonicalElement:
        return CanonicalElement(
            element_id="E1",
            element_type="table_row",
            logical_order=1,
            text="Version | 6",
            transformations=["table_cell_join"],
            source_fragments=[
                SourceFragment(page=1, start_offset=0, end_offset=9, text="Version 6")
            ],
        )

    def test_it_is_counted_as_unprovable(self) -> None:
        report = _assert_the_check_saw(_document("Version 6", [self._row()]))
        assert report.failures == []
        assert len(report.unprovable) == 1
        assert "cannot be reconstructed" in report.unprovable[0]

    def test_it_is_not_counted_as_verified(self) -> None:
        """The distinction the report type exists to hold.

        Were the row silently skipped, `verified` would still read 0 but
        `checked` would too — and a caller summing verified against element
        count would conclude the document was proved.
        """

        report = _assert_the_check_saw(_document("Version 6", [self._row()]))
        assert report.verified == 0
        assert report.checked == 0

    def test_the_exclusion_is_by_transformation_not_by_element_type(self) -> None:
        """Narrowness control: prose is still checked, table or not.

        If the exclusion keyed on `element_type` it would swallow any element
        a converter happened to label a row, including one built by an ordinary
        line join.
        """

        prose_in_a_row = CanonicalElement(
            element_id="E1",
            element_type="table_row",
            logical_order=1,
            text="wrong text entirely",
            transformations=["line_join_space"],
            source_fragments=[
                SourceFragment(page=1, start_offset=0, end_offset=9, text="Version 6")
            ],
        )
        report = _assert_the_check_saw(_document("Version 9", [prose_in_a_row]))
        assert len(report.failures) == 1
        assert report.unprovable == []


class TestTheCheckIsNotBlind:
    def test_an_empty_document_is_caught_by_that_assertion(self) -> None:
        """A scan of nothing returns [] — identical to a clean result.

        This is the failure this repository has met repeatedly, so the guard
        against it is asserted rather than assumed.
        """

        empty = CanonicalDocument(document_id="doc", page_count=0, parser="test")
        assert verify_element_text(empty).failures == []
        assert verify_element_text(empty).checked == 0
        with pytest.raises(AssertionError, match="pass blindly"):
            _assert_the_check_saw(empty)

    def test_the_rebuild_is_not_a_no_op_returning_the_stored_text(self) -> None:
        """Prove the reconstruction derives text rather than echoing it."""

        raw = "alpha\nbeta"
        element = _element("alpha beta", [(0, len(raw), raw)], ["line_join_space"])
        assert rebuild_element_text(element) == "alpha beta"
        # It reads the fragments, not element.text: change only the stored
        # text and the rebuild is unmoved.
        object.__setattr__(element, "text", "something else entirely")
        assert rebuild_element_text(element) == "alpha beta"


class TestAgainstRealDocuments:
    """Run against tracked sample documents, not the local-only corpus.

    `data/documents/` is untracked, so a test anchored there skips wherever the
    corpus is absent — and a skipped check is the silent gap this whole file
    exists to argue against. The DOCX samples are in the repository.

    WHAT THIS DELIBERATELY DOES NOT COVER
    -------------------------------------
    The tracked PDF is excluded. It ingests in ~20s against ~1.4s for all four
    DOCX, which is a third again on a suite that runs in about a minute, and
    the transformations only it exercises on real input — `cross_page_join` and
    `line_break_hyphen_join`, 5 of its 502 elements — are covered exactly by
    the synthetic cases above. It was measured separately at 502/502, as were
    the DOCX (215/215) and a second hardware revision.

    This is a stated coverage limit rather than an oversight. Promoting it into
    the routine suite is a decision about test tiers that this repository has
    no convention for yet.
    """

    def test_the_sample_corpus_reconstructs_exactly(self) -> None:
        from policy_platform.infrastructure.ingestion.document_ingestion import ingest_docx

        assert SAMPLES.is_dir(), "sample corpus missing — the scan would see nothing"
        sources = sorted(SAMPLES.glob("*.docx"))
        assert sources, "no source documents found — the scan would pass blindly"

        checked = 0
        for path in sources:
            document = ingest_docx(str(path))
            report = verify_element_text(document)
            assert report.failures == [], f"{path.name} does not reconstruct"
            checked += report.checked

        # Narrowness control: a rule that reconstructs three elements proves
        # very little. State the floor so a corpus that quietly shrinks is
        # visible rather than reassuring.
        assert checked > 300, f"only {checked} elements verified — too few to mean much"
