"""One-off backfill: extract clauses + best-effort index into Azure Search
for `DocumentVersion` rows that were uploaded before clause extraction was
wired into the upload endpoint (see infrastructure/document_extraction.py).

Usage (from repo root, with the venv active):
    python scripts/backfill_clause_extraction.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from policy_platform.domain.models import DocumentVersion, SourceDocument  # noqa: E402
from policy_platform.infrastructure import document_extraction  # noqa: E402
from policy_platform.infrastructure.db import get_sessionmaker  # noqa: E402
from policy_platform.infrastructure.repositories import ClauseRepository  # noqa: E402
from policy_platform.infrastructure.search.indexing import index_clauses_best_effort  # noqa: E402


async def main() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(
            select(DocumentVersion).where(DocumentVersion.storage_path != "")
        )
        versions = list(result.scalars().all())
        clause_repo = ClauseRepository(session)

        for version in versions:
            if await clause_repo.has_clauses(version.id):
                print(f"skip {version.storage_path} (already has clauses)")
                continue

            doc_result = await session.execute(
                select(SourceDocument).where(SourceDocument.id == version.document_id)
            )
            document = doc_result.scalar_one()

            try:
                extracted = document_extraction.extract_clauses(version.storage_path, version.mime_type)
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED extraction for {version.storage_path}: {exc}")
                continue

            clauses = await clause_repo.bulk_create(
                document_version_id=version.id,
                clauses=[
                    {"clause_ref": c.clause_ref, "section": c.section, "page": c.page, "text": c.text}
                    for c in extracted
                ],
            )
            await session.commit()
            print(f"extracted {len(clauses)} clauses from {version.storage_path}")

            indexed = await index_clauses_best_effort(
                document_title=document.title,
                document_id=str(document.id),
                document_version_id=str(version.id),
                version_number=version.version_number,
                content_hash=version.content_hash,
                clauses=clauses,
            )
            print(f"indexed {indexed} clauses into Azure Search for {document.title} v{version.version_number}")


if __name__ == "__main__":
    asyncio.run(main())
