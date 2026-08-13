"""Guard: text captured as display glyphs must be reported, never repaired.

WHAT THIS PROTECTS
------------------
Some extractors read a PDF's painted glyph stream and record what was drawn
rather than what was written. The stored codepoints are then presentation forms
— the shaped glyph a renderer picked for a letter given its neighbours — and
not the characters the document contains.

This is a general text-extraction defect, not a property of any language. It
affects every script whose letters have positional forms, and it affects an
otherwise English document that quotes a single term in one of them.

It is unusually dangerous because it defeats the check that would normally
catch it. This platform promises that an attribute holds the source's words
verbatim, and a verbatim comparison between a record and the canonical store
compares one rendering against the same rendering and reports a match. The
corruption is invisible to anything treating the canonical store as ground
truth, so it has to be caught at ingestion.

TWO PROPERTIES, BOTH LOAD-BEARING
---------------------------------
1. It fires for any document with the property, in any script, and stays silent
   for correctly-encoded text — including correctly-encoded text in the very
   scripts most likely to trigger a naive check.
2. It changes nothing. Detection only. A stored value that reads oddly is a
   defect a reviewer can see; a value silently rewritten into something the
   document does not contain is a defect nobody can see.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    SourceFragment,
)
from policy_platform.infrastructure.ingestion import document_extraction
from policy_platform.infrastructure.settings import Settings

DIAGNOSTIC_CODE = "display_glyphs_not_characters"

#: Text already stored as display glyphs — the defect itself. Several scripts,
#: so nothing can come to depend on one of them.
GLYPH_TEXT = {
    "arabic": "\ufe9f\ufeaa\ufe8d\ufeed\ufee0",
    "arabic_ligature_block": "\ufdf2",
    "farsi": "\ufb8b\ufeeb\ufead",
}

#: Correctly-encoded text. None of this may ever raise the diagnostic — these
#: are exactly the cases a script-based or direction-based check gets wrong.
CLEAN_TEXT = {
    "arabic": "جداول المخالفات والجزاءات",
    "hebrew": "מדיניות משאבי אנוש",
    "farsi": "سیاست منابع انسانی",
    "syriac": "ܟܬܒܐ ܕܝܠܢܝܐ",
    "thaana": "ދިވެހި ސިޔާސަތު",
    "english": "Employees must submit the request within 15 minutes.",
    "greek": "Πολιτική ανθρώπινου δυναμικού",
    "cjk": "人事方針",
    # Typographic ligatures and fullwidth forms are compatibility characters
    # too, but they are not *positional* glyphs and appear in ordinary text.
    # A check that matched them would cry wolf on routine documents.
    "latin_ligature": "The o\ufb03ce \ufb01le was classi\ufb01ed.",
    "fullwidth": "\uff21\uff22\uff23 全角",
}


def _document(*texts: str, pages: tuple[int, ...] | None = None) -> CanonicalDocument:
    """A canonical document whose elements carry the given text, one per page."""

    page_numbers = pages or tuple(range(1, len(texts) + 1))
    elements = [
        CanonicalElement(
            element_id=f"E{index:06d}",
            element_type="paragraph",
            logical_order=index,
            text=text,
            source_fragments=[
                SourceFragment(page=page, start_offset=0, end_offset=len(text), text=text)
            ],
        )
        for index, (text, page) in enumerate(zip(texts, page_numbers))
    ]
    return CanonicalDocument(
        document_id="d",
        source_hash="a" * 64,
        parser="test",
        page_count=max(page_numbers, default=1),
        elements=elements,
    )


class TestItFiresOnDisplayGlyphs:
    @pytest.mark.parametrize("label", sorted(GLYPH_TEXT))
    def test_any_script_stored_as_glyphs_is_reported(self, label: str) -> None:
        diagnostic = document_extraction.detect_display_glyphs(_document(GLYPH_TEXT[label]))

        assert diagnostic is not None
        assert diagnostic.code == DIAGNOSTIC_CODE

    def test_it_fires_when_a_single_quoted_term_is_affected(self) -> None:
        """An otherwise ordinary document quoting one term still misquotes it.

        The defect does not require the document to be "in" any language, which
        is why this cannot be a document-level language judgement.
        """

        document = _document(
            "The following term appears in the source: " + GLYPH_TEXT["arabic"],
            CLEAN_TEXT["english"],
        )

        assert document_extraction.detect_display_glyphs(document) is not None

    def test_the_severity_says_usable_but_not_faithful(self) -> None:
        """Not an error: the document parsed, and its structure is sound.

        What is unsound is any claim that a quoted span reproduces the source's
        characters, and that is a warning a reviewer must see.
        """

        diagnostic = document_extraction.detect_display_glyphs(_document(GLYPH_TEXT["arabic"]))

        assert diagnostic is not None
        assert diagnostic.severity == "warning"

    def test_it_reports_scale_rather_than_a_bare_boolean(self) -> None:
        """A reviewer needs to know whether this is one word or the whole annex."""

        mostly = document_extraction.detect_display_glyphs(_document(GLYPH_TEXT["arabic"]))
        barely = document_extraction.detect_display_glyphs(
            _document(GLYPH_TEXT["arabic"] + CLEAN_TEXT["english"] * 40)
        )

        assert mostly is not None and barely is not None
        assert str(len(GLYPH_TEXT["arabic"])) in mostly.detail
        # Same affected text, far more clean text: the proportion must fall.
        assert mostly.detail != barely.detail

    def test_it_names_the_affected_pages_and_only_those(self) -> None:
        document = _document(
            CLEAN_TEXT["english"],
            GLYPH_TEXT["arabic"],
            CLEAN_TEXT["arabic"],
            GLYPH_TEXT["farsi"],
            pages=(1, 2, 3, 4),
        )

        diagnostic = document_extraction.detect_display_glyphs(document)

        assert diagnostic is not None
        assert "[2, 4]" in diagnostic.detail

    def test_it_surfaces_to_the_upload_caller(self) -> None:
        """`ingestion_warnings` is what the upload route returns.

        A diagnostic nobody is shown prevents nothing.
        """

        document = _document(GLYPH_TEXT["arabic"])
        diagnostic = document_extraction.detect_display_glyphs(document)
        assert diagnostic is not None
        document.diagnostics.append(diagnostic)

        codes = {d.code for d in document_extraction.ingestion_warnings(document)}
        assert DIAGNOSTIC_CODE in codes


class TestItStaysSilentOnCorrectText:
    @pytest.mark.parametrize("label", sorted(CLEAN_TEXT))
    def test_correctly_encoded_text_is_never_flagged(self, label: str) -> None:
        """Including the scripts a script-based check would wrongly accuse.

        Correctly-encoded Arabic, Hebrew, Farsi, Syriac and Thaana are the whole
        point: they are right-to-left, or have positional shaping, or both, and
        a check keyed on script or direction would fire on every one of them.
        """

        assert document_extraction.detect_display_glyphs(_document(CLEAN_TEXT[label])) is None

    def test_an_empty_document_is_not_flagged(self) -> None:
        assert document_extraction.detect_display_glyphs(_document()) is None

    def test_a_document_of_only_punctuation_is_not_flagged(self) -> None:
        """No letters must not mean a division by zero."""

        assert document_extraction.detect_display_glyphs(_document("--- 123 ... ///")) is None


class TestItDetectsWithoutRepairing:
    def test_the_text_is_left_exactly_as_the_converter_produced_it(self) -> None:
        """The rule that must never be relaxed.

        Reversing or normalising quoted text would replace a defect a reviewer
        can see with one nobody can, and this product must not alter the words
        it attributes to a source.
        """

        original = GLYPH_TEXT["arabic"]
        document = _document(original)

        document_extraction.detect_display_glyphs(document)

        assert document.elements[0].text == original
        assert document.elements[0].source_fragments[0].text == original


class TestBothConverterPathsAreChecked:
    """The defect was observed from both parsers, so neither may be exempt."""

    def _settings(self, converter: str) -> Settings:
        return Settings(
            database_url="******localhost:5433/db",
            alembic_database_url="******localhost:5433/db",
            document_converter=converter,
        )

    @pytest.mark.parametrize("converter", ["legacy", "docling"])
    def test_the_seam_appends_the_diagnostic_whichever_parser_ran(
        self, monkeypatch, converter: str
    ) -> None:
        produced = _document(GLYPH_TEXT["arabic"])
        monkeypatch.setattr(
            document_extraction, "get_settings", lambda: self._settings(converter)
        )
        monkeypatch.setattr(
            document_extraction, "ingest_document", lambda *a, **k: produced
        )
        monkeypatch.setattr(
            document_extraction, "_extract_with_docling", lambda *a, **k: produced
        )

        result = document_extraction.extract_document("f.pdf", "application/pdf")

        assert DIAGNOSTIC_CODE in {d.code for d in result.diagnostics}

    @pytest.mark.parametrize("converter", ["legacy", "docling"])
    def test_a_clean_document_gains_no_diagnostic_on_either_path(
        self, monkeypatch, converter: str
    ) -> None:
        produced = _document(CLEAN_TEXT["arabic"], CLEAN_TEXT["english"])
        monkeypatch.setattr(
            document_extraction, "get_settings", lambda: self._settings(converter)
        )
        monkeypatch.setattr(
            document_extraction, "ingest_document", lambda *a, **k: produced
        )
        monkeypatch.setattr(
            document_extraction, "_extract_with_docling", lambda *a, **k: produced
        )

        result = document_extraction.extract_document("f.pdf", "application/pdf")

        assert DIAGNOSTIC_CODE not in {d.code for d in result.diagnostics}
