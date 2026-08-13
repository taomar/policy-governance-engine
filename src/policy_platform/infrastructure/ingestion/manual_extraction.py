"""Manual candidate-rule entry: a stand-in extraction path.

Real AI extraction (Azure OpenAI reading source documents) is deferred (see
ADR-0004 / docs/known-limitations.md). Until that's implemented, a human can
still draft a candidate rule directly and put it through the same
review -> approve -> publish lifecycle the real extraction pipeline will use.

To do that honestly within the existing schema (`CandidateRule.extraction_run_id`
is a required FK to `extraction_runs`, which itself requires a
`document_version_id`), this module lazily creates one singleton
"Manual Candidate Entry" `SourceDocument` / `DocumentVersion` / `ExtractionRun`
chain, reused for every manually-drafted candidate. The `ExtractionRun.status`
is explicitly `"manual_entry"` so it is never confused with a real extraction
run in audit/reporting.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import DocumentVersion, ExtractionRun, SourceDocument

_MANUAL_SOURCE_SYSTEM = "manual_entry"
_MANUAL_DOCUMENT_TITLE = "Manual Candidate Entry"
_MANUAL_CONTENT_HASH = "manual-entry-placeholder"


async def get_or_create_manual_extraction_run(session: AsyncSession) -> ExtractionRun:
    """Return the singleton manual-entry extraction run, creating it if needed."""

    result = await session.execute(
        select(ExtractionRun).where(ExtractionRun.status == "manual_entry").limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    document = SourceDocument(
        title=_MANUAL_DOCUMENT_TITLE,
        source_system=_MANUAL_SOURCE_SYSTEM,
        owner="system",
    )
    session.add(document)
    await session.flush()

    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        content_hash=_MANUAL_CONTENT_HASH,
        storage_path="",
        mime_type="text/plain",
    )
    session.add(version)
    await session.flush()

    run = ExtractionRun(
        document_version_id=version.id,
        status="manual_entry",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()
    return run
