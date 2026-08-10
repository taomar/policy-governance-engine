"""Tests for the legacy-versus-Docling shadow comparison.

The comparison's job is to answer one question honestly: did any content the
legacy parser recovered disappear under Docling? These tests concentrate on the
ways a comparison could answer "no" while being wrong — by treating structural
difference as loss, or by treating loss as structural difference.
"""
from __future__ import annotations

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.infrastructure.docling.shadow_comparison import compare, format_report


def _document(texts: list[tuple[str, str]], parser: str, markers: dict[int, str] | None = None) -> CanonicalDocument:
    """Build a canonical document from (element_type, text) pairs."""

    elements: list[CanonicalElement] = []
    parts: list[str] = []
    cursor = 0
    for index, (element_type, text) in enumerate(texts):
        start, end = cursor, cursor + len(text)
        elements.append(
            CanonicalElement(
                element_id=f"E{index}",
                element_type=element_type,  # type: ignore[arg-type]
                logical_order=index,
                text=text,
                list_marker=(markers or {}).get(index),
                source_fragments=[
                    SourceFragment(page=1, start_offset=start, end_offset=end, text=text)
                ],
            )
        )
        parts.append(text)
        cursor = end + 1
    return CanonicalDocument(
        document_id="DOC",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text="\n".join(parts))],
        elements=elements,
        parser=parser,
    )


class TestContentLoss:
    def test_identical_content_scores_perfect_recall(self) -> None:
        legacy = _document([("paragraph", "Employees must apply in writing.")], "pdfplumber")
        docling = _document([("paragraph", "Employees must apply in writing.")], "docling")

        result = compare(legacy, docling, document_name="x.docx")
        assert result.recall == 1.0
        assert not result.blocks_cutover

    def test_missing_content_blocks_cutover(self) -> None:
        """A sentence that vanished is a policy statement no longer extractable."""

        legacy = _document(
            [
                ("paragraph", "Employees must apply in writing."),
                ("paragraph", "Contractors are excluded entirely."),
            ],
            "pdfplumber",
        )
        docling = _document([("paragraph", "Employees must apply in writing.")], "docling")

        result = compare(legacy, docling, document_name="x.docx")
        assert result.blocks_cutover
        assert result.recall < 1.0
        assert "contractors" in result.missing_tokens

    def test_resegmentation_alone_is_not_treated_as_loss(self) -> None:
        """The converters legitimately disagree about where elements begin.

        Comparing element counts or raw strings would report a huge difference
        that means nothing.
        """

        legacy = _document(
            [("paragraph", "Employees must apply in writing. Approval is required.")],
            "pdfplumber",
        )
        docling = _document(
            [
                ("paragraph", "Employees must apply in writing."),
                ("paragraph", "Approval is required."),
            ],
            "docling",
        )

        result = compare(legacy, docling, document_name="x.docx")
        assert result.recall == 1.0
        assert not result.blocks_cutover
        assert result.legacy_elements != result.docling_elements

    def test_added_content_is_reported_but_does_not_block(self) -> None:
        """Recovering table headers the old path dropped is an improvement."""

        legacy = _document([("table_row", "P1 15 minutes")], "python-docx")
        docling = _document(
            [
                ("table_cell", "Severity"),
                ("table_cell", "SLA"),
                ("table_cell", "P1"),
                ("table_cell", "15 minutes"),
            ],
            "docling",
        )

        result = compare(legacy, docling, document_name="x.docx")
        assert not result.blocks_cutover
        assert result.added_token_count > 0
        assert "severity" in result.added_tokens

    def test_case_and_unicode_differences_are_not_loss(self) -> None:
        legacy = _document([("paragraph", "Übergabe ﬁve DAYS")], "pdfplumber")
        docling = _document([("paragraph", "übergabe five days")], "docling")

        assert compare(legacy, docling, document_name="x.docx").recall == 1.0

    def test_short_decisive_words_are_not_filtered_away(self) -> None:
        """Aggressive stopword removal would hide the loss of 'not'."""

        legacy = _document([("paragraph", "Costs must not exceed five days.")], "pdfplumber")
        docling = _document([("paragraph", "Costs must exceed five days.")], "docling")

        result = compare(legacy, docling, document_name="x.docx")
        assert result.blocks_cutover
        assert "not" in result.missing_tokens

    def test_a_relocated_list_marker_is_not_reported_as_loss(self) -> None:
        """Legacy keeps 'D.' in the text; Docling holds it as structure.

        Comparing text alone would report the label as lost when it merely moved.
        """

        legacy = _document(
            [("list_item", "D. The outside employment should not embarrass the Foundation.")],
            "pdfplumber",
        )
        docling = _document(
            [("list_item", "The outside employment should not embarrass the Foundation.")],
            "docling",
            markers={0: "D."},
        )

        result = compare(legacy, docling, document_name="x.pdf")
        assert result.recall == 1.0
        assert not result.blocks_cutover

    def test_a_genuinely_dropped_marker_is_still_reported(self) -> None:
        """The counterpart: relocation is fine, disappearance is not."""

        legacy = _document([("list_item", "D. Employees must apply.")], "pdfplumber")
        docling = _document([("list_item", "Employees must apply.")], "docling")

        result = compare(legacy, docling, document_name="x.pdf")
        assert result.blocks_cutover
        assert "d" in result.missing_tokens


class TestIntegrity:
    def test_unresolvable_docling_fragments_block_cutover(self) -> None:
        legacy = _document([("paragraph", "A clause.")], "pdfplumber")
        docling = _document([("paragraph", "A clause.")], "docling")
        docling.elements[0].source_fragments[0].start_offset = 99

        result = compare(legacy, docling, document_name="x.docx")
        assert result.docling_fragment_failures > 0
        assert result.blocks_cutover

    def test_empty_legacy_document_does_not_divide_by_zero(self) -> None:
        legacy = _document([], "pdfplumber")
        docling = _document([("paragraph", "A clause.")], "docling")

        result = compare(legacy, docling, document_name="x.docx")
        assert result.recall == 1.0
        assert not result.blocks_cutover


class TestReport:
    def test_report_states_the_verdict_per_document(self) -> None:
        legacy = _document([("paragraph", "A clause.")], "pdfplumber")
        docling = _document([("paragraph", "A clause.")], "docling")

        report = format_report([compare(legacy, docling, document_name="x.docx")])
        assert "x.docx" in report
        assert "no content loss" in report
        assert "No document lost content" in report

    def test_report_names_blocking_documents(self) -> None:
        legacy = _document([("paragraph", "Contractors are excluded.")], "pdfplumber")
        docling = _document([("paragraph", "Employees apply.")], "docling")

        report = format_report([compare(legacy, docling, document_name="bad.docx")])
        assert "BLOCKS CUTOVER" in report
        assert "bad.docx" in report

    def test_report_shows_structural_change_separately_from_fidelity(self) -> None:
        """Structural gain is the reason to migrate, not evidence of fidelity."""

        legacy = _document([("table_row", "P1 15 minutes")], "python-docx")
        docling = _document([("table_cell", "P1"), ("table_cell", "15 minutes")], "docling")

        report = format_report([compare(legacy, docling, document_name="x.docx")])
        assert "legacy element types" in report
        assert "docling element types" in report
        assert "table_cell" in report
