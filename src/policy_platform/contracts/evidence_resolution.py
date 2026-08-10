"""Pointer-only evidence selection and deterministic span resolution.

THE GUARANTEE
-------------
A model selecting evidence returns **pointers only**: element ids, offsets,
and a role. It never returns text. The application then copies the characters
out of the canonical artifact itself and verifies the copy::

    canonical_raw_text[start:end] == evidence.exact_text

This is strictly stronger than instructing a model to quote verbatim and
checking afterwards. Text a model never emits cannot be fabricated, so the
failure mode "the quote looks right but does not appear in the document" is
eliminated by construction rather than by detection.

When a locator does not resolve, the span is **rejected**. The model is never
asked to correct or re-quote it: a model that has already mislocated a span has
no better information the second time, and accepting a repaired quote would
reintroduce exactly the fabrication risk the design removes.

NON-CONTIGUOUS EVIDENCE
-----------------------
One evaluable rule routinely needs a target clause, a definition, a table
header, a row value, and an exception — from five different places. Each span is
preserved separately with its semantic role rather than concatenated into a
single passage. Concatenation would manufacture prose that appears nowhere in
the document, which is the same defect as the legacy table flattening.

COVERAGE
--------
Every canonical leaf receives exactly one disposition. That is what turns "we
extracted the policies" into a checkable claim: an element with no disposition
was never considered, which is silent loss, and is distinguished from an element
deliberately marked ``unresolved``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.canonical_document import CanonicalDocument
from policy_platform.contracts.graph_run import (
    CoverageDisposition,
    CoverageReport,
    ElementCoverage,
)
from policy_platform.contracts.structural_graph import StructuralGraph

#: What a span contributes to a rule. Roles are kept because a reviewer must be
#: able to tell the clause that *states* an obligation from the definition that
#: merely explains a word in it.
EvidenceRole = Literal[
    "target",
    "context",
    "definition",
    "exception",
    "approval",
    "condition",
    "table_header",
    "table_row",
    "footnote",
    "cross_reference",
]

#: Why a selected span could not be used.
RejectionCode = Literal[
    "unknown_element",
    "offset_out_of_range",
    "inverted_range",
    "empty_span",
    "text_mismatch",
]


class EvidencePointer(BaseModel):
    """What a model is permitted to return: a location, never text.

    ``start_offset``/``end_offset`` are optional and element-relative. Omitting
    them selects the whole element, which is the common case; supplying them
    allows a single sentence to be cited out of a long paragraph without
    quoting it.
    """

    model_config = ConfigDict(extra="ignore")

    element_id: str
    role: EvidenceRole = "target"
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    candidate_key: str | None = Field(
        default=None, description="Candidate this span supports, for grouping."
    )


class ResolvedEvidence(BaseModel):
    """A span the application resolved and verified against the canonical text."""

    model_config = ConfigDict(extra="ignore")

    element_id: str
    role: EvidenceRole
    exact_text: str = Field(description="Copied by the application, never by a model.")
    page: int
    #: Absolute offsets into that page's ``raw_text``, so the span re-resolves
    #: after a process restart without re-running extraction.
    page_start_offset: int
    page_end_offset: int
    element_start_offset: int
    element_end_offset: int
    candidate_key: str | None = None
    #: Hash over the resolved text and its locator together. Text alone is not
    #: enough: the same sentence can legitimately appear twice in a document, and
    #: position is what distinguishes the two occurrences.
    evidence_hash: str = ""


class RejectedEvidence(BaseModel):
    """A pointer that did not resolve, kept so the loss stays visible."""

    model_config = ConfigDict(extra="ignore")

    element_id: str
    role: EvidenceRole
    code: RejectionCode
    detail: str = ""


class EvidenceResolution(BaseModel):
    """The outcome of resolving one set of pointers."""

    model_config = ConfigDict(extra="ignore")

    resolved: list[ResolvedEvidence] = Field(default_factory=list)
    rejected: list[RejectedEvidence] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected

    def by_role(self, role: EvidenceRole) -> list[ResolvedEvidence]:
        return [e for e in self.resolved if e.role == role]


def resolve_evidence(
    document: CanonicalDocument, pointers: list[EvidencePointer]
) -> EvidenceResolution:
    """Copy and verify the text for each pointer.

    Each pointer is resolved independently: one bad locator rejects its own span
    and nothing else, so a single mislocated citation cannot discard the valid
    evidence gathered for the same rule.
    """

    by_id = {element.element_id: element for element in document.elements}
    resolution = EvidenceResolution()

    for pointer in pointers:
        element = by_id.get(pointer.element_id)
        if element is None:
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="unknown_element",
                    detail="no such element in the canonical document",
                )
            )
            continue

        start = pointer.start_offset if pointer.start_offset is not None else 0
        end = pointer.end_offset if pointer.end_offset is not None else len(element.text)

        if start >= end:
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="inverted_range" if start > end else "empty_span",
                    detail=f"start {start} is not before end {end}",
                )
            )
            continue

        if end > len(element.text):
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="offset_out_of_range",
                    detail=f"end {end} exceeds element length {len(element.text)}",
                )
            )
            continue

        # The application copies here. The model's own characters, if it ever
        # sent any, are not consulted.
        exact_text = element.text[start:end]

        fragment = _fragment_covering(element, start, end)
        if fragment is None:
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="offset_out_of_range",
                    detail="span crosses a page boundary and has no single source fragment",
                )
            )
            continue

        fragment_offset = _fragment_start_within_element(element, fragment)
        page_start = fragment.start_offset + (start - fragment_offset)
        page_end = page_start + (end - start)

        try:
            page_text = document.page_text(fragment.page)
        except KeyError:
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="unknown_element",
                    detail=f"page {fragment.page} missing from the canonical document",
                )
            )
            continue

        # The check the whole design rests on.
        if page_text[page_start:page_end] != exact_text:
            resolution.rejected.append(
                RejectedEvidence(
                    element_id=pointer.element_id,
                    role=pointer.role,
                    code="text_mismatch",
                    detail="resolved locator does not slice back to the element text",
                )
            )
            continue

        resolution.resolved.append(
            ResolvedEvidence(
                element_id=element.element_id,
                role=pointer.role,
                exact_text=exact_text,
                page=fragment.page,
                page_start_offset=page_start,
                page_end_offset=page_end,
                element_start_offset=start,
                element_end_offset=end,
                candidate_key=pointer.candidate_key,
                evidence_hash=canonical_hash(
                    {
                        "document_id": document.document_id,
                        "element_id": element.element_id,
                        "page": fragment.page,
                        "start": page_start,
                        "end": page_end,
                        "text": exact_text,
                    }
                ),
            )
        )

    return resolution


def _fragment_covering(element, start: int, end: int):
    """Find the source fragment containing an element-relative range.

    An element may span pages, in which case its text is the concatenation of
    several fragments. A span that crosses that boundary has no single page
    locator, so it is rejected rather than being attributed to one page — a
    citation pointing at the wrong page is worse than a missing one.
    """

    cursor = 0
    for fragment in element.source_fragments:
        length = fragment.end_offset - fragment.start_offset
        if start >= cursor and end <= cursor + length:
            return fragment
        cursor += length
    return None


def _fragment_start_within_element(element, target) -> int:
    cursor = 0
    for fragment in element.source_fragments:
        if fragment is target:
            return cursor
        cursor += fragment.end_offset - fragment.start_offset
    return 0


def build_coverage_report(
    document: CanonicalDocument,
    graph: StructuralGraph,
    dispositions: dict[str, tuple[CoverageDisposition, str]],
) -> CoverageReport:
    """Account for every canonical leaf exactly once.

    `dispositions` maps element id to (disposition, reason). Leaves absent from
    it are reported as *unaccounted* rather than being defaulted to anything:
    defaulting would convert content nobody considered into content that looks
    deliberately classified, which is the silent loss this report exists to
    expose.

    Non-normative elements are given a disposition automatically, because
    "this is a page header" is a genuine answer rather than a gap, and requiring
    a caller to enumerate furniture would make omission likely.
    """

    leaves = graph.leaf_element_ids
    by_id = {element.element_id: element for element in document.elements}

    entries: list[ElementCoverage] = []
    unaccounted: list[str] = []

    for element_id in leaves:
        supplied = dispositions.get(element_id)
        if supplied is not None:
            disposition, reason = supplied
            entries.append(
                ElementCoverage(element_id=element_id, disposition=disposition, reason=reason)
            )
            continue

        element = by_id.get(element_id)
        if element is not None and element.is_non_normative:
            entries.append(
                ElementCoverage(
                    element_id=element_id,
                    disposition="non_normative",
                    reason=f"{element.element_type} carries no policy statement",
                )
            )
            continue

        unaccounted.append(element_id)

    return CoverageReport(
        total_leaf_elements=len(leaves),
        elements=entries,
        unaccounted_element_ids=unaccounted,
    )
