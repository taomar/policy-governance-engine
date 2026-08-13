"""The invariant: text is persisted in logical (reading) order, not paint order.

A PDF records where each glyph was *painted*. For a left-to-right script that
is also the order the words were written in, so the distinction never surfaces.
For a run written in a right-to-left script the two orders differ, and storing
the paint order stores text the document does not contain — while still looking
like well-formed prose, so nothing downstream can flag it.

These tests assert the invariant rather than any one document's wording:

* the transformation must be a pure permutation of the parser's own glyphs, so
  nothing can be invented, dropped, or rewritten to make text look right;
* every number must survive with its digits in the source's order, which is
  what rules out "repairing" a line by reversing it — reversal turns 50 into
  05, and in a document of penalty rates the quantities are the content;
* a document with no right-to-left run must come out byte for byte unchanged.

Two of them use a real bilingual PDF, because font encodings and glyph
coordinates cannot be synthesised — a hand-built fixture would be a fixture of
this test's own assumptions. What the tests must never do is take today's
output as the specification, so every expected string below was read off the
rendered source page by eye and written down before it was compared to
anything. A fixture derived from current output would enshrine whatever
corruption current output has.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

from policy_platform.infrastructure.ingestion.document_ingestion import ingest_document
from policy_platform.infrastructure.ingestion.reading_order import (
    has_rtl,
    normalize_presentation_forms,
)

DOCUMENTS = Path(__file__).resolve().parents[2] / "data" / "documents"
SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "source-documents"

#: A PDF that paints right-to-left runs, with numbers embedded inside them.
BILINGUAL = DOCUMENTS / "d2997cd6-7534-4de0-8c87-5cbdf8a3a900_v1_AIS_Employee_Handbook-1.pdf"
#: A PDF with no right-to-left character anywhere, for the no-change guarantee.
LTR_ONLY = SAMPLES / "HR-Guide-Policy-and-Procedure-Template.pdf"

#: Read off the rendered source page by eye, not copied from any output. Each
#: is a continuous passage of the document, and each is stored here in the
#: order a reader of the source reads it.
#:
#: The first carries an embedded left-to-right number, "(15)", inside a
#: right-to-left sentence: the digits, the parentheses and the sentence around
#: them each have to end up in their own correct order for it to match.
SOURCE_PASSAGES = (
    "التأخر عن مواعيد الحضور للعمل لغاية (15) دقيقة دون إذن أو عذر مقبول،"
    " إذا لم يترتب على ذلك تعطيل عمال آخرين.",
    "مقبول، إذا لم يترتب على ذلك تعطيل عمال",
    "جداول المخالفات والجزاءات",
    "الجزاء (النسبة المحسوبة من الأجر اليومي)",
)


def _persisted_text(document) -> str:
    """Everything the ingestion persisted, page text and element text alike."""

    return "\n".join(
        [page.raw_text for page in document.pages]
        + [element.text for element in document.elements]
    )


def _paint_order_text(document) -> str:
    """The parser's own output, in the order the pages paint it."""

    return "\n".join(
        page.visual_order_raw_text or page.raw_text for page in document.pages
    )


@pytest.fixture(scope="module")
def bilingual():
    if not BILINGUAL.exists():
        pytest.fail(
            f"the bilingual fixture is missing at {BILINGUAL}. This test cannot be "
            "skipped quietly: with no fixture there is nothing to detect, and a "
            "silent skip reads exactly like a pass."
        )
    return ingest_document(BILINGUAL, document_id="rtl-guard")


def test_the_fixture_actually_contains_right_to_left_runs(bilingual):
    """Assert the volume examined, not only what was found.

    A scan that reports what it found without reporting what it looked at makes
    "there was nothing wrong" and "there was nothing to look at" render
    identically. If this fixture ever stops carrying right-to-left text, every
    other test in this file would pass without exercising anything, so the
    absence has to be a failure in its own right.
    """

    text = _persisted_text(bilingual)
    rtl_characters = sum(1 for char in text if unicodedata.bidirectional(char) in ("R", "AL"))
    assert has_rtl(text), (
        "expected the fixture to contain right-to-left text; found none. "
        "The reading-order tests below would then be asserting nothing."
    )
    assert rtl_characters > 100, (
        f"expected the fixture to carry a substantial right-to-left passage; "
        f"found only {rtl_characters} right-to-left characters."
    )


def test_text_painted_in_visual_order_is_persisted_in_logical_order(bilingual):
    """Passages must be stored as the source reads, not as the page paints."""

    text = _persisted_text(bilingual)
    missing = [passage for passage in SOURCE_PASSAGES if passage not in text]
    assert not missing, (
        "these passages of the source are not present in the persisted text, "
        "which means the text was stored in some order other than the one the "
        "document is written in.\n"
        + "\n".join(f"  expected to find: {passage!r}" for passage in missing)
    )


def test_numbers_inside_right_to_left_runs_keep_the_source_digit_order(bilingual):
    """A number is a left-to-right run wherever it appears.

    This is the test that rules out repairing a line by reversing it. Reversal
    makes the prose look corrected while silently turning every 50 into an 05,
    and in a schedule of penalty rates those quantities are the operative
    content. Stated as a general property so it holds for any document: putting
    a page into reading order rearranges runs, so it must never alter the
    digits within any one number.
    """

    painted = Counter(re.findall(r"\d+", normalize_presentation_forms(_paint_order_text(bilingual))))
    persisted = Counter(re.findall(r"\d+", "\n".join(page.raw_text for page in bilingual.pages)))

    assert painted, "no numbers found in the fixture; this test would assert nothing"
    assert persisted == painted, (
        "the numbers changed when the text was put into reading order. Digits "
        "run left to right inside a right-to-left passage, so reordering must "
        "leave each number intact.\n"
        f"  expected (as painted): {sorted(painted.elements())}\n"
        f"  actual  (as stored)  : {sorted(persisted.elements())}\n"
        f"  lost: {sorted((painted - persisted).elements())}\n"
        f"  invented: {sorted((persisted - painted).elements())}"
    )


def test_reading_order_only_rearranges_and_never_rewrites(bilingual):
    """Whatever is stored must be the parser's own glyphs, merely reordered.

    Recovering reading order is a decoding step. It may move characters and it
    may decode a positional glyph variant back to the letter it is a variant
    of, but it may not introduce a character that was never on the page. This
    holds the fix to rearranging what was extracted rather than producing text
    from anywhere else.
    """

    for page in bilingual.pages:
        if page.visual_order_raw_text is None:
            continue
        painted = Counter(normalize_presentation_forms(page.visual_order_raw_text))
        stored = Counter(page.raw_text)
        invented = stored - painted
        lost = painted - stored
        assert not invented and not lost, (
            f"page {page.page}: reading order changed which characters are present, "
            "not merely their order.\n"
            f"  invented: {sorted(invented.elements())}\n"
            f"  lost: {sorted(lost.elements())}"
        )


def test_a_document_with_no_right_to_left_run_is_left_exactly_as_it_was():
    """No right-to-left run means nothing to recover, so nothing may change."""

    if not LTR_ONLY.exists():
        pytest.fail(f"the left-to-right fixture is missing at {LTR_ONLY}")
    document = ingest_document(LTR_ONLY, document_id="ltr-guard")

    assert document.pages, "fixture produced no pages; this test would assert nothing"
    text = _persisted_text(document)
    assert not has_rtl(text), (
        "this fixture is meant to contain no right-to-left text; it now does, so "
        "it can no longer stand for the leave-it-alone case."
    )
    changed = [page.page for page in document.pages if page.visual_order_raw_text is not None]
    assert not changed, (
        "pages with no right-to-left run were rewritten by the reading-order "
        f"step; it must be a no-op for them. Pages affected: {changed}"
    )
