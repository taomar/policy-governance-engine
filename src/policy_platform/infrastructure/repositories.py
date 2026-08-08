"""Repository layer: the only place that issues SQL against domain entities.

Enforces Rule 5.3 (approved artifacts are immutable — insert-only) and keeps
routers/services from depending on SQLAlchemy query construction directly.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.domain.models import (
    ApprovedPolicyVersion,
    ApprovedRule,
    CandidateRule,
    Clause,
    Evaluation,
    EvidenceReference,
    ExtractionRun,
    Note,
    PolicyAggregateLimit,
    PolicyAuthority,
    PolicyException,
    PolicySet,
    PolicyTest,
    PolicyTestRun,
    QualityRun,
)


class PolicySetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> PolicySet | None:
        result = await self._session.execute(select(PolicySet).where(PolicySet.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PolicySet]:
        result = await self._session.execute(select(PolicySet).order_by(PolicySet.key))
        return list(result.scalars().all())

    async def create(
        self,
        *,
        key: str,
        name: str,
        owner: str,
        description: str = "",
        category: str = "",
        tags: list[str] | None = None,
    ) -> PolicySet:
        policy_set = PolicySet(
            key=key,
            name=name,
            owner=owner,
            description=description,
            category=category,
            tags_json=list(tags or []),
        )
        self._session.add(policy_set)
        await self._session.flush()
        return policy_set

    async def update_metadata(
        self,
        policy_set: PolicySet,
        *,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> PolicySet:
        if name is not None:
            policy_set.name = name
        if description is not None:
            policy_set.description = description
        if category is not None:
            policy_set.category = category
        if tags is not None:
            policy_set.tags_json = list(tags)
        await self._session.flush()
        return policy_set


class PolicyAuthorityRepository:
    """Get-or-create access to authority rows (keyed by level+owner)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, *, level: str, owner: str, rank: int) -> PolicyAuthority:
        result = await self._session.execute(
            select(PolicyAuthority).where(PolicyAuthority.level == level, PolicyAuthority.owner == owner)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        authority = PolicyAuthority(level=level, owner=owner, rank=rank)
        self._session.add(authority)
        await self._session.flush()
        return authority


class ApprovedPolicyVersionRepository:
    """Read/insert access to immutable approved policy versions and rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_version(self, policy_set_id: uuid.UUID) -> ApprovedPolicyVersion | None:
        stmt = (
            select(ApprovedPolicyVersion)
            .where(
                ApprovedPolicyVersion.policy_set_id == policy_set_id,
                ApprovedPolicyVersion.is_active.is_(True),
            )
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
            .order_by(ApprovedPolicyVersion.version_number.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, policy_version_id: uuid.UUID) -> ApprovedPolicyVersion | None:
        stmt = (
            select(ApprovedPolicyVersion)
            .where(ApprovedPolicyVersion.id == policy_version_id)
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def insert_version(self, version: ApprovedPolicyVersion) -> ApprovedPolicyVersion:
        """Insert a brand-new immutable version row (never call session.merge on an existing one)."""

        self._session.add(version)
        await self._session.flush()
        return version

    async def list_all_versions(self, policy_set_id: uuid.UUID) -> list[ApprovedPolicyVersion]:
        """All versions of a policy set, newest first, rules eager-loaded.

        Used by the admin UI's version-history timeline — unlike
        `get_active_version`/`get_by_id`, this deliberately returns every
        version (active and superseded) so reviewers can see the full history.
        """
        stmt = (
            select(ApprovedPolicyVersion)
            .where(ApprovedPolicyVersion.policy_set_id == policy_set_id)
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
            .order_by(ApprovedPolicyVersion.version_number.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_max_version_number(self, policy_set_id: uuid.UUID) -> int:
        stmt = select(ApprovedPolicyVersion.version_number).where(
            ApprovedPolicyVersion.policy_set_id == policy_set_id
        )
        result = await self._session.execute(stmt)
        numbers = [row[0] for row in result.all()]
        return max(numbers) if numbers else 0

    async def deactivate_all(self, policy_set_id: uuid.UUID) -> None:
        """Flip `is_active` off for every existing version of this policy set.

        Called before activating a newly-published version so exactly one
        version is active at a time (the `is_active` flag itself is mutable
        lifecycle metadata, not a substantive/audited column — Rule 5.3
        immutability applies to the rule content, not this flag).
        """
        stmt = select(ApprovedPolicyVersion).where(ApprovedPolicyVersion.policy_set_id == policy_set_id)
        result = await self._session.execute(stmt)
        for version in result.scalars().all():
            version.is_active = False
        await self._session.flush()


class EvaluationRepository:
    """Append-only audit log of runtime evaluation calls."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        policy_set_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        correlation_id: str | None,
        calling_system_identity: str | None,
        request_facts: dict,
        overall_status: str,
        result_hash: str,
        response_json: dict,
        evaluation_timestamp: datetime,
    ) -> Evaluation:
        evaluation = Evaluation(
            policy_set_id=policy_set_id,
            policy_version_id=policy_version_id,
            correlation_id=correlation_id,
            calling_system_identity=calling_system_identity,
            request_facts_json=request_facts,
            overall_status=overall_status,
            result_hash=result_hash,
            response_json=response_json,
            evaluation_timestamp=evaluation_timestamp or datetime.now(timezone.utc),
        )
        self._session.add(evaluation)
        await self._session.flush()
        return evaluation


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
        self, policy_set_id: uuid.UUID, *, review_status: str | None = None
    ) -> list[CandidateRule]:
        stmt = select(CandidateRule).where(CandidateRule.policy_set_id == policy_set_id)
        if review_status is not None:
            stmt = stmt.where(CandidateRule.review_status == review_status)
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

    async def mark_completed(self, run: ExtractionRun) -> ExtractionRun:
        run.status = "completed"
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


class NoteRepository:
    """Access to human-authored collaboration notes (see domain/models.py:Note).

    Append-mostly: notes are created and (optionally) deleted by their
    author, never edited in place — this mirrors the audit-trail posture of
    the rest of the domain rather than introducing a new "editable comment"
    concept.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, entity_type: str, entity_id: str, author: str, author_role: str, body: str
    ) -> Note:
        note = Note(
            entity_type=entity_type,
            entity_id=entity_id,
            author=author,
            author_role=author_role,
            body=body,
        )
        self._session.add(note)
        await self._session.flush()
        return note

    async def list_for_entity(self, *, entity_type: str, entity_id: str) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.entity_type == entity_type, Note.entity_id == entity_id)
            .order_by(Note.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, note_id: uuid.UUID) -> Note | None:
        result = await self._session.execute(select(Note).where(Note.id == note_id))
        return result.scalar_one_or_none()

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)
        await self._session.flush()


class PolicyAggregateLimitRepository:
    """CRUD access to mutable draft aggregate limits (see domain/models.py).

    Unlike `CandidateRuleRepository`, there is no review workflow here —
    aggregate limits are structural policy-set configuration a Policy
    Manager edits directly (same posture as `PolicySetRepository.update_metadata`
    for tags/category), not prose subject to per-candidate human review.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_policy_set(self, policy_set_id: uuid.UUID) -> list[PolicyAggregateLimit]:
        stmt = (
            select(PolicyAggregateLimit)
            .where(PolicyAggregateLimit.policy_set_id == policy_set_id)
            .order_by(PolicyAggregateLimit.aggregate_key)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, policy_set_id: uuid.UUID, aggregate_key: str) -> PolicyAggregateLimit | None:
        stmt = select(PolicyAggregateLimit).where(
            PolicyAggregateLimit.policy_set_id == policy_set_id,
            PolicyAggregateLimit.aggregate_key == aggregate_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        aggregate_key: str,
        description: str,
        contributing_rules: list[dict],
        aggregator: str = "SUM",
        max_value: float,
        period: str | None = None,
    ) -> PolicyAggregateLimit:
        row = PolicyAggregateLimit(
            policy_set_id=policy_set_id,
            aggregate_key=aggregate_key,
            description=description,
            contributing_rules_json=contributing_rules,
            aggregator=aggregator,
            max_value=max_value,
            period=period,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        row: PolicyAggregateLimit,
        *,
        description: str,
        contributing_rules: list[dict],
        aggregator: str,
        max_value: float,
        period: str | None,
    ) -> PolicyAggregateLimit:
        """Full-replace update (mirrors `create`'s signature).

        Aggregate limits are small, fully-specified structural rows edited
        via a single form — unlike `PolicySetRepository.update_metadata`
        there is no ambiguity to resolve between "field omitted" and "field
        cleared to None", since every field is always supplied.
        """
        row.description = description
        row.contributing_rules_json = contributing_rules
        row.aggregator = aggregator
        row.max_value = max_value
        row.period = period
        await self._session.flush()
        return row

    async def delete(self, row: PolicyAggregateLimit) -> None:
        await self._session.delete(row)
        await self._session.flush()


class PolicyTestRepository:
    """Access to saved `PolicyTest` definitions.

    Updates in place are expected here (`review_status`, `is_active`, etc.)
    — like `CandidateRuleRepository`, a test's own definition is not yet an
    authoritative published artifact, so this is not a Rule 5.3 violation.
    Only `PolicyTestRunRepository` (the recorded results of executing a
    test) is append-only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        name: str,
        description: str,
        test_kind: str,
        input_facts_json: dict,
        evaluation_timestamp_override: datetime | None,
        expected_overall_status: str,
        expected_rule_id: str | None,
        expected_rule_status: str | None,
        expected_missing_facts_json: list | None,
        proposed_by: str,
        review_status: str,
        is_active: bool,
    ) -> PolicyTest:
        test = PolicyTest(
            policy_set_id=policy_set_id,
            name=name,
            description=description,
            test_kind=test_kind,
            input_facts_json=input_facts_json,
            evaluation_timestamp_override=evaluation_timestamp_override,
            expected_overall_status=expected_overall_status,
            expected_rule_id=expected_rule_id,
            expected_rule_status=expected_rule_status,
            expected_missing_facts_json=expected_missing_facts_json,
            proposed_by=proposed_by,
            review_status=review_status,
            is_active=is_active,
        )
        self._session.add(test)
        await self._session.flush()
        return test

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, is_active: bool | None = None, test_kind: str | None = None
    ) -> list[PolicyTest]:
        stmt = select(PolicyTest).where(PolicyTest.policy_set_id == policy_set_id)
        if is_active is not None:
            stmt = stmt.where(PolicyTest.is_active == is_active)
        if test_kind is not None:
            stmt = stmt.where(PolicyTest.test_kind == test_kind)
        stmt = stmt.order_by(PolicyTest.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, test_id: uuid.UUID) -> PolicyTest | None:
        result = await self._session.execute(select(PolicyTest).where(PolicyTest.id == test_id))
        return result.scalar_one_or_none()

    async def set_review_status(
        self,
        test: PolicyTest,
        *,
        review_status: str,
        is_active: bool,
        reviewed_by: str,
        review_notes: str | None = None,
    ) -> PolicyTest:
        test.review_status = review_status
        test.is_active = is_active
        test.reviewed_by = reviewed_by
        test.reviewed_at = datetime.now(timezone.utc)
        test.review_notes = review_notes
        await self._session.flush()
        return test


class PolicyTestRunRepository:
    """Append-only execution history for `PolicyTest` rows.

    Mirrors `EvaluationRepository`: every call to `record` inserts a new row,
    never updates an existing one, so the full pass/fail history for a test
    across every published version is preserved.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        policy_test_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        status: str,
        explanation: str,
        actual_response_json: dict | None,
        run_trigger: str,
        triggered_by: str,
        run_at: datetime | None = None,
    ) -> PolicyTestRun:
        run = PolicyTestRun(
            policy_test_id=policy_test_id,
            policy_version_id=policy_version_id,
            status=status,
            explanation=explanation,
            actual_response_json=actual_response_json,
            run_trigger=run_trigger,
            triggered_by=triggered_by,
            run_at=run_at or datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def list_by_test(self, policy_test_id: uuid.UUID) -> list[PolicyTestRun]:
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id == policy_test_id)
            .order_by(PolicyTestRun.run_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_test(self, policy_test_id: uuid.UUID) -> PolicyTestRun | None:
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id == policy_test_id)
            .order_by(PolicyTestRun.run_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_tests(self, policy_test_ids: list[uuid.UUID]) -> dict[uuid.UUID, PolicyTestRun]:
        """Batch-fetch the single most recent run per test id.

        Uses Postgres `DISTINCT ON` (this project only ever targets
        Postgres — see infrastructure/settings.py — so there is no
        cross-dialect portability concern here, same reasoning as the
        JSONB columns used throughout domain/models.py).
        """
        if not policy_test_ids:
            return {}
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id.in_(policy_test_ids))
            .distinct(PolicyTestRun.policy_test_id)
            .order_by(PolicyTestRun.policy_test_id, PolicyTestRun.run_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {row.policy_test_id: row for row in rows}


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


class PolicyExceptionRepository:
    """CRUD + decide workflow for ad hoc, human-requested policy exceptions
    (ADR-0009; see domain.models.PolicyException for the full contrast with
    the standing, auto-evaluated `RuleException`).

    Mutable in place for the decide step (`decision`/`decided_by`
    /`decided_at`/`decision_notes`) — same posture as `PolicyTestRepository`:
    a request record, not an immutable governance artifact like
    `ApprovedRule`, so updating it in place is not a Rule 5.3 violation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        rule_id: str | None,
        requester: str,
        justification: str,
        expiry_date: date | None,
    ) -> PolicyException:
        row = PolicyException(
            policy_set_id=policy_set_id,
            rule_id=rule_id,
            requester=requester,
            justification=justification,
            decision="pending",
            expiry_date=expiry_date,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, decision: str | None = None, rule_id: str | None = None
    ) -> list[PolicyException]:
        stmt = select(PolicyException).where(PolicyException.policy_set_id == policy_set_id)
        if decision is not None:
            stmt = stmt.where(PolicyException.decision == decision)
        if rule_id is not None:
            stmt = stmt.where(PolicyException.rule_id == rule_id)
        stmt = stmt.order_by(PolicyException.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, exception_id: uuid.UUID) -> PolicyException | None:
        result = await self._session.execute(select(PolicyException).where(PolicyException.id == exception_id))
        return result.scalar_one_or_none()

    async def decide(
        self,
        row: PolicyException,
        *,
        decision: str,
        decided_by: str,
        decision_notes: str | None,
    ) -> PolicyException:
        row.decision = decision
        row.decided_by = decided_by
        row.decided_at = datetime.now(timezone.utc)
        row.decision_notes = decision_notes
        await self._session.flush()
        return row
