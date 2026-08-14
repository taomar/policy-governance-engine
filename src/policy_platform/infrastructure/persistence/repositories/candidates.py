"""The review pipeline: an extraction run, the candidates it proposes, and
the quality runs that assess them before anyone approves.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    CandidateRule,
    DocumentVersion,
    ExtractionRun,
    QualityRun,
)

class CandidateRuleRepository:
    """Access to non-authoritative candidate rules going through human review.

    Unlike `ApprovedPolicyVersionRepository`, updates in place are expected
    here (`review_status`, `reviewed_by`, etc.) — a candidate is explicitly
    not yet authoritative, so this is not a Rule 5.3 violation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        extraction_run_id: uuid.UUID,
        rule_type: str,
        payload_json: dict,
        revision: int = 1,
    ) -> CandidateRule:
        candidate = CandidateRule(
            policy_set_id=policy_set_id,
            extraction_run_id=extraction_run_id,
            rule_type=rule_type,
            payload_json=payload_json,
            revision=revision,
            review_status="candidate",
        )
        self._session.add(candidate)
        await self._session.flush()
        return candidate

    async def list_by_policy_set(
        self,
        policy_set_id: uuid.UUID,
        *,
        review_status: str | None = None,
        document_id: uuid.UUID | None = None,
        document_version_id: uuid.UUID | None = None,
        extraction_run_id: uuid.UUID | None = None,
        delta_status: str | None = None,
        include_superseded: bool = False,
    ) -> list[CandidateRule]:
        """Candidate rules for a policy set, current generation by default.

        `include_superseded` exists for exactly one caller shape: looking at a
        historical extraction run on purpose. Every other read means "the rules
        in play right now", so superseded rows — the previous extraction of a
        re-extracted document, retained for delta comparison — are excluded
        unless asked for. Defaulting the other way would silently double the
        review queue the first time anyone re-ran a document.
        """

        stmt = select(CandidateRule).where(CandidateRule.policy_set_id == policy_set_id)
        if not include_superseded:
            stmt = stmt.where(CandidateRule.superseded_at.is_(None))
        if review_status is not None:
            stmt = stmt.where(CandidateRule.review_status == review_status)
        if extraction_run_id is not None:
            stmt = stmt.where(CandidateRule.extraction_run_id == extraction_run_id)
        if delta_status is not None:
            stmt = stmt.where(CandidateRule.delta_status == delta_status)
        if document_version_id is not None or document_id is not None:
            # Joined rather than filtered on the payload's evidence, because a
            # rule composed by the AI author or written by hand has no evidence
            # pointing at a document version, and the run it belongs to is the
            # only reliable link back to the source.
            stmt = stmt.join(ExtractionRun, ExtractionRun.id == CandidateRule.extraction_run_id)
            if document_version_id is not None:
                stmt = stmt.where(ExtractionRun.document_version_id == document_version_id)
            if document_id is not None:
                stmt = stmt.join(
                    DocumentVersion, DocumentVersion.id == ExtractionRun.document_version_id
                ).where(DocumentVersion.document_id == document_id)
        stmt = stmt.order_by(CandidateRule.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, candidate_id: uuid.UUID) -> CandidateRule | None:
        result = await self._session.execute(select(CandidateRule).where(CandidateRule.id == candidate_id))
        return result.scalar_one_or_none()

    async def set_review_status(
        self,
        candidate: CandidateRule,
        *,
        review_status: str,
        reviewed_by: str,
        review_notes: str | None = None,
    ) -> CandidateRule:
        candidate.review_status = review_status
        candidate.reviewed_by = reviewed_by
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.review_notes = review_notes
        await self._session.flush()
        return candidate

    async def mark_published(self, candidate: CandidateRule, *, published_version_id: uuid.UUID) -> CandidateRule:
        candidate.review_status = "published"
        candidate.published_version_id = published_version_id
        await self._session.flush()
        return candidate

    async def update_payload(self, candidate: CandidateRule, *, payload_json: dict) -> CandidateRule:
        """Overwrite the draft payload in place (e.g. an accepted AI rewrite).

        Only valid while the candidate is still `candidate`/`rejected` — once
        approved or published the payload is frozen, matching the same
        lifecycle guard `review_candidate_rule` already enforces.
        """

        candidate.payload_json = payload_json
        candidate.revision += 1
        await self._session.flush()
        return candidate


#: A run that reached the end of its work having read everything it was given.
RUN_COMPLETED = "completed"

#: A run that reached the end of its work having passed over some of it. It
#: finished, and what it produced is real; it just is not a whole reading of the
#: document. Callers asking "did this see everything?" must not fold it in with
#: RUN_COMPLETED. Kept as a separate status value rather than a flag beside the
#: status precisely so that the existing readers of `status` cannot answer that
#: question wrongly by default.
RUN_COMPLETED_WITH_GAPS = "completed_with_gaps"


class ExtractionRunRepository:
    """Access to real (non-manual) AI extraction attempts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_version_id: uuid.UUID,
        deployment_name: str,
        prompt_version: str,
        parser_version: str,
    ) -> ExtractionRun:
        run = ExtractionRun(
            document_version_id=document_version_id,
            status="running",
            deployment_name=deployment_name,
            prompt_version=prompt_version,
            parser_version=parser_version,
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def mark_completed(
        self, run: ExtractionRun, *, coverage_complete: bool = True
    ) -> ExtractionRun:
        """Close a run that reached the end of its work.

        ``coverage_complete`` is False when the run passed over material it was
        handed — a batch that errored, a passage that could not be formulated.
        That run finished, but it did not read the whole document, and it is
        recorded under a status that says so.

        This distinction is load-bearing, not cosmetic. ``status == "completed"``
        is the test for "trustworthy enough to diff against" when a later run
        picks its baseline, and the comment at that query says a partial run must
        not be chosen because "comparing against that partial set would report
        every rule it never reached as brand new". A run that skipped material is
        partial in exactly that sense, so folding it in with the whole readings
        makes the delta lie in both directions: rules the baseline never reached
        surface as new, and rules the current run never reached surface as "no
        longer found" — a claim about the document made on the strength of how
        much of it we managed to read.

        The shortfall is in the extraction, never in the policy: material passed
        over is material this system did not read, not material the document
        failed to state.
        """
        run.status = RUN_COMPLETED if coverage_complete else RUN_COMPLETED_WITH_GAPS
        run.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return run

    async def mark_failed(self, run: ExtractionRun, *, error_message: str) -> ExtractionRun:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = error_message
        await self._session.flush()
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> ExtractionRun | None:
        result = await self._session.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
        return result.scalar_one_or_none()


class QualityRunRepository:
    """Append-only history of quality evaluations for a policy set.

    Mirrors `PolicyTestRunRepository`: rows are only ever inserted, never
    updated, so a reviewer can compare quality across time rather than only
    seeing the most recent result.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        scope: str,
        version_number: int | None,
        rule_count: int,
        findings: list[dict],
        ai_review_used: bool,
        methodology_version: str = "1",
        triggered_by: str = "",
    ) -> QualityRun:
        counts: dict[str, int] = {}
        for f in findings:
            sev = str(f.get("severity", "")).lower()
            counts[sev] = counts.get(sev, 0) + 1
        run = QualityRun(
            policy_set_id=policy_set_id,
            scope=scope,
            version_number=version_number,
            rule_count=rule_count,
            high_count=counts.get("high", 0),
            medium_count=counts.get("medium", 0),
            low_count=counts.get("low", 0),
            ai_review_used=ai_review_used,
            methodology_version=methodology_version,
            findings_json=findings,
            triggered_by=triggered_by,
            run_at=datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, scope: str | None = None, limit: int = 50
    ) -> list[QualityRun]:
        stmt = select(QualityRun).where(QualityRun.policy_set_id == policy_set_id)
        if scope is not None:
            stmt = stmt.where(QualityRun.scope == scope)
        stmt = stmt.order_by(QualityRun.run_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, run_id: uuid.UUID) -> QualityRun | None:
        result = await self._session.execute(select(QualityRun).where(QualityRun.id == run_id))
        return result.scalar_one_or_none()
