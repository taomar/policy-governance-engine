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
from functools import lru_cache
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

def _wrapping(text: str, top: float, size: float, page: int = 0) -> di._Line:
    """A line of running text: it reaches the right-hand edge of the measure."""

    return di._Line(
        text=text, top=top, bottom=top + size, x0=56.0, x1=500.0, size=size, page=page
    )


def _short(text: str, top: float, size: float, page: int = 0) -> di._Line:
    """A line that stops where its words stop, as a heading does."""

    return di._Line(
        text=text, top=top, bottom=top + size, x0=56.0, x1=180.0, size=size, page=page
    )


class TestTheBodyIsABandNotAPoint:
    """A document need not set its running text in one size.

    Asking such a document for a single typical size forces a wrong answer. A
    bilingual document sets each language in its own face and the two are
    co-equal — neither is a heading in the other's terms — but a modal can only
    name one of them. Every line of the other class then measures as "set larger
    than the body" and is read as structure, which is how a document comes to be
    half headings.

    The claim these tests make is that the yardstick spans the running text
    rather than picking one class of it, and — the direction this most easily
    over-reaches — that a class of *headings* never joins the band however many
    of them the document contains.
    """

    def test_two_co_equal_text_classes_are_both_body(self) -> None:
        lines = [_wrapping(f"first class line {i}", i * 14.0, 10.0) for i in range(40)]
        lines += [
            _wrapping(f"second class line {i}", 600.0 + i * 16.0, 12.0)
            for i in range(40)
        ]
        lines += [_short("A Heading", 1400.0, 20.0)]

        smallest, largest = di._body_size_band(lines)

        assert (smallest, largest) == (10.0, 12.0), (
            f"expected the band to span both text classes as [10.0, 12.0], got "
            f"[{smallest}, {largest}]; a band that names one class reads every "
            "line of the other as a heading"
        )

    def test_one_text_class_yields_a_band_of_zero_width(self) -> None:
        """The ordinary document must be unaffected by any of this."""

        lines = [_wrapping(f"body line {i}", i * 14.0, 10.0) for i in range(60)]
        lines += [_short(f"Heading {i}", 900.0 + i * 20.0, 16.0) for i in range(6)]

        smallest, largest = di._body_size_band(lines)

        assert smallest == largest == 10.0, (
            f"expected a single text class to give the modal size as a point, got "
            f"[{smallest}, {largest}]"
        )

    def test_a_class_of_headings_never_joins_the_band(self) -> None:
        """The over-reach control, and the reason frequency alone is not enough.

        Here the larger size is *more* frequent than a tenth of the document, so
        a rule that admitted classes on frequency would let it in — and the band
        would then stretch over the document's own headings and stop recognising
        them. What keeps it out is that its lines do not wrap: running text
        reaches the edge of the measure and continues, where a heading stops
        where its words stop.
        """

        lines = [_wrapping(f"body line {i}", i * 14.0, 10.0) for i in range(60)]
        lines += [_short(f"Heading {i}", 900.0 + i * 20.0, 14.0) for i in range(30)]

        smallest, largest = di._body_size_band(lines)

        assert largest == 10.0, (
            f"expected the heading class at 14.0 to stay outside the band, got "
            f"[{smallest}, {largest}]; a band that swallows a heading class "
            "leaves the document unable to recognise its own structure"
        )

    def test_a_class_that_does_not_wrap_is_excluded_however_frequent(self) -> None:
        """The same claim stated without the word 'heading' anywhere in it."""

        lines = [_wrapping(f"body line {i}", i * 14.0, 10.0) for i in range(50)]
        lines += [_short(f"caption {i}", 800.0 + i * 12.0, 8.0) for i in range(50)]

        smallest, largest = di._body_size_band(lines)

        assert smallest == largest == 10.0, (
            f"expected a non-wrapping class to be excluded whatever its share, "
            f"got [{smallest}, {largest}]"
        )

    def test_an_empty_document_does_not_raise(self) -> None:
        assert di._body_size_band([]) == (0.0, 0.0)


def _running_text_classes(lines: list[di._Line]) -> set[float]:
    """The sizes a document sets running text in, derived here from geometry.

    Computed in the test rather than imported so the claim below is stated in
    the document's terms and not in the implementation's. A size counts as
    running text when it carries a real share of the lines and those lines wrap
    — reaching the edge of the measure and continuing — which is what separates
    prose from a label without knowing anything about the words.
    """

    live = [line for line in lines if line.text.strip()]
    if not live:
        return set()
    widths = sorted(line.x1 - line.x0 for line in live)
    measure = widths[min(int(len(widths) * 0.9), len(widths) - 1)]
    if measure <= 0:
        return set()

    totals: Counter[float] = Counter(round(line.size, 1) for line in live)
    wrapping: Counter[float] = Counter(
        round(line.size, 1)
        for line in live
        if (line.x1 - line.x0) >= measure * 0.9
    )
    return {
        size
        for size, count in totals.items()
        if count >= len(live) * 0.1 and wrapping[size] >= count * 0.15
    }


class TestRunningTextIsNotReadAsStructure:
    """The claim above, made against a document rather than a construction.

    Font metrics cannot be synthesised convincingly, so the mechanism tests
    above are built by hand and this one reads a real file. It asserts nothing
    true only of that file: the claim is that whatever sizes a document sets its
    running text in, no one of them is read as structure.
    """

    @pytest.fixture(scope="class")
    def lines(self) -> list[di._Line]:
        candidates = sorted(_PAGINATED_PDF.parent.glob("*AIS_Employee_Handbook*.pdf"))
        if not candidates:
            pytest.skip("no multi-class fixture available")
        collected: list[di._Line] = []
        with di.pdfplumber.open(candidates[0]) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                collected.extend(di._read_page(page, index)[0])
        return collected

    def test_the_fixture_sets_running_text_in_more_than_one_size(
        self, lines: list[di._Line]
    ) -> None:
        """Absence of evidence and evidence of absence must not render alike.

        The claim below is vacuous on a document with one text class, and one
        text class is the common case. So the fixture is asked to prove it can
        exercise the claim before the claim is made.
        """

        classes = _running_text_classes(lines)

        assert len(classes) > 1, (
            f"the fixture sets running text in {sorted(classes)}, a single class, "
            "so it cannot exercise the claim that a document may have several; "
            "the test below would pass without testing anything"
        )

    def test_no_class_of_running_text_is_predominantly_headings(
        self, lines: list[di._Line]
    ) -> None:
        """A size the document writes prose in is not a size it labels with.

        The threshold is a majority rather than a tuned figure: whatever else is
        true of a class the document sets running text in, it cannot be mostly
        labels.
        """

        classes = _running_text_classes(lines)
        smallest, largest = di._body_size_band(lines)

        by_page: dict[int, list[di._Line]] = {}
        for line in lines:
            by_page.setdefault(line.page, []).append(line)

        headings: Counter[float] = Counter()
        totals: Counter[float] = Counter()
        for page_lines in by_page.values():
            kinds = di._classify_lines(
                page_lines, largest, smallest_body_size=smallest
            )
            for line, kind in zip(page_lines, kinds):
                size = round(line.size, 1)
                if not line.text.strip() or size not in classes:
                    continue
                totals[size] += 1
                if kind == "heading":
                    headings[size] += 1

        assert totals, "no running text was examined, so nothing was asserted"

        overtaken = {
            size: f"{headings[size]} of {totals[size]}"
            for size in sorted(totals)
            if headings[size] * 2 > totals[size]
        }
        assert not overtaken, (
            f"these running-text sizes are mostly typed as headings: {overtaken}. "
            "A whole class of the document's prose is being read as structure, "
            "which is what a single typical size does to a document that sets "
            "text in more than one"
        )


_SENTENCE_END = (".", "!", "?", "\u061f", "\u3002")


def _available_documents() -> list[Path]:
    """Every document on disk this file can reach, without naming any of them.

    The claim below is a property of ingestion, not of a chosen file, so it is
    asked of whatever is present. Adding a document to the corpus extends the
    guard; none of them is a target.
    """

    roots = [
        _PAGINATED_PDF.parent,
        Path(__file__).resolve().parents[2] / "samples" / "source-documents",
    ]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(sorted(root.glob("*.pdf")))
    return found


@lru_cache(maxsize=None)
def _ingest_once(path: str) -> object:
    """Ingest a document at most once per session; ingestion is not cheap."""

    return di.ingest_document(path, Path(path).name)


class TestASentenceIsNotAHeading:
    """A heading names what follows it. A sentence says something itself.

    This is the harm the yardstick does where it can be seen from outside the
    module. A document that sets running text in two sizes has no single typical
    size, and against the smaller of them every line of the larger reads as
    set-larger-than-usual — so whole sentences are filed as headings. They then
    become the section every following record is attributed to, and a reader is
    shown a sentence in place of the heading it sat under.

    The signal is structural, not lexical: the document itself terminates the
    line. A label that ends in an abbreviation would be reported here, which is
    a stated limit rather than a hidden one; across the corpus none does.
    """

    @pytest.mark.parametrize(
        "document_path", _available_documents(), ids=lambda p: p.stem[:40]
    )
    def test_no_heading_is_a_finished_sentence(self, document_path: Path) -> None:
        document = _ingest_once(str(document_path))

        headings = [
            element.text.strip()
            for element in document.elements
            if element.element_type == "heading" and element.text.strip()
        ]
        if not headings:
            pytest.skip("no headings were found, so nothing is asserted")

        offenders = [text for text in headings if text.endswith(_SENTENCE_END)]

        assert not offenders, (
            f"{len(offenders)} of {len(headings)} headings are finished "
            f"sentences, for example {offenders[0][:90]!r}. Prose has been read "
            "as structure, and each of these becomes the section that the "
            "records after it are filed under"
        )





def _begins_mid_sentence(text: str) -> bool:
    """Whether the first cased character is lowercase.

    Defined here rather than imported so the claim below is expressed in terms
    of the document, not of the implementation that satisfies it. Read from
    Unicode character properties, so a script without case answers False and
    contributes nothing rather than a wrong answer.
    """

    for char in text.strip():
        if char.isupper():
            return False
        if char.islower():
            return True
    return False


class TestAHeadingIsNeverAContinuation:
    """A heading begins something, so it is never the tail of what precedes it.

    This guards the opposite failure to the two above: over-promotion. Where a
    paragraph line is typed `heading`, the damage compounds rather than staying
    local. Blocks are broken at a heading and never merged across one, so the
    sentence is cut and the halves can never be rejoined; and a heading carries
    no section, because a heading *is* a section rather than being *in* one. The
    tail therefore loses both the clause that gave its references an antecedent
    and the heading it sat under, and arrives at review as a fragment that reads
    as meaningless.

    Whether a line is a heading is decided by whether the document sets it
    apart, which it can do by size, by space or by case. All three are read from
    page geometry and Unicode character properties, so the claims below hold for
    any script: in one that marks no case, the case signal simply abstains and
    the others decide.

    Both directions are asserted. A rule that demotes every short line would
    pass a test that only contains orphans, so genuine headings that happen to
    follow an unterminated line are asserted to survive.

    The document read here is a different witness from the one used above,
    chosen because it exhibits the structure under test: it mixes two co-equal
    text sizes, which is the condition under which a size-based classifier
    promotes body lines. A document that never produces an orphan cannot show
    that orphans are handled, and asserting the claim against one would pass
    without exercising anything.
    """

    @pytest.fixture(scope="class")
    def document(self):
        candidates = sorted(
            (_PAGINATED_PDF.parent).glob("*AIS_Employee_Handbook*.pdf")
        )
        if not candidates:
            pytest.skip("no mixed-size document available to exercise the claim")
        source = candidates[0]
        return ingest_document(str(source), source.name)

    def test_a_sentence_tail_set_like_its_paragraph_is_not_a_heading(self) -> None:
        """The mechanism: no size change, no extra space, no case change."""

        lines = [
            _line("A member of staff who is absent on that day must", 100.0),
            _line("notify the department in writing.", 114.0),
        ]
        kinds = di._classify_lines(lines, 12.0)
        assert kinds[1] == "paragraph", (
            f"expected the tail of a sentence to be a paragraph, got {kinds[1]!r}; "
            "a line set exactly like the line it continues is not a heading"
        )

    def test_a_heading_set_larger_survives_an_unterminated_predecessor(self) -> None:
        """The control against over-reach, in the direction this fix risks.

        A predecessor without terminal punctuation is weak evidence on its own —
        headings routinely follow other headings, captions and table cells. A
        line the document sets larger is a heading whatever precedes it.
        """

        lines = [
            _line("A table cell with no closing punctuation", 100.0, size=12.0),
            _line("Leave And Absence", 130.0, size=16.0),
        ]
        kinds = di._classify_lines(lines, 12.0)
        assert kinds[1] == "heading", (
            f"expected a line set larger than its predecessor to stay a heading, "
            f"got {kinds[1]!r}; demoting it loses a real section"
        )

    def test_a_heading_set_apart_by_space_survives(self) -> None:
        """Space is the second way a document sets a heading apart."""

        tight = [
            _line("An opening line with no closing punctuation", 100.0, size=12.0),
            _line("Another line of the same paragraph", 114.0, size=12.0),
            _line("A Heading After A Paragraph Break", 128.0, size=12.0),
        ]
        assert di._classify_lines(tight, 10.0)[2] == "paragraph"

        spaced = [
            _line("An opening line with no closing punctuation", 100.0, size=12.0),
            _line("Another line of the same paragraph", 114.0, size=12.0),
            _line("A Heading After A Paragraph Break", 190.0, size=12.0),
        ]
        kinds = di._classify_lines(spaced, 10.0)
        assert kinds[2] == "heading", (
            f"expected a line separated by more than the running leading to stay a "
            f"heading, got {kinds[2]!r}; the same words differing only in the white "
            "space above them must classify differently"
        )

    def test_a_heading_set_apart_by_case_survives_at_body_size(self) -> None:
        """Case is the third, and the only one left for a marker at body size.

        A section marker set at body size and tight against the line above it is
        still a heading if it is the only capitalised thing on the page.
        """

        lines = [
            _line("Holiday entitlement 13", 100.0),
            _line("SECTION 2", 114.0),
        ]
        kinds = di._classify_lines(lines, 12.0)
        assert kinds[1] == "heading", (
            f"expected an all-capital marker to stay a heading, got {kinds[1]!r}; "
            "case is the only signal left once size and space are unavailable"
        )

    def test_no_heading_is_a_full_width_line_of_prose(self, document) -> None:
        """The product-level claim, asserted over a real document.

        A line that begins mid-sentence and runs the full width of the column is
        prose, whatever size it is set in. Both halves are needed: a short line
        beginning lowercase may be the second line of a heading that wrapped,
        which is a different thing and is left alone. Both are read from Unicode
        character properties and page geometry, so a script without case
        contributes nothing here rather than a wrong answer.
        """

        headings = [el for el in document.elements if el.element_type == "heading"]
        assert headings, "no heading was examined, so this asserts nothing"

        prose_typed_as_headings = [
            el.text.strip()[:70]
            for el in headings
            if _begins_mid_sentence(el.text) and len(el.text.strip()) > 70
        ]
        assert not prose_typed_as_headings, (
            f"{len(prose_typed_as_headings)} of {len(headings)} headings are "
            "full-width lines that begin mid-sentence, so each is the tail of a "
            f"paragraph the classifier cut in half: {prose_typed_as_headings[:2]}"
        )

    def test_a_wrapped_heading_keeps_its_second_line(self) -> None:
        """The control in the direction this rule most easily over-reaches.

        A heading that runs onto a second line leaves that line carrying none of
        the three signals: same size, same leading, and it begins mid-phrase.
        Demoting it merges a real heading into the body and a section
        disappears. What distinguishes it from a paragraph tail is that it stops
        short of the measure — a heading does not fill the column.
        """

        lines = [
            _line("Occupational Health", 100.0, size=12.0),
            di._Line(
                text="and Safety Regulations",
                top=114.0,
                bottom=126.0,
                x0=56.0,
                x1=180.0,
                size=12.0,
                page=0,
            ),
            di._Line(
                text="The regulation sets out the duties owed by every employer to",
                top=140.0,
                bottom=152.0,
                x0=56.0,
                x1=500.0,
                size=10.0,
                page=0,
            ),
        ]
        kinds = di._classify_lines(lines, 10.0)
        assert kinds[1] == "heading", (
            f"expected the second line of a wrapped heading to stay a heading, got "
            f"{kinds[1]!r}; demoting it merges the heading into the body and the "
            "section it names disappears"
        )

    def test_a_full_width_tail_is_demoted_even_after_a_heading(self) -> None:
        """The same shape, but running the full measure, is prose.

        This is the pair to the test above: identical signals except width, so a
        pass on both shows the width is doing the work rather than something
        incidental to the wording.
        """

        lines = [
            _line("Occupational Health", 100.0, size=12.0),
            di._Line(
                text="and safety obligations apply to every employer in the sector",
                top=114.0,
                bottom=126.0,
                x0=56.0,
                x1=500.0,
                size=12.0,
                page=0,
            ),
            di._Line(
                text="The regulation sets out the duties owed by every employer to",
                top=128.0,
                bottom=140.0,
                x0=56.0,
                x1=500.0,
                size=12.0,
                page=0,
            ),
        ]
        kinds = di._classify_lines(lines, 10.0)
        assert kinds[1] == "paragraph", (
            f"expected a full-width line beginning mid-sentence to be a paragraph, "
            f"got {kinds[1]!r}; a line that fills the measure is prose whatever "
            "precedes it"
        )

    def test_the_fixture_still_exercises_the_claim(self, document) -> None:
        """Absence of evidence and evidence of absence must not render alike.

        Every assertion above is satisfied vacuously by a document with no
        headings and no prose. Asserting the volume examined is what makes a
        pass mean the claim held rather than that nothing was looked at.
        """

        headings = [el for el in document.elements if el.element_type == "heading"]
        prose = [el for el in document.elements if el.element_type == "paragraph"]
        assert len(headings) > 10, (
            f"only {len(headings)} headings in the fixture; the claims above would "
            "pass without exercising anything"
        )
        assert len(prose) > 10, (
            f"only {len(prose)} paragraphs in the fixture; a document with no prose "
            "cannot produce an orphaned sentence tail to catch"
        )
