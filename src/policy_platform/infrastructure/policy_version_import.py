"""Service: import an approved canonical policy version into the domain schema.

Translates `policy_platform.contracts.policy.CanonicalRule` objects (the
canonical, provider-neutral representation) into the relational + JSONB
`ApprovedPolicyVersion` / `ApprovedRule` rows described in
docs/data-model.md. This is the inverse of
`policy_platform.infrastructure.mappers.approved_policy_version_to_package`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import AggregateLimit, CanonicalRule
from policy_platform.domain.models import (
    ApprovedAggregateLimit,
    ApprovedPolicyVersion,
    ApprovedRule,
    RuleException,
)
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    ClauseRepository,
    EvidenceReferenceRepository,
    PolicyAuthorityRepository,
)

logger = logging.getLogger(__name__)


async def import_approved_policy_version(
    session: AsyncSession,
    *,
    policy_set_id: uuid.UUID,
    version_number: int,
    effective_from: date,
    effective_to: date | None,
    approved_by: str,
    is_active: bool,
    rules: list[CanonicalRule],
    aggregate_limits: list[AggregateLimit] | None = None,
) -> ApprovedPolicyVersion:
    authority_repo = PolicyAuthorityRepository(session)
    evidence_repo = EvidenceReferenceRepository(session)

    # A rule's `evidence[].clause_id` is captured at AI-extraction time and
    # persisted verbatim inside the candidate's JSONB payload — an unenforced,
    # best-effort pointer into `clauses`, not a real foreign key until this
    # import promotes it into an `EvidenceReference` row. If the referenced
    # clause was since deleted (e.g. a one-off re-extraction that replaced a
    # document's clause rows to fix parse quality — see
    # scripts/reextract_document.py), the stale id must not fail the entire
    # publish: `EvidenceReference.clause_id` is nullable specifically so
    # evidence can degrade to "hash/page/section only" when the live
    # cross-reference is gone, rather than blocking publication of otherwise
    # valid, human-approved rules. Resolve validity once, in bulk, up front.
    referenced_clause_ids = {
        uuid.UUID(ev.clause_id)
        for rule in rules
        for ev in rule.evidence
        if ev.clause_id
    }
    valid_clause_ids: set[uuid.UUID] = set()
    if referenced_clause_ids:
        existing_clauses = await ClauseRepository(session).get_by_ids(list(referenced_clause_ids))
        valid_clause_ids = {c.id for c in existing_clauses}
        stale_count = len(referenced_clause_ids) - len(valid_clause_ids)
        if stale_count:
            logger.warning(
                "publish: %d of %d referenced clause_id(s) no longer exist (likely a prior "
                "clause re-extraction); those evidence entries will be persisted with "
                "clause_id=NULL, keeping source_hash/page/section/offsets intact.",
                stale_count,
                len(referenced_clause_ids),
            )

    if is_active:
        # Enforce "exactly one active version at a time" before inserting the
        # new one, so `get_active_version` is unambiguous regardless of
        # version_number ordering.
        await ApprovedPolicyVersionRepository(session).deactivate_all(policy_set_id)

    version = ApprovedPolicyVersion(
        policy_set_id=policy_set_id,
        version_number=version_number,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=is_active,
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc),
    )
    session.add(version)
    await session.flush()

    for rule in rules:
        authority = await authority_repo.get_or_create(
            level=rule.authority.level, owner=rule.authority.owner, rank=rule.authority.rank
        )

        approved_rule = ApprovedRule(
            policy_version_id=version.id,
            authority_id=authority.id,
            rule_id=rule.rule_id,
            revision=rule.rule_revision,
            title=rule.title,
            description=rule.description,
            rule_type=rule.rule_type.value,
            priority=rule.priority,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            machine_executable=rule.machine_executable,
            ambiguity_status=rule.ambiguity_status.value,
            review_status=rule.review_status.value,
            scope_json=rule.scope.model_dump(mode="json"),
            condition_json=rule.condition.model_dump(mode="json", by_alias=True),
            effect_json=rule.effect.model_dump(mode="json"),
            required_facts_json=[f.model_dump(mode="json") for f in rule.required_facts],
            lineage_json=rule.lineage.model_dump(mode="json"),
            category=rule.category,
            tags_json=list(rule.tags),
            group_label=rule.group_label,
            related_rule_ids_json=list(rule.related_rule_ids),
            is_explicit_override=rule.is_explicit_override,
            supersedes_rule_ids_json=list(rule.supersedes_rule_ids),
            advice_json=[a.model_dump(mode="json") for a in rule.advice],
            formulation_json=(
                rule.formulation.model_dump(mode="json") if rule.formulation else None
            ),
        )
        session.add(approved_rule)
        await session.flush()

        for exc in rule.exceptions:
            session.add(
                RuleException(
                    rule_id=approved_rule.id,
                    exception_key=exc.exception_id,
                    description=exc.description,
                    condition_json=exc.condition.model_dump(mode="json", by_alias=True) if exc.condition else None,
                    effect_override_json=exc.effect_override.model_dump(mode="json") if exc.effect_override else None,
                    limit_value=exc.limit_value,
                    limit_unit=exc.limit_unit,
                )
            )

        if rule.evidence:
            evidence_dicts = []
            for ev in rule.evidence:
                ev_dict = ev.model_dump(mode="json")
                if ev_dict.get("clause_id") and uuid.UUID(ev_dict["clause_id"]) not in valid_clause_ids:
                    ev_dict["clause_id"] = None
                evidence_dicts.append(ev_dict)
            await evidence_repo.bulk_create(rule_id=approved_rule.id, evidence=evidence_dicts)

    # Aggregate limits have no per-candidate review workflow (they're
    # structural policy-set configuration, not prose) — the caller passes the
    # policy set's current full draft list, which is snapshotted verbatim as
    # this version's immutable record (Rule 5.3), mirroring how `rules` above
    # represents the full rule set rather than only what changed.
    for agg in aggregate_limits or []:
        session.add(
            ApprovedAggregateLimit(
                policy_version_id=version.id,
                aggregate_key=agg.aggregate_id,
                description=agg.description,
                contributing_rules_json=[c.model_dump(mode="json") for c in agg.contributing_rules],
                aggregator=agg.aggregator,
                max_value=agg.max_value,
                period=agg.period,
            )
        )

    await session.flush()
    return version
