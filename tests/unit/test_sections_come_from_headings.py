"""Records must carry the heading they sit under, and never page furniture.

A policy read without its heading loses the context that makes it mean
anything, so every record carries a `section`. That makes the *correctness* of
the section the thing worth guarding, not its presence: a field that is
populated but wrong is worse than one that is empty, because an empty field
invites a question and a wrong one invites trust. A reviewer shown a section
believes it.

Two structural mistakes produce a section that is populated and wrong, and they
fail in opposite directions, so both are guarded here:

* Under-suppression — running page furniture (a footer, a page number, a
  standing title) is read as a heading and becomes the section for everything
  printed after it. Coverage then measures as complete while naming something
  that is not a section at all.
* Over-suppression — furniture detection widens until it swallows genuine
  headings, and real sections disappear. This is the failure a fix for the
  first one invites, so it is asserted directly rather than assumed.

The claims below are expressed against structure, never against the wording,
numbering, layout or language of any particular document. The PDF used as a
vehicle is a witness, not a target: it supplies real font encodings and page
geometry, which cannot be synthesised faithfully, but nothing here is asserted
of it that would not be asserted of any paginated document.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from policy_platform.infrastructure.ingestion import document_ingestion as di
from policy_platform.infrastructure.ingestion.document_ingestion import ingest_document

_PAGINATED_PDF = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "documents"
    / "aa098d99-a26b-4f19-bb35-162336932938_v1_STAFF-HANDBOOK-GMU-2024.pdf"
)


def _line(text: str, top: float, *, size: float = 12.0, height: float = 12.0) -> di._Line:
    return di._Line(
        text=text,
        top=top,
        bottom=top + height,
        x0=56.0,
        x1=500.0,
        size=size,
        page=0,
    )


class TestFurnitureBandIsFoundBySeparation:
    """The page-edge band is bounded by white space, not by a line count.

    Running furniture is whatever the page sets apart at its edge. A footer
    carrying a standing title, a page number and a document name is three
    lines; a bare page number is one. Measuring the band in lines therefore
    sees all of a short footer and only the last line of a tall one, and the
    remainder is left to be classified as content.
    """

    def test_a_multi_line_band_is_seen_whole(self) -> None:
        body = [_line(f"body line {i}", 60.0 + i * 14.0) for i in range(20)]
        footer = [
            _line("standing title", 660.0, size=6.0, height=6.0),
            _line("7", 663.5, size=7.0, height=7.0),
            _line("document name", 667.0, size=6.0, height=6.0),
        ]

        band = di._edge_lines(body + footer)
        band_text = {line.text for line in band}

        assert {line.text for line in footer} <= band_text, (
            "every line of a set-apart edge band must be offered to furniture "
            f"detection; band was {sorted(band_text)}"
        )

    def test_a_band_that_is_not_set_apart_does_not_widen(self) -> None:
        """The control against over-suppression.

        A page whose text runs evenly to the margin has no furniture band. If
        the walk widened here it would hand real content — including a section
        heading that happens to sit at the top of a page — to the furniture
        detector, and a document whose genuine headings recur would lose them.
        """

        evenly_set = [_line(f"body line {i}", 60.0 + i * 14.0) for i in range(20)]

        band = di._edge_lines(evenly_set)

        assert len(band) == 2, (
            "with no white space setting an edge apart, only the outermost line "
            f"of each edge is a furniture candidate; got {len(band)}: "
            f"{[line.text for line in band]}"
        )
        assert {band[0].text, band[1].text} == {"body line 0", "body line 19"}


class TestSmallPrintIsNotAHeading:
    """The weak all-caps rule needs a size floor, and the floor needs a margin.

    Both directions are asserted, because the fix for one invites the other.
    """

    def test_type_set_below_the_body_is_not_a_heading(self) -> None:
        """Under-suppression: small-print furniture must not become a heading.

        A running footer, a watermark, a copyright line or a column label set
        in small capitals satisfies "looks like a label" on text alone. Nothing
        set smaller than the text it would introduce is a section heading, and
        without this floor such a line becomes the section for every record
        printed after it on every page it appears on.
        """

        small = _line("A STANDING FOOTER", 680.0, size=6.0, height=6.0)
        assert di._classify_line(small, body_size=12.0) != "heading"

    def test_a_heading_set_at_body_size_survives(self) -> None:
        """Over-suppression: the floor must not demote genuine headings.

        Plenty of documents distinguish a heading by weight, spacing or case
        rather than by size, so a real section heading is often set at exactly
        body size — and measured size carries floating-point noise, so "exactly"
        can read as a hair under. A floor without a margin therefore deletes
        real sections, which is the more expensive direction: a heading lost is
        context lost from every record beneath it.
        """

        at_body = _line("SECTION 1", 120.0, size=10.0 - 1e-6)
        assert di._classify_line(at_body, body_size=10.0) == "heading"


@pytest.mark.skipif(not _PAGINATED_PDF.exists(), reason="paginated fixture not present")
class TestSectionsComeFromHeadingsNotFurniture:
    @pytest.fixture(scope="class")
    def document(self):
        return ingest_document(str(_PAGINATED_PDF), _PAGINATED_PDF.name)

    def test_the_fixture_still_exercises_the_claim(self, document) -> None:
        """Assert the volume examined, so an empty scan cannot pass silently.

        A scan that reports what it found without reporting what it looked at
        renders absence-of-evidence and evidence-of-absence identically. If
        this fixture ever stops being a multi-page document that carries
        headings, the assertions below would hold vacuously.
        """

        assert len(document.pages) >= 10, "fixture must be long enough to repeat furniture"
        headings = [el for el in document.elements if el.element_type == "heading"]
        assert len(headings) >= 10, f"fixture must carry headings; found {len(headings)}"
        sections = {el.section for el in document.elements if el.section}
        assert len(sections) >= 10, f"fixture must yield sections; found {len(sections)}"

    def test_no_section_is_repeating_page_furniture(self, document) -> None:
        """Text the page repeats at its edge is furniture, and is never a section.

        Furniture is *marked* rather than deleted, so it remains auditable on
        the page it came from; what it must not do is become the heading under
        which unrelated records are filed.
        """

        furniture = Counter()
        for page in document.pages:
            for entry in page.removed_boilerplate or []:
                furniture[di._normalize_line(entry)] += 1
        recurring = {text for text, count in furniture.items() if count >= 3}
        assert recurring, "fixture must contain recurring furniture for this to mean anything"

        offenders = sorted(
            {
                el.section
                for el in document.elements
                if el.section and di._normalize_line(el.section) in recurring
            }
        )
        assert not offenders, (
            "records are filed under page furniture rather than a heading: " f"{offenders}"
        )

    def test_sections_are_not_dominated_by_one_label(self, document) -> None:
        """A single label owning nearly every record is the signature of the defect.

        When furniture is read as a heading it becomes the section for every
        element printed after it, on every page it appears on, so one label
        accumulates almost the whole document. Real sections divide a document;
        they do not monopolise it. The threshold is deliberately loose — this
        asserts that the document is divided at all, not that it is divided in
        any particular way.
        """

        filed = [el for el in document.elements if el.section]
        assert filed, "no record carries a section"
        label, count = Counter(el.section for el in filed).most_common(1)[0]
        share = count / len(filed)
        assert share < 0.5, (
            f"{share:.1%} of records are filed under a single label {label!r}; "
            "a section that owns the document is furniture, not a heading"
        )

    def test_an_enumerated_heading_is_still_a_heading(self, document) -> None:
        """A document that numbers its sections still has sections.

        What separates an enumerated list item from an enumerated heading is
        how the document sets it, not how it is numbered: a heading is set
        larger than the content it introduces, while an item in a list is set
        like its siblings. Deciding on the marker alone calls every numbered
        heading a list item, and a list item is merged into the text that
        follows it — so the title and its opening paragraph fuse, and the
        boundaries between numbered sections are destroyed together.
        """

        enumerated = [
            el
            for el in document.elements
            if el.element_type == "heading" and di._LIST_MARKER_RE.match(el.text.strip())
        ]
        assert enumerated, (
            "no enumerated line survives as a heading, so every numbered section "
            "boundary has been merged into the following paragraph"
        )

        sections = {el.section for el in document.elements if el.section}
        enumerated_sections = {
            text for text in sections if di._LIST_MARKER_RE.match(text.strip())
        }
        assert enumerated_sections, (
            "no record is filed under an enumerated heading, so numbered sections "
            "exist in the document but not on its records"
        )
