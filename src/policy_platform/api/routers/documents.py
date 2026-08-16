"""Document upload endpoints.

Persists the uploaded file to local disk under `./data/documents/`, records
`SourceDocument`/`DocumentVersion` rows, then synchronously extracts the
document's text into `Clause` rows (see `infrastructure/ingestion/document_extraction.py`)
and best-effort indexes those clauses into Azure AI Search so Ask-AI chat and
AI rule extraction have real grounding text to work with. Azure Blob Storage
for raw file persistence remains deferred — see docs/known-limitations.md.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.api.schemas import (
    AssignDocumentRequest,
    ClauseResponse,
    SourceDocumentResponse,
    ingestion_status_of,
)
from policy_platform.domain.models import DocumentVersion, SourceDocument
from policy_platform.infrastructure.ingestion import document_extraction
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.persistence.repositories import ClauseRepository, PolicySetRepository
from policy_platform.infrastructure.search.indexing import clause_search_document_id, index_clauses_best_effort
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

_STORAGE_ROOT = Path("data") / "documents"


def _to_response(document: SourceDocument) -> SourceDocumentResponse:
    policy_set = document.policy_set
    return SourceDocumentResponse(
        id=str(document.id),
        title=document.title,
        owner=document.owner,
        source_system=document.source_system,
        created_at=document.created_at,
        versions=[
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "content_hash": v.content_hash,
                "storage_path": v.storage_path,
                "mime_type": v.mime_type,
                "created_at": v.created_at,
                # Carried on every list of versions, not behind a detail
                # fetch. A reviewer deciding which document to trust is
                # looking at the list, and a problem that only appears
                # once you already suspect one is not a warning.
                "ingestion_diagnostics": v.ingestion_diagnostics_json or [],
                "ingestion_error": v.ingestion_error,
                "ingestion_status": ingestion_status_of(
                    v.ingestion_diagnostics_json, v.ingestion_error
                ),
            }
            for v in document.versions
        ],
        policy_set_id=str(document.policy_set_id) if document.policy_set_id else None,
        policy_set_key=policy_set.key if policy_set else None,
        policy_set_name=policy_set.name if policy_set else None,
    )


@router.get("", response_model=list[SourceDocumentResponse])
async def list_documents(
    policy_set_key: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[SourceDocumentResponse]:
    """List documents, optionally scoped to one project (policy set).

    Omitting `policy_set_key` returns every document across all projects plus
    any unassigned ones — this is what powers the global "Document Inbox".
    """
    stmt = (
        select(SourceDocument)
        .options(selectinload(SourceDocument.versions), selectinload(SourceDocument.policy_set))
        .order_by(SourceDocument.created_at)
    )
    if policy_set_key is not None:
        policy_set_repo = PolicySetRepository(session)
        policy_set = await policy_set_repo.get_by_key(policy_set_key)
        if policy_set is None:
            raise HTTPException(status_code=404, detail=f"policy set '{policy_set_key}' not found")
        stmt = stmt.where(SourceDocument.policy_set_id == policy_set.id)
    result = await session.execute(stmt)
    documents = result.scalars().unique().all()
    return [_to_response(d) for d in documents]


@router.post("/upload")
async def upload_document(
    title: str,
    owner: str,
    file: UploadFile,
    policy_set_key: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    policy_set_id = None
    if policy_set_key is not None:
        policy_set_repo = PolicySetRepository(session)
        policy_set = await policy_set_repo.get_by_key(policy_set_key)
        if policy_set is None:
            raise HTTPException(status_code=404, detail=f"policy set '{policy_set_key}' not found")
        policy_set_id = policy_set.id

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    # Scope the "does this document already exist" lookup by project too:
    # two different projects each uploading a "Handbook.pdf" are two distinct
    # documents, not versions of the same one. Unassigned uploads (no project)
    # only match other unassigned documents with the same title.
    existing_doc_stmt = select(SourceDocument).where(SourceDocument.title == title)
    if policy_set_id is not None:
        existing_doc_stmt = existing_doc_stmt.where(SourceDocument.policy_set_id == policy_set_id)
    else:
        existing_doc_stmt = existing_doc_stmt.where(SourceDocument.policy_set_id.is_(None))
    result = await session.execute(existing_doc_stmt)
    document = result.scalar_one_or_none()
    if document is None:
        document = SourceDocument(title=title, owner=owner, source_system="manual_upload", policy_set_id=policy_set_id)
        session.add(document)
        await session.flush()

    existing = await session.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id, DocumentVersion.content_hash == content_hash
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="identical document content already uploaded")

    # "new content", "content the register already holds under another name",
    # and "refused" are three different facts, and only the third has a signal
    # today (the 409 above, for an identical re-upload of THIS document). The
    # same bytes filed under a different title -- or owner, or project -- are a
    # legitimate second registration: an archived snapshot of a handbook, a
    # re-parse under a new parser, one source serving two projects. Refusing
    # those would remove a capability the register is actively using, so the
    # upload proceeds. But a plain success reports this second fact as the
    # first, leaving whoever maintains a compliance register unaware it now
    # holds the same source twice -- a silent accept. So the other
    # registrations of these exact bytes are gathered and returned with the
    # success, scoped away from this document's own (not-yet-created) version.
    #
    # The empty list is load-bearing and distinct from absence: it says this
    # lookup ran and found no other copy (the content is new to the register),
    # not that the question went unasked -- the same []-vs-None distinction the
    # ingestion diagnostics keep below.
    other_copies_result = await session.execute(
        select(
            SourceDocument.id,
            SourceDocument.title,
            SourceDocument.owner,
            DocumentVersion.id,
            DocumentVersion.version_number,
        )
        .join(DocumentVersion, DocumentVersion.document_id == SourceDocument.id)
        .where(
            DocumentVersion.content_hash == content_hash,
            SourceDocument.id != document.id,
        )
        .order_by(SourceDocument.created_at, DocumentVersion.version_number)
    )
    content_already_present = [
        {
            "document_id": str(other_document_id),
            "title": other_title,
            "owner": other_owner,
            "document_version_id": str(other_version_id),
            "version_number": other_version_number,
        }
        for (
            other_document_id,
            other_title,
            other_owner,
            other_version_id,
            other_version_number,
        ) in other_copies_result.all()
    ]

    version_count = await session.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    )
    version_number = len(list(version_count.scalars().all())) + 1

    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    storage_path = _STORAGE_ROOT / f"{document.id}_v{version_number}_{file.filename}"
    storage_path.write_bytes(content)

    doc_version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        content_hash=content_hash,
        storage_path=str(storage_path),
        mime_type=file.content_type or "application/octet-stream",
    )
    session.add(doc_version)
    await session.flush()

    clause_count = 0
    extraction_error: str | None = None
    ingestion_diagnostics: list[dict] = []
    try:
        canonical = document_extraction.extract_document(
            str(storage_path),
            doc_version.mime_type,
            # Element ids are namespaced by the source hash so the same sentence
            # in two documents never collides, and the canonical document is
            # labelled with the row it belongs to rather than a filename stem.
            document_id=str(document.id),
            source_hash=content_hash,
        )
        extracted = document_extraction.clauses_from_document(canonical)
        # Surface parse problems (scanned pages, unreadable pages, coverage
        # loss) to the caller. Reporting zero clauses without saying why lets a
        # scanned PDF look like an empty policy document, which spec section 55
        # invariant 9 forbids.
        ingestion_diagnostics = [
            d.model_dump() for d in document_extraction.ingestion_warnings(canonical)
        ]
        # Appended rather than routed through ingestion_warnings, which keeps
        # only warning and error. This one is deliberately info: it says the
        # evidence for an element shares its character range with a neighbour,
        # which is a property of the source, not a defect in the document. It
        # is reported at the point both converter paths converge so neither
        # parser has to carry its own copy of the rule.
        ingestion_diagnostics.extend(
            d.model_dump() for d in canonical.shared_span_diagnostics()
        )
        clause_repo = ClauseRepository(session)
        clauses = await clause_repo.bulk_create(
            document_version_id=doc_version.id,
            clauses=[
                {
                    "clause_ref": c.clause_ref,
                    "section": c.section,
                    "page": c.page,
                    "text": c.text,
                    "element_id": c.element_id,
                    "element_type": c.element_type,
                    "source_fragments": c.source_fragments,
                    "table_id": c.table_id,
                    "table_headers": c.table_headers,
                }
                for c in extracted
            ],
        )
        clause_count = len(clauses)
    except Exception as exc:  # noqa: BLE001 - extraction failure shouldn't block the upload
        extraction_error = str(exc)
        logger.warning("clause extraction failed for %s: %s", storage_path, exc)
        clauses = []

    # Persist what we just learned about this ingestion, in the same
    # transaction as the version and its clauses. Until this existed the
    # diagnostics reached exactly one person -- whoever ran the upload -- and
    # were unrecoverable afterwards, so no reviewer or auditor could later
    # discover that a document's source did not fully resolve. Committing the
    # version and dropping the reason it is thin is the storage-layer form of
    # the thing spec section 55 invariant 9 forbids.
    #
    # `[]` and `None` are kept distinct on purpose: an empty list means this
    # ingestion ran and had nothing to report, NULL means nothing was recorded.
    doc_version.ingestion_diagnostics_json = ingestion_diagnostics
    doc_version.ingestion_error = extraction_error

    await session.commit()

    indexed_count = 0
    if clauses:
        indexed_count = await index_clauses_best_effort(
            document_title=document.title,
            document_id=str(document.id),
            document_version_id=str(doc_version.id),
            version_number=version_number,
            content_hash=content_hash,
            clauses=clauses,
        )

    return {
        "document_id": str(document.id),
        "document_version_id": str(doc_version.id),
        "version_number": version_number,
        "content_hash": content_hash,
        "storage_path": str(storage_path),
        "clause_count": clause_count,
        "clauses_indexed": indexed_count,
        "extraction_error": extraction_error,
        "ingestion_diagnostics": ingestion_diagnostics,
        # Same derivation the list view uses, so the sentence the uploader sees
        # and the marker a reviewer sees later cannot disagree about the same
        # ingestion.
        "ingestion_status": ingestion_status_of(ingestion_diagnostics, extraction_error),
        # The other registrations that already hold these exact bytes, under a
        # different title/owner/project. An empty list is a positive answer --
        # "checked, this content is new to the register" -- and is distinct
        # from the field being absent. A non-empty list means the upload
        # succeeded AND the register already held this source elsewhere, so a
        # second registration cannot pass for new content in silence.
        "content_already_present": content_already_present,
    }


@router.get("/{document_version_id}/clauses", response_model=list[ClauseResponse])
async def list_document_clauses(
    document_version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ClauseResponse]:
    clause_repo = ClauseRepository(session)
    clauses = await clause_repo.list_by_document_version(document_version_id)
    settings = get_settings()
    return [
        ClauseResponse(
            id=str(c.id),
            document_version_id=str(c.document_version_id),
            clause_ref=c.clause_ref,
            section=c.section,
            page=c.page,
            text=c.text,
            sequence=c.sequence,
            element_id=c.element_id,
            element_type=c.element_type,
            search_document_id=clause_search_document_id(str(c.document_version_id), str(c.id)),
            search_index=settings.azure_search_authoring_index,
        )
        for c in clauses
    ]


@router.patch("/{document_id}/assign", response_model=SourceDocumentResponse)
async def assign_document_to_project(
    document_id: uuid.UUID,
    body: AssignDocumentRequest,
    session: AsyncSession = Depends(get_session),
) -> SourceDocumentResponse:
    """File an existing document into a project, or un-assign it (`policy_set_key: null`).

    Lets documents uploaded through the global Document Inbox (or uploaded
    before this project link existed) be organized into a project after the
    fact, without re-uploading the file.
    """
    stmt = (
        select(SourceDocument)
        .options(selectinload(SourceDocument.versions), selectinload(SourceDocument.policy_set))
        .where(SourceDocument.id == document_id)
    )
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail=f"document '{document_id}' not found")

    if body.policy_set_key is None:
        document.policy_set_id = None
    else:
        policy_set_repo = PolicySetRepository(session)
        policy_set = await policy_set_repo.get_by_key(body.policy_set_key)
        if policy_set is None:
            raise HTTPException(status_code=404, detail=f"policy set '{body.policy_set_key}' not found")
        document.policy_set_id = policy_set.id

    await session.commit()
    await session.refresh(document, attribute_names=["policy_set"])
    return _to_response(document)
