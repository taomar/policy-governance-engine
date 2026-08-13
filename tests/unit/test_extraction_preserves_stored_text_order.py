"""The default converter must not alter text the source already stores correctly.

Why this test exists
--------------------
The document that exposed the text-fidelity problem stores its right-to-left
runs in visual order, so it cannot answer the question that decides whether the
structured converter is safe to make the default: *does the converter change
text that is already correct?* On a document that is already reversed, a
converter that reverses everything looks like a fix.

Two controls settle it. They contain the same characters, in the same font, with
the same ToUnicode mapping, and differ only in the order the glyphs were
painted:

    control_logical_order.pdf   painted at ascending X in logical order
    control_visual_order.pdf    painted at ascending X in visual order

A parser that decides from the evidence in the file handles both. A parser
applying a fixed policy handles exactly one, and which one reveals the policy.

Measured, both converters apply a fixed policy and they are complementary:

                        paint=logical      paint=visual
    legacy              preserved          reversed
    docling             reversed           preserved

So neither is correct in general, and flipping the default would trade one
population of damaged documents for another. This test guards the specific
consequence: whatever converter the platform defaults to must not corrupt text
that arrives correct.

Golden-test discipline
----------------------
The expected strings here are not derived from any parser's output. They are the
codepoints the fixtures were *constructed from* - see `make_controls.py`, which
writes exactly these characters - so they are an independent statement of what
the file contains, not a recording of what the code currently produces.

Nothing here branches on language or script. Both an Arabic and a Hebrew run are
present so the property is not stated about one writing system, and the test
asserts about order only, never about meaning.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from policy_platform.infrastructure.ingestion import document_extraction
from policy_platform.infrastructure.settings import Settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "text-order"
LOGICAL_PDF = FIXTURES / "control_logical_order.pdf"
VISUAL_PDF = FIXTURES / "control_visual_order.pdf"
PDF_MIME = "application/pdf"

#: The characters the fixtures were built from, in the order they are read.
ARABIC = "\u062c\u062f\u0648\u0644\u0627\u0644\u0645\u062e\u0627\u0644\u0641\u0627\u062a"
HEBREW = "\u05e9\u05dc\u05d5\u05dd\u05e2\u05d5\u05dc\u05dd"

RUNS = [
    ("arabic", ARABIC, "\u0600", "\u06ff"),
    ("hebrew", HEBREW, "\u0590", "\u05ff"),
]


def _run_of(text: str, low: str, high: str) -> str:
    return "".join(c for c in text if low <= c <= high)


def _painted(pdf: Path) -> str:
    """Characters in the order the PDF paints them, straight from the source."""

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextContainer

    out: list[str] = []
    for layout in extract_pages(str(pdf)):
        for element in layout:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                for char in getattr(line, "_objs", []):
                    if isinstance(char, LTChar):
                        out.append(char.get_text())
    return "".join(out)


def _extract(path: Path) -> str:
    document = document_extraction.extract_document(
        str(path), PDF_MIME, document_id="CTRL", source_hash="c" * 64
    )
    return "\n".join(e.text for e in document.elements)


class TestTheControlsStillSayWhatTheyClaim:
    """A fixture that stopped containing right-to-left text would pass silently.

    Asserted against the PDF itself and against `unicodedata`, never against the
    parser under test, so this cannot be satisfied by the code agreeing with
    itself.
    """

    @pytest.mark.parametrize(("name", "expected", "low", "high"), RUNS)
    def test_the_logical_control_paints_in_logical_order(
        self, name: str, expected: str, low: str, high: str
    ) -> None:
        painted = _run_of(_painted(LOGICAL_PDF), low, high)
        assert painted, f"the control no longer contains a {name} run"
        assert painted == expected, (
            f"the {name} control is not in logical paint order: {painted!r}"
        )

    @pytest.mark.parametrize(("name", "expected", "low", "high"), RUNS)
    def test_the_visual_control_paints_in_the_opposite_order(
        self, name: str, expected: str, low: str, high: str
    ) -> None:
        painted = _run_of(_painted(VISUAL_PDF), low, high)
        assert painted == expected[::-1], (
            f"the {name} visual control is not the mirror of the logical one"
        )

    def test_the_controls_carry_characters_not_display_glyphs(self) -> None:
        """Otherwise this would be measuring the glyph defect, not order."""

        for pdf in (LOGICAL_PDF, VISUAL_PDF):
            painted = _painted(pdf)
            glyphs = [
                c
                for c in painted
                if unicodedata.decomposition(c).split()[:1]
                and unicodedata.decomposition(c).split()[0]
                in ("<isolated>", "<initial>", "<medial>", "<final>")
            ]
            assert glyphs == [], f"{pdf.name} carries presentation forms: {glyphs[:5]}"

    def test_the_two_controls_are_not_the_same_file(self) -> None:
        assert LOGICAL_PDF.read_bytes() != VISUAL_PDF.read_bytes()


class TestTheDefaultConverterPreservesCorrectText:
    """The property that decides whether the default may change."""

    @pytest.mark.parametrize(("name", "expected", "low", "high"), RUNS)
    def test_text_stored_in_logical_order_survives_extraction(
        self, name: str, expected: str, low: str, high: str
    ) -> None:
        extracted = _run_of(_extract(LOGICAL_PDF), low, high)

        assert extracted != expected[::-1], (
            f"the default converter reversed a {name} run that the source stored "
            f"in logical order: got {extracted!r}, source has {expected!r}. "
            "Text that arrives correct must not be rewritten by extraction."
        )
        assert extracted == expected, (
            f"the default converter altered a {name} run: got {extracted!r}, "
            f"expected {expected!r}"
        )

    def test_the_default_is_the_converter_this_property_was_measured_for(self) -> None:
        """If the default moves, the measurement above has to be redone.

        This is not a claim that the default is the right one - it is a claim
        that changing it is a decision, not an accident.
        """

        assert Settings().document_converter == "legacy"
