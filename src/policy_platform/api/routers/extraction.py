"""Extraction-side read access: canonical documents, structure, stages, coverage.

Deliberately narrow. Everything a reviewer *does* — approve, reject, request
changes, publish, activate — already has endpoints, and the integration
directive forbids a second set. This router adds only what those surfaces cannot
currently answer: what the converter produced, how the document is structured,
how the run progressed, and what happened to every element.

Read-only by construction. There is no POST here and there should not be one:
extraction is started through the existing document and candidate-rule flows,
and an endpoint that could mutate a canonical artifact would break the one
guarantee the artifact exists to provide.

Conversion is intentionally *not* exposed as a live call. A 53-page PDF takes
roughly three minutes to convert, which no HTTP client will wait for, and an
endpoint that quietly re-converts on every request would also produce a new
artifact behind spans already stored against the old one.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.reading_plan import build_reading_plan
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.domain.models import Clause, DocumentVersion
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.extraction_stage_repository import (
    ExtractionStageRepository,
)

router = APIRouter(prefix="/api/extraction", tags=["extraction"])

#: Ceiling on elements returned in one call. A 53-page PDF yields ~780 elements
#: and a large handbook considerably more, so an unbounded response is a way to
#: hang a browser by accident.
_MAX_ELEMENTS = 2000


async def _load_version(session: AsyncSession, document_version_id: uuid.UUID) -> DocumentVersion:
    version = await session.get(DocumentVersion, document_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"document version {document_version_id} not found")
    return version


async def _load_clauses(session: AsyncSession, document_version_id: uuid.UUID) -> list[Clause]:
    result = await session.execute(
        select(Clause)
        .where(Clause.document_version_id == document_version_id)
        .order_by(Clause.sequence)
    )
    return list(result.scalars().all())


def _canonical_from_clauses(document_id: str, clauses: list[Clause]):
    """Rebuild a canonical document from the persisted clauses.

    Rebuilt rather than re-converted. Re-running Docling would take minutes and,
    worse, could produce a *different* artifact from the one whose offsets are
    already stored — so every span a reviewer is looking at would silently stop
    referring to what produced it.
    """

    from policy_platform.contracts.canonical_document import (
        CanonicalDocument,
        CanonicalElement,
        CanonicalPage,
        SourceFragment,
    )

    elements: list[CanonicalElement] = []
    pages: dict[int, list[str]] = {}

    for index, clause in enumerate(clauses):
        fragments = [
            SourceFragment(**{k: v for k, v in fragment.items() if k in
                              {"page", "start_offset", "end_offset", "text"}})
            for fragment in (clause.source_fragments or [])
        ]
        elements.append(
            CanonicalElement(
                element_id=clause.element_id or f"E{index:06d}",
                element_type=clause.element_type or "paragraph",  # type: ignore[arg-type]
                logical_order=clause.sequence,
                text=clause.text,
                section=clause.section,
                source_fragments=fragments,
            )
        )
        for fragment in fragments:
            pages.setdefault(fragment.page, [])

    return CanonicalDocument(
        document_id=document_id,
        page_count=len(pages) or 1,
        pages=[CanonicalPage(page=page, raw_text="") for page in sorted(pages)] or
        [CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="persisted",
    )


@router.get("/{document_version_id}/canonical")
async def get_canonical_document(
    document_version_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=_MAX_ELEMENTS),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The canonical elements of one document version, in reading order."""

    await _load_version(session, document_version_id)
    clauses = await _load_clauses(session, document_version_id)
    window = clauses[offset : offset + limit]

    return {
        "document_version_id": str(document_version_id),
        "total_elements": len(clauses),
        "offset": offset,
        "elements": [
            {
                "element_id": clause.element_id,
                "element_type": clause.element_type,
                "sequence": clause.sequence,
                "section": clause.section,
                "page": clause.page,
                "clause_ref": clause.clause_ref,
                "text": clause.text,
                "source_fragments": clause.source_fragments or [],
            }
            for clause in window
        ],
    }


@router.get("/{document_version_id}/structure")
async def get_structural_graph(
    document_version_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The deterministic structural graph for one document version.

    Recomputed on request rather than stored. It is a pure function of the
    canonical elements, so storing it would create a second copy that can
    disagree with them — and recomputation is cheap next to the conversion that
    produced the elements in the first place.
    """

    await _load_version(session, document_version_id)
    clauses = await _load_clauses(session, document_version_id)
    document = _canonical_from_clauses(str(document_version_id), clauses)
    graph = build_structural_graph(document)

    return {
        "document_version_id": str(document_version_id),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "leaf_element_ids": graph.leaf_element_ids,
        "nodes": [
            {
                "element_id": node.element_id,
                "element_type": node.element_type,
                "reading_order": node.reading_order,
                "section": node.section,
                "page": node.page,
            }
            for node in graph.reading_order()
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "kind": edge.kind}
            for edge in graph.edges
        ],
    }


@router.get("/{document_version_id}/reading-plan")
async def get_reading_plan(
    document_version_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The graph-aware context units extraction would read.

    Exposed because "why did the model see this text alongside that rule" is the
    first question a reviewer asks about a wrong extraction, and the dependency
    reasons are the answer.
    """

    await _load_version(session, document_version_id)
    clauses = await _load_clauses(session, document_version_id)
    document = _canonical_from_clauses(str(document_version_id), clauses)
    graph = build_structural_graph(document)
    plan = build_reading_plan(document, graph)

    return {
        "document_version_id": str(document_version_id),
        "unit_count": len(plan.units),
        "is_exhaustive": plan.is_exhaustive,
        "uncovered_target_ids": plan.uncovered_target_ids,
        "units": [
            {
                "unit_id": unit.unit_id,
                "heading_path": unit.heading_path,
                "target_element_ids": unit.target_element_ids,
                "context": [
                    {"element_id": entry.element_id, "reason": entry.reason,
                     "is_candidate": entry.is_candidate}
                    for entry in unit.context
                ],
            }
            for unit in plan.units
        ],
    }


@router.get("/{document_version_id}/stages")
async def list_extraction_stages(
    document_version_id: uuid.UUID,
    idempotency_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Recorded stages for this document's extraction runs.

    Without `idempotency_key` this returns every run's stages, which is what an
    operator asking "has this document ever been extracted, and how did it go"
    needs — a single run's view requires already knowing its key.
    """

    await _load_version(session, document_version_id)

    if idempotency_key:
        stages = await ExtractionStageRepository(session).list_for_run(idempotency_key)
    else:
        from policy_platform.domain.models import ExtractionStage

        result = await session.execute(
            select(ExtractionStage)
            .where(ExtractionStage.document_version_id == document_version_id)
            .order_by(ExtractionStage.idempotency_key, ExtractionStage.sequence)
        )
        stages = list(result.scalars().all())

    return {
        "document_version_id": str(document_version_id),
        "stages": [
            {
                "idempotency_key": stage.idempotency_key,
                "stage_name": stage.stage_name,
                "sequence": stage.sequence,
                "status": stage.status,
                "attempt": stage.attempt,
                "detail": stage.detail,
                "duration_seconds": stage.duration_seconds,
                "input_hash": stage.input_hash,
                "output_hash": stage.output_hash,
            }
            for stage in stages
        ],
    }


@router.get("/{document_version_id}/coverage")
async def get_coverage(
    document_version_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Coverage disposition for every canonical leaf of this version.

    Derived from the reading plan rather than from a stored report, so it stays
    truthful when clauses change. Elements in no unit are returned as
    `unaccounted` rather than defaulted to a class, because that distinction is
    the entire point of the coverage gate.
    """

    await _load_version(session, document_version_id)
    clauses = await _load_clauses(session, document_version_id)
    document = _canonical_from_clauses(str(document_version_id), clauses)
    graph = build_structural_graph(document)
    plan = build_reading_plan(document, graph)

    from policy_platform.contracts.evidence_resolution import build_coverage_report
    from policy_platform.infrastructure.docling.pipeline import _dispositions_from_plan

    report = build_coverage_report(
        document, graph, _dispositions_from_plan(plan, [], document, graph)
    )

    return {
        "document_version_id": str(document_version_id),
        "total_leaf_elements": report.total_leaf_elements,
        "accounted": report.accounted,
        "unresolved": report.unresolved,
        "unaccounted_element_ids": report.unaccounted_element_ids,
        "is_complete": report.is_complete,
        "elements": [
            {
                "element_id": entry.element_id,
                "disposition": entry.disposition,
                "reason": entry.reason,
            }
            for entry in report.elements
        ],
    }
