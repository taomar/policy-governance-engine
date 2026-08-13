"""One-off remediation script: re-extract clauses for a document version using
the fixed PDF extraction (boilerplate-stripping + word-spacing fix), replacing
the old polluted `Clause` rows and purging/re-uploading the corresponding
Azure Search index entries.

This is a data-fix utility for documents that were uploaded before the
document_extraction.py fix landed — it is NOT a new permanent app feature.
Future uploads never need this, since the fix applies automatically in
routers/documents.py::upload_document.

Usage: python scripts/reextract_document.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from policy_platform.domain.models import DocumentVersion, SourceDocument  # noqa: E402
from policy_platform.infrastructure.ingestion import document_extraction  # noqa: E402
from policy_platform.infrastructure.persistence.db import get_sessionmaker  # noqa: E402
from policy_platform.infrastructure.persistence.repositories import ClauseRepository  # noqa: E402
from policy_platform.infrastructure.search.indexing import index_clauses_best_effort  # noqa: E402
from policy_platform.infrastructure.search.search_client import AzureSearchClient  # noqa: E402
from policy_platform.infrastructure.settings import get_settings  # noqa: E402

TARGET_TITLE = "HR Guide Policy and Procedure Template"


async def main() -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(select(SourceDocument).where(SourceDocument.title == TARGET_TITLE))
        document = result.scalar_one_or_none()
        if document is None:
            print(f"No document titled {TARGET_TITLE!r} found.")
            return

        versions = await session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        doc_versions = list(versions.scalars().all())
        if not doc_versions:
            print("No document versions found.")
            return

        for doc_version in doc_versions:
            print(f"\n=== Re-extracting version {doc_version.version_number} ({doc_version.id}) ===")
            print(f"storage_path={doc_version.storage_path}")

            clause_repo = ClauseRepository(session)
            deleted = await clause_repo.delete_by_document_version(doc_version.id)
            print(f"Deleted {deleted} old (polluted) clause rows.")

            extracted = document_extraction.extract_clauses(doc_version.storage_path, doc_version.mime_type)
            new_clauses = await clause_repo.bulk_create(
                document_version_id=doc_version.id,
                clauses=[
                    {"clause_ref": c.clause_ref, "section": c.section, "page": c.page, "text": c.text}
                    for c in extracted
                ],
            )
            print(f"Created {len(new_clauses)} new (clean) clause rows.")
            await session.commit()

            if settings.search_enabled:
                search_client = AzureSearchClient(settings)
                stale_ids = await search_client.find_ids_by_filter(
                    settings.azure_search_authoring_index,
                    filter_expr=f"document_version eq '{doc_version.id}'",
                )
                print(f"Found {len(stale_ids)} stale index entries for this document version.")
                await search_client.delete_documents(settings.azure_search_authoring_index, stale_ids)
                print("Deleted stale index entries.")

                indexed = await index_clauses_best_effort(
                    document_title=document.title,
                    document_id=str(document.id),
                    document_version_id=str(doc_version.id),
                    version_number=doc_version.version_number,
                    content_hash=doc_version.content_hash,
                    clauses=new_clauses,
                )
                print(f"Re-indexed {indexed} clean clauses into Azure Search.")
            else:
                print("Azure Search not configured; skipped re-indexing.")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
