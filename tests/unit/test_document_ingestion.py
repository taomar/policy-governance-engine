"""Boundary tests for canonical document ingestion (spec sections 47-53).

These target the failures that are *invisible downstream*: text that reads
plausibly but was assembled wrongly. A cut paragraph, a welded two-column line,
or a shredded table all produce output that looks like ordinary prose, so
nothing later in the pipeline can flag them — they have to be caught here.
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
from policy_platform.infrastructure import document_ingestion as ingestion
from policy_platform.infrastructure.document_ingestion import (
    IngestionError,
    _Block,
    _classify_line,
    _continues_previous,
    _detect_columns,
    _is_genuine_table,
    _join_lines,
    _Line,
)

DOCUMENTS = Path(__file__).resolve().parents[2] / "data" / "documents"
LABOR_LAW = DOCUMENTS / "76d9d9d5-fa0b-42c1-bd84-fcdf772ecea4_v1_262c0074-a07a-46d7-aec5-aa339fa11179-saudilaborlaw.pdf"
HARDWARE_DOCX = DOCUMENTS / "fd1a8004-0876-42fc-82ea-87599bcdc942_v2_Workplace-Hardware-Provisioning-Policy-v3.3.docx"


def _line(text: str, *, top=0.0, x0=0.0, x1=100.0, size=10.0, page=1) -> _Line:
    return _Line(
        text=text,
        top=top,
        bottom=top + 10,
        x0=x0,
        x1=x1,
        size=size,
        page=page,
        start_offset=0,
        end_offset=len(text),
    )


class TestLineJoining:
    """Spec section 10: only characters from source fragments may participate."""

    def test_joins_lines_with_a_single_space(self):
        text, transformations = _join_lines([_line("If an employee is absent"), _line("for thirty days")])
        assert text == "If an employee is absent for thirty days"
        assert "line_join_space" in transformations

    def test_preserves_hyphen_rather_than_guessing_a_word(self):
        # "non-" + "renewal" must not become "nonrenewal", a token that appears
        # nowhere in the source.
        text, transformations = _join_lines([_line("notice of non-"), _line("renewal shall be given")])
        assert text == "notice of non-renewal shall be given"
        assert "line_break_hyphen_join" in transformations

    def test_never_inserts_a_word(self):
        text, _ = _join_lines([_line("The employee must obtain"), _line("approval prior to travel.")])
        assert text == "The employee must obtain approval prior to travel."
        assert "manager" not in text

    def test_single_line_needs_no_transformation(self):
        text, transformations = _join_lines([_line("A standalone sentence.")])
        assert text == "A standalone sentence."
        assert transformations == []


class TestClassification:
    def test_provision_label_is_a_heading(self):
        assert _classify_line(_line("Article 12"), 10.0) == "heading"
        assert _classify_line(_line("Article (81)"), 10.0) == "heading"
        assert _classify_line(_line("Chapter 1: Definitions"), 10.0) == "heading"

    def test_provision_citation_inside_a_sentence_is_not_a_heading(self):
        # This is a real policy clause that merely begins with a citation.
        # Promoting it to a heading loses it from extraction entirely and
        # mislabels the section of everything that follows.
        line = _line("Article (81) of the Labor Law during the training term or within")
        assert _classify_line(line, 10.0) == "paragraph"

    def test_numbered_sentence_is_not_a_heading(self):
        line = _line("2.1 Such jobs shall not be potentially harmful to their health.")
        assert _classify_line(line, 10.0) == "paragraph"

    def test_larger_font_is_a_heading(self):
        assert _classify_line(_line("Scope And Purpose", size=14.0), 10.0) == "heading"

    def test_bullet_is_a_list_item(self):
        assert _classify_line(_line("1. Employees shall submit a request."), 10.0) == "list_item"
        assert _classify_line(_line("(a) written notice"), 10.0) == "list_item"


class TestGenuineTable:
    """Spec section 13: a chunk boundary must never split a sentence."""

    def test_multi_column_table_is_genuine(self):
        rows = [["Tier", "Limit"], ["1", "5000"], ["2", "10000"]]
        assert _is_genuine_table(rows) is True

    def test_bordered_paragraph_is_not_a_table(self):
        # A framed callout registers as a one-column table; accepting it splits
        # one paragraph into four "rows".
        rows = [
            ["", "Article (6)", ""],
            ["", "Incidental workers shall be subject to the provisions of duties,", ""],
            ["", "disciplinary rules, the maximum working hours, and daily rest.", ""],
        ]
        assert _is_genuine_table(rows) is False

    def test_single_row_is_not_a_table(self):
        assert _is_genuine_table([["Tier", "Limit"]]) is False


class TestColumnDetection:
    def test_single_column_prose_has_no_gutter(self):
        lines = [_line(f"line {i}", top=i * 12, x0=50, x1=550) for i in range(20)]
        assert _detect_columns(lines, 600.0) == []

    def test_two_column_layout_is_detected(self):
        left = [_line(f"left {i}", top=i * 12, x0=50, x1=270) for i in range(12)]
        right = [_line(f"right {i}", top=i * 12, x0=330, x1=550) for i in range(12)]
        columns = _detect_columns(left + right, 600.0)
        assert len(columns) == 2

    def test_ragged_right_margin_is_not_a_gutter(self):
        lines = [_line(f"line {i}", top=i * 12, x0=50, x1=400 + (i % 5) * 20) for i in range(20)]
        assert _detect_columns(lines, 600.0) == []

    def test_too_few_lines_yields_no_columns(self):
        lines = [_line("a", top=0, x0=50, x1=100), _line("b", top=12, x0=400, x1=450)]
        assert _detect_columns(lines, 600.0) == []


class TestCrossPageContinuation:
    def _block(self, kind, text, page=1):
        return _Block(element_type=kind, lines=[_line(text, page=page)])

    def test_open_sentence_continues_onto_next_page(self):
        previous = self._block("paragraph", "If an employee is absent from work for more than", page=1)
        nxt = self._block("paragraph", "thirty consecutive days, the employer may terminate.", page=2)
        assert _continues_previous(previous, nxt) is True

    def test_completed_sentence_does_not_continue(self):
        previous = self._block("paragraph", "The employer shall keep records.", page=1)
        nxt = self._block("paragraph", "Wages shall be paid in the national currency.", page=2)
        assert _continues_previous(previous, nxt) is False

    def test_new_article_is_a_hard_boundary(self):
        previous = self._block("paragraph", "the employer may terminate the contract without", page=1)
        nxt = self._block("paragraph", "Article 80 The employer may terminate without award", page=2)
        assert _continues_previous(previous, nxt) is False

    def test_new_list_item_is_a_hard_boundary(self):
        previous = self._block("paragraph", "the following shall apply to any worker who", page=1)
        nxt = self._block("paragraph", "1. fails to report for duty", page=2)
        assert _continues_previous(previous, nxt) is False

    def test_heading_never_continues_a_paragraph(self):
        previous = self._block("paragraph", "the employer may terminate the contract without", page=1)
        nxt = self._block("heading", "Article 81", page=2)
        assert _continues_previous(previous, nxt) is False


class TestFragmentVerification:
    def test_resolvable_offsets_pass(self):
        page = CanonicalPage(page=1, raw_text="The employer shall keep records.")
        element = CanonicalElement(
            element_id="E000001",
            element_type="paragraph",
            logical_order=0,
            text="The employer",
            source_fragments=[SourceFragment(page=1, start_offset=0, end_offset=12, text="The employer")],
        )
        document = CanonicalDocument(
            document_id="d", page_count=1, pages=[page], elements=[element], parser="test"
        )
        assert document.verify_fragments() == []

    def test_unresolvable_offsets_are_reported(self):
        page = CanonicalPage(page=1, raw_text="The employer shall keep records.")
        element = CanonicalElement(
            element_id="E000001",
            element_type="paragraph",
            logical_order=0,
            text="something else",
            source_fragments=[SourceFragment(page=1, start_offset=0, end_offset=12, text="Wrong text!!")],
        )
        document = CanonicalDocument(
            document_id="d", page_count=1, pages=[page], elements=[element], parser="test"
        )
        assert len(document.verify_fragments()) == 1


class TestUnsupportedInput:
    def test_unknown_type_is_rejected_clearly(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("hello")
        with pytest.raises(IngestionError):
            ingestion.ingest_document(target)

    def test_corrupt_pdf_raises_rather_than_returning_empty(self, tmp_path):
        target = tmp_path / "broken.pdf"
        target.write_bytes(b"%PDF-1.4 this is not a real pdf")
        with pytest.raises(IngestionError):
            ingestion.ingest_document(target)


@pytest.mark.skipif(not LABOR_LAW.exists(), reason="sample PDF not present")
class TestRealPdf:
    """Spec sections 51-53 against a real document."""

    @pytest.fixture(scope="class")
    def document(self):
        return ingestion.ingest_pdf(LABOR_LAW, "labor-law")

    def test_every_page_is_ingested(self, document):
        # INVARIANT 1.
        assert document.page_count == 50
        assert len(document.pages) == 50

    def test_every_fragment_resolves(self, document):
        # INVARIANT 4 and 5.
        assert document.verify_fragments() == []

    def test_elements_form_a_total_order(self, document):
        # INVARIANT 2.
        orders = [element.logical_order for element in document.elements]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)

    def test_paragraphs_are_reconnected_across_pages(self, document):
        # INVARIANT 3: a page boundary is not a semantic boundary.
        assert any(element.spans_pages for element in document.elements)

    def test_no_word_is_invented(self, document):
        # INVARIANT 6, checked over the whole document rather than a sample.
        import re
        from collections import Counter

        def words(value: str) -> list[str]:
            return re.findall(r"\w+", value.lower())

        for element in document.elements:
            if element.table_id:
                continue  # table text is a recorded cell join, not a line join
            available: Counter[str] = Counter()
            for fragment in element.source_fragments:
                available.update(words(fragment.text))
            for word in words(element.text):
                assert available[word] > 0, f"{element.element_id} invented {word!r}"
                available[word] -= 1

    def test_coverage_is_near_total(self, document):
        # INVARIANT 8: the only characters that may go missing are the running
        # headers deliberately removed from the logical flow.
        raw = sum(len("".join(page.raw_text.split())) for page in document.pages)
        kept = sum(len("".join(element.text.split())) for element in document.elements)
        assert kept / raw > 0.95

    def test_ingestion_is_deterministic(self):
        # Spec section 45: identical bytes produce identical ids and offsets.
        first = ingestion.ingest_pdf(LABOR_LAW, "labor-law")
        second = ingestion.ingest_pdf(LABOR_LAW, "labor-law")
        assert [e.element_id for e in first.elements] == [e.element_id for e in second.elements]
        assert [e.text for e in first.elements] == [e.text for e in second.elements]
        assert [
            (f.page, f.start_offset, f.end_offset)
            for e in first.elements
            for f in e.source_fragments
        ] == [
            (f.page, f.start_offset, f.end_offset)
            for e in second.elements
            for f in e.source_fragments
        ]

    def test_sections_are_attributed(self, document):
        paragraphs = [e for e in document.elements if e.element_type == "paragraph"]
        attributed = [e for e in paragraphs if e.section]
        assert len(attributed) / len(paragraphs) > 0.5


@pytest.mark.skipif(not HARDWARE_DOCX.exists(), reason="sample DOCX not present")
class TestRealDocx:
    @pytest.fixture(scope="class")
    def document(self):
        return ingestion.ingest_docx(HARDWARE_DOCX, "hardware")

    def test_fragments_resolve(self, document):
        assert document.verify_fragments() == []

    def test_table_rows_keep_cell_values_verbatim(self, document):
        rows = [e for e in document.elements if e.element_type == "table_row"]
        assert rows, "expected the approval-tier tables to survive ingestion"
        raw = document.page_text(1)
        for row in rows:
            # Each cell value must appear in the source; the pipe separator is
            # structural, never editorial.
            for cell in row.text.split(" | "):
                if cell.strip():
                    assert cell.strip() in raw

    def test_table_headers_are_preserved_not_flattened(self, document):
        rows = [e for e in document.elements if e.element_type == "table_row" and e.table_headers]
        assert rows, "expected at least one table with headers"
        for row in rows:
            assert "; " not in row.text or " | " in row.text


class TestWithinPageContinuation:
    """Merging used to be gated on `index == 0`, so only a page-leading block
    could ever be joined and a sentence cut mid-page stayed cut.

    Two clauses in AD-103 begin mid-sentence for that reason, and each produced
    a duplicate rule: the formulator reconstructs the governing sentence from
    inherited context for the orphaned half, remaking a rule the preceding
    clause already produced. Two cuts, two duplicate pairs, exact
    correspondence.
    """

    def _block(self, kind, text, page=1):
        return _Block(element_type=kind, lines=[_line(text, page=page)])

    def test_a_bracket_continues_within_a_page(self):
        """The real cut: "...one employee of the married couple" | "(husband
        and wife). In the case of...". Both on page 2."""

        previous = self._block(
            "paragraph", "The housing allowance is limited to one employee of the married couple", page=2
        )
        nxt = self._block(
            "paragraph", "(husband and wife). In the case of a married couple are employed by FBSU", page=2
        )
        assert _continues_previous(previous, nxt, same_page=True) is True

    def test_a_lowercase_start_continues_within_a_page(self):
        """The other real cut: "...is calculated as twice" | "the monthly basic
        salary up to a maximum of:"."""

        previous = self._block(
            "paragraph", "The housing allowance per calendar year (12 months) is calculated as twice", page=2
        )
        nxt = self._block("paragraph", "the monthly basic salary up to a maximum of:", page=2)
        assert _continues_previous(previous, nxt, same_page=True) is True

    def test_a_capitalised_block_does_not_continue_within_a_page(self):
        """Within a page a block break carries layout meaning — spacing, a font
        change, a new column — so a capitalised block after an unpunctuated one
        is commonly a genuine new paragraph. Across a page break the same pair
        does continue, because a sentence does not normally end at a page
        boundary without punctuation."""

        previous = self._block("paragraph", "The employer shall keep records of", page=2)
        nxt = self._block("paragraph", "Employees are entitled to annual leave.", page=2)
        assert _continues_previous(previous, nxt, same_page=True) is False
        assert _continues_previous(previous, nxt, same_page=False) is True

    def test_a_completed_sentence_never_continues(self):
        previous = self._block("paragraph", "The housing allowance is paid monthly.", page=2)
        nxt = self._block("paragraph", "(husband and wife) are both eligible.", page=2)
        assert _continues_previous(previous, nxt, same_page=True) is False

    def test_a_provision_number_is_still_a_hard_boundary(self):
        previous = self._block("paragraph", "The housing allowance is limited to one employee of", page=2)
        nxt = self._block("paragraph", "3.4.2. Transportation allowance is paid separately.", page=2)
        assert _continues_previous(previous, nxt, same_page=True) is False

    def test_a_list_marker_is_still_a_hard_boundary(self):
        previous = self._block("paragraph", "The allowance is limited to one employee of", page=2)
        nxt = self._block("paragraph", "1. the married couple", page=2)
        assert _continues_previous(previous, nxt, same_page=True) is False
