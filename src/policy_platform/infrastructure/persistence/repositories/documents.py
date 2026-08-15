"""Source material: the clauses a rule cites and the evidence linking them.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    Clause,
    EvidenceReference,
)

class ClauseRepository:
    """Access to extracted document text chunks (populated by document_extraction)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, *, document_version_id: uuid.UUID, clauses: list[dict]) -> list[Clause]:
        rows = [
            Clause(
                document_version_id=document_version_id,
                clause_ref=c["clause_ref"],
                section=c.get("section"),
                page=c.get("page"),
                text=c["text"],
                sequence=idx,
                element_id=c.get("element_id"),
                element_type=c.get("element_type"),
                source_fragments=c.get("source_fragments"),
                # `.get` rather than `["..."]` so a caller that predates these
                # columns still writes rows; it stores NULL, which is what is
                # true of a clause whose writer never knew its table.
                table_id=c.get("table_id"),
                table_headers=c.get("table_headers"),
            )
            for idx, c in enumerate(clauses)
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def list_by_document_version(self, document_version_id: uuid.UUID) -> list[Clause]:
        result = await self._session.execute(
            select(Clause).where(Clause.document_version_id == document_version_id).order_by(Clause.sequence)
        )
        return list(result.scalars().all())

    async def has_clauses(self, document_version_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(Clause.id).where(Clause.document_version_id == document_version_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_ids(self, clause_ids: list[uuid.UUID]) -> list[Clause]:
        """Batch-fetch clauses by id — used to resolve a rule's evidence[] back to verbatim
        source text without an N+1 round trip per evidence entry."""

        if not clause_ids:
            return []
        result = await self._session.execute(select(Clause).where(Clause.id.in_(clause_ids)))
        return list(result.scalars().all())

    async def delete_by_document_version(self, document_version_id: uuid.UUID) -> int:
        """Remove all clauses for a document version (e.g. before re-extraction after
        an extraction-quality fix). Returns the number of rows deleted."""

        existing = await self.list_by_document_version(document_version_id)
        for clause in existing:
            await self._session.delete(clause)
        await self._session.flush()
        return len(existing)


class EvidenceReferenceRepository:
    """Access to persisted rule -> source-clause lineage rows.

    Populated at publish time (see policy_version_import.py) from each
    published rule's `CanonicalRule.evidence`; without this the source-clause
    linkage a reviewer saw on the candidate is silently lost the moment the
    rule is approved and published.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, *, rule_id: uuid.UUID, evidence: list[dict]) -> list[EvidenceReference]:
        if not evidence:
            return []
        rows = [
            EvidenceReference(
                rule_id=rule_id,
                document_version_id=uuid.UUID(ev["document_version_id"]),
                clause_id=uuid.UUID(ev["clause_id"]) if ev.get("clause_id") else None,
                source_hash=ev["source_hash"],
                page=ev.get("page"),
                section=ev.get("section"),
                start_offset=ev.get("start_offset"),
                end_offset=ev.get("end_offset"),
            )
            for ev in evidence
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows
