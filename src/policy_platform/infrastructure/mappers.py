"""Mappers between domain (SQLAlchemy) rows and canonical contracts.

Keeps the evaluator's input type (`ApprovedPolicyPackage`) fully decoupled
from the persistence schema (Rule 5.4 / ADR-0002): the evaluator never sees
a SQLAlchemy object.
"""
from __future__ import annotations

from policy_platform.contracts.formulation import RuleFormulation
from policy_platform.contracts.policy import (
    AggregateLimit,
    AggregateLimitContribution,
    ApprovedPolicyPackage,
    Advice,
    CanonicalRule,
    Effect,
    EvidenceReference as ContractEvidenceReference,
    PolicyAuthority as ContractPolicyAuthority,
    PolicyScope,
    RequiredFact,
    RuleException as ContractRuleException,
    RuleLineage,
)
from policy_platform.domain.models import ApprovedPolicyVersion, ApprovedRule


def _rule_to_contract(rule: ApprovedRule) -> CanonicalRule:
    # Imported here rather than at module scope: `formulation_mapping` imports
    # the contracts this module also imports, and hoisting it makes the cycle
    # an import-time failure instead of a lazy one.
    from policy_platform.infrastructure.formulation_mapping import _decision_readiness_for

    formulation = (
        RuleFormulation.model_validate(rule.formulation_json) if rule.formulation_json else None
    )
    return CanonicalRule(
        policy_set_id=str(rule.policy_version.policy_set_id),
        policy_version_id=str(rule.policy_version_id),
        rule_id=rule.rule_id,
        rule_revision=rule.revision,
        title=rule.title,
        description=rule.description,
        rule_type=rule.rule_type,
        authority=ContractPolicyAuthority(
            level=rule.authority.level, owner=rule.authority.owner, rank=rule.authority.rank
        ),
        scope=PolicyScope(**rule.scope_json),
        condition=rule.condition_json,
        effect=Effect(**rule.effect_json),
        required_facts=[RequiredFact(**f) for f in rule.required_facts_json],
        exceptions=[
            ContractRuleException(
                exception_id=exc.exception_key,
                description=exc.description,
                condition=exc.condition_json,
                effect_override=exc.effect_override_json,
                limit_value=exc.limit_value,
                limit_unit=exc.limit_unit,
            )
            for exc in rule.exceptions
        ],
        priority=rule.priority,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
        machine_executable=rule.machine_executable,
        ambiguity_status=rule.ambiguity_status,
        review_status=rule.review_status,
        evidence=[
            ContractEvidenceReference(
                document_version_id=str(ev.document_version_id),
                source_hash=ev.source_hash,
                page=ev.page,
                section=ev.section,
                clause_id=str(ev.clause_id) if ev.clause_id else None,
                start_offset=ev.start_offset,
                end_offset=ev.end_offset,
            )
            for ev in rule.evidence
        ],
        lineage=RuleLineage(**rule.lineage_json) if rule.lineage_json else RuleLineage(),
        category=rule.category,
        tags=list(rule.tags_json or []),
        group_label=rule.group_label,
        related_rule_ids=list(rule.related_rule_ids_json or []),
        is_explicit_override=rule.is_explicit_override,
        supersedes_rule_ids=list(rule.supersedes_rule_ids_json or []),
        advice=[Advice(**a) for a in (rule.advice_json or [])],
        # Restores what the source actually said. The fields above are a lossy
        # executable projection of this record, so a rule reconstructed without
        # it is not the rule that was published — see migration e4c7a2b8d190.
        formulation=formulation,
        # Derived on read rather than stored in its own column. It is a pure
        # function of `formulation.canonical`, which is already persisted, so a
        # second copy could only ever disagree with the record it came from —
        # and correcting the assessment would leave every rule approved before
        # the fix carrying the stale verdict. Deriving it means a correction
        # applies everywhere at once.
        decision_readiness=(
            _decision_readiness_for(formulation.canonical)
            if formulation and formulation.canonical
            else None
        ),
    )


def approved_policy_version_to_package(version: ApprovedPolicyVersion) -> ApprovedPolicyPackage:
    """Reconstruct the canonical, immutable `ApprovedPolicyPackage` the evaluator consumes."""

    return ApprovedPolicyPackage(
        policy_set_id=str(version.policy_set_id),
        policy_version_id=str(version.id),
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        rules=[_rule_to_contract(r) for r in version.rules],
        aggregate_limits=[
            AggregateLimit(
                aggregate_id=agg.aggregate_key,
                description=agg.description,
                contributing_rules=[
                    AggregateLimitContribution(**c) for c in (agg.contributing_rules_json or [])
                ],
                aggregator=agg.aggregator,
                max_value=agg.max_value,
                period=agg.period,
            )
            for agg in version.aggregate_limits
        ],
    )

