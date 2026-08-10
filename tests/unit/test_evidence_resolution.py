"""Tests for pointer-only evidence resolution and coverage accounting.

The property being protected is that evidence text is *copied by the
application*, never accepted from a model. These tests therefore concentrate on
the ways a resolver could appear to work while quietly weakening that: accepting
a locator that does not resolve, attributing a cross-page span to one page, or
defaulting an unconsidered element into a coverage class.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.evidence_resolution import (
    EvidencePointer,
    build_coverage_report,
    resolve_evidence,
)
from policy_platform.contracts.structural_graph import build_structural_graph


def _document(texts: list[tuple[str, str]]) -> CanonicalDocument:
    """Build a one-page document from (element_id, text) pairs."""

    elements: list[CanonicalElement] = []
    parts: list[str] = []
    cursor = 0
    for index, (element_id, text) in enumerate(texts):
        start, end = cursor, cursor + len(text)
        elements.append(
            CanonicalElement(
                element_id=element_id,
                element_type="paragraph",
                logical_order=index,
                text=text,
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
        parser="docling",
    )


class TestApplicationCopiesText:
    def test_whole_element_resolves_to_its_exact_text(self) -> None:
        document = _document([("E1", "Employees must apply in writing.")])
        result = resolve_evidence(document, [EvidencePointer(element_id="E1")])

        assert result.ok
        assert result.resolved[0].exact_text == "Employees must apply in writing."

    def test_partial_span_cites_a_sentence_without_quoting_it(self) -> None:
        document = _document([("E1", "Employees must apply. Managers approve.")])
        result = resolve_evidence(
            document, [EvidencePointer(element_id="E1", start_offset=22, end_offset=38)]
        )

        assert result.ok
        assert result.resolved[0].exact_text == "Managers approve."[:16]

    def test_resolved_offsets_slice_back_from_the_page(self) -> None:
        """The locator must survive a restart without re-running extraction."""

        document = _document([("E1", "First clause."), ("E2", "Second clause here.")])
        result = resolve_evidence(document, [EvidencePointer(element_id="E2")])
        span = result.resolved[0]
        page_text = document.page_text(span.page)

        assert page_text[span.page_start_offset : span.page_end_offset] == span.exact_text

    def test_evidence_hash_covers_position_not_just_text(self) -> None:
        """The same sentence can legitimately appear twice in a document."""

        document = _document([("E1", "Approval is required."), ("E2", "Approval is required.")])
        result = resolve_evidence(
            document,
            [EvidencePointer(element_id="E1"), EvidencePointer(element_id="E2")],
        )

        assert result.resolved[0].exact_text == result.resolved[1].exact_text
        assert result.resolved[0].evidence_hash != result.resolved[1].evidence_hash


class TestRejection:
    def test_unknown_element_is_rejected(self) -> None:
        document = _document([("E1", "A clause.")])
        result = resolve_evidence(document, [EvidencePointer(element_id="E404")])

        assert not result.ok
        assert result.rejected[0].code == "unknown_element"

    def test_offsets_past_the_element_are_rejected(self) -> None:
        document = _document([("E1", "Short.")])
        result = resolve_evidence(
            document, [EvidencePointer(element_id="E1", start_offset=0, end_offset=999)]
        )

        assert result.rejected[0].code == "offset_out_of_range"

    @pytest.mark.parametrize(
        ("start", "end", "code"),
        [(5, 2, "inverted_range"), (3, 3, "empty_span")],
    )
    def test_degenerate_ranges_are_rejected(self, start: int, end: int, code: str) -> None:
        document = _document([("E1", "A clause of some length.")])
        result = resolve_evidence(
            document, [EvidencePointer(element_id="E1", start_offset=start, end_offset=end)]
        )

        assert result.rejected[0].code == code

    def test_a_shifted_locator_is_rejected_rather_than_trusted(self) -> None:
        """The check the whole design rests on.

        The fragment still has the right length, so it passes the range checks
        and reaches the text comparison — which is the guarantee that matters:
        a locator pointing at the wrong characters is caught, not trusted.
        """

        document = _document([("E1", "Employees must apply."), ("E2", "Second clause.")])
        fragment = document.elements[0].source_fragments[0]
        fragment.start_offset += 2
        fragment.end_offset += 2

        result = resolve_evidence(document, [EvidencePointer(element_id="E1")])

        assert not result.ok
        assert result.rejected[0].code == "text_mismatch"

    def test_a_truncated_locator_is_also_rejected(self) -> None:
        """A different corruption, caught earlier by the range check."""

        document = _document([("E1", "Employees must apply.")])
        document.elements[0].source_fragments[0].start_offset = 5

        result = resolve_evidence(document, [EvidencePointer(element_id="E1")])

        assert not result.ok
        assert result.rejected[0].code == "offset_out_of_range"

    def test_one_bad_pointer_does_not_discard_valid_evidence(self) -> None:
        """A single mislocated citation must not lose a rule's other spans."""

        document = _document([("E1", "First clause."), ("E2", "Second clause.")])
        result = resolve_evidence(
            document,
            [
                EvidencePointer(element_id="E1"),
                EvidencePointer(element_id="E404"),
                EvidencePointer(element_id="E2"),
            ],
        )

        assert len(result.resolved) == 2
        assert len(result.rejected) == 1

    def test_span_crossing_a_page_boundary_is_rejected(self) -> None:
        """A citation pointing at the wrong page is worse than a missing one."""

        element = CanonicalElement(
            element_id="E1",
            element_type="paragraph",
            logical_order=0,
            text="Employees may take leave provided the manager approves.",
            source_fragments=[
                SourceFragment(
                    page=1, start_offset=0, end_offset=25, text="Employees may take leave "
                ),
                SourceFragment(
                    page=2, start_offset=0, end_offset=30, text="provided the manager approves."
                ),
            ],
        )
        document = CanonicalDocument(
            document_id="DOC",
            page_count=2,
            pages=[
                CanonicalPage(page=1, raw_text="Employees may take leave "),
                CanonicalPage(page=2, raw_text="provided the manager approves."),
            ],
            elements=[element],
            parser="docling",
        )
        result = resolve_evidence(document, [EvidencePointer(element_id="E1")])

        assert not result.ok
        assert result.rejected[0].code == "offset_out_of_range"


class TestNonContiguousEvidence:
    def test_spans_are_kept_separate_with_their_roles(self) -> None:
        """Concatenation would manufacture prose that is nowhere in the document."""

        document = _document(
            [
                ("E1", "An Eligible Employee may request leave."),
                ("E2", '"Eligible Employee" means an employee of 12 months.'),
                ("E3", "This does not apply during probation."),
            ]
        )
        result = resolve_evidence(
            document,
            [
                EvidencePointer(element_id="E1", role="target"),
                EvidencePointer(element_id="E2", role="definition"),
                EvidencePointer(element_id="E3", role="exception"),
            ],
        )

        assert result.ok
        assert len(result.resolved) == 3
        assert len(result.by_role("target")) == 1
        assert len(result.by_role("definition")) == 1
        assert result.by_role("exception")[0].exact_text.startswith("This does not apply")

    def test_spans_group_by_candidate(self) -> None:
        document = _document([("E1", "A clause."), ("E2", "Its exception.")])
        result = resolve_evidence(
            document,
            [
                EvidencePointer(element_id="E1", role="target", candidate_key="2.1"),
                EvidencePointer(element_id="E2", role="exception", candidate_key="2.1"),
            ],
        )

        assert {e.candidate_key for e in result.resolved} == {"2.1"}


class TestCoverage:
    def _plan_inputs(self, texts: list[tuple[str, str]]):
        document = _document(texts)
        return document, build_structural_graph(document)

    def test_supplied_dispositions_are_recorded(self) -> None:
        document, graph = self._plan_inputs([("E1", "A clause."), ("E2", "Another clause.")])
        report = build_coverage_report(
            document,
            graph,
            {
                "E1": ("policy_target", "states an obligation"),
                "E2": ("supporting_context", "explains E1"),
            },
        )

        assert report.is_complete
        assert report.accounted == 2

    def test_an_unconsidered_element_is_reported_not_defaulted(self) -> None:
        """Defaulting turns content nobody looked at into content that looks classified."""

        document, graph = self._plan_inputs([("E1", "A clause."), ("E2", "Another clause.")])
        report = build_coverage_report(document, graph, {"E1": ("policy_target", "obligation")})

        assert not report.is_complete
        assert report.unaccounted_element_ids == ["E2"]

    def test_furniture_is_dispositioned_automatically(self) -> None:
        """'This is a page header' is an answer, and requiring callers to
        enumerate furniture would make omission likely."""

        document = _document([("E1", "A clause.")])
        document.elements.append(
            CanonicalElement(
                element_id="F1",
                element_type="furniture",
                logical_order=1,
                text="Confidential",
                source_fragments=[
                    SourceFragment(page=1, start_offset=0, end_offset=12, text="Confidential")
                ],
            )
        )
        graph = build_structural_graph(document)
        report = build_coverage_report(document, graph, {"E1": ("policy_target", "obligation")})

        assert report.is_complete
        furniture = next(e for e in report.elements if e.element_id == "F1")
        assert furniture.disposition == "non_normative"

    def test_unresolved_is_distinct_from_unaccounted(self) -> None:
        """One is an honest 'could not classify'; the other is silent loss."""

        document, graph = self._plan_inputs([("E1", "A clause."), ("E2", "Ambiguous text.")])
        report = build_coverage_report(
            document,
            graph,
            {
                "E1": ("policy_target", "obligation"),
                "E2": ("unresolved", "cannot tell if normative"),
            },
        )

        assert report.unaccounted_element_ids == []
        assert report.unresolved == 1
        assert not report.is_complete

    def test_every_leaf_appears_exactly_once(self) -> None:
        document, graph = self._plan_inputs(
            [("E1", "One."), ("E2", "Two."), ("E3", "Three.")]
        )
        report = build_coverage_report(
            document, graph, {e: ("policy_target", "obligation") for e in ("E1", "E2", "E3")}
        )
        ids = [e.element_id for e in report.elements]

        assert sorted(ids) == ["E1", "E2", "E3"]
        assert len(ids) == len(set(ids))
        assert report.total_leaf_elements == 3
