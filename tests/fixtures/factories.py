"""Shared test factories for constructing canonical policy fixtures."""
from __future__ import annotations

from datetime import date

from policy_platform.contracts.conditions import ConditionNode
from policy_platform.contracts.policy import (
    Advice,
    ApprovedPolicyPackage,
    CanonicalRule,
    Effect,
    EffectType,
    PolicyAuthority,
    PolicyScope,
    RuleType,
)


def make_authority(rank: int = 10, level: str = "corporate", owner: str = "test-owner") -> PolicyAuthority:
    return PolicyAuthority(level=level, owner=owner, rank=rank)


def make_scope(**kwargs) -> PolicyScope:
    # All-wildcard by default: existing tests exercise conditions/precedence,
    # not scope enforcement, and should not be affected by turning on Target
    # matching. Tests that specifically exercise scope enforcement override
    # individual dimensions explicitly.
    defaults = {"jurisdictions": ["*"], "organizational_units": ["*"], "personas": ["*"], "processes": ["*"]}
    defaults.update(kwargs)
    return PolicyScope(**defaults)


def make_rule(
    rule_id: str,
    condition: ConditionNode,
    *,
    effect_action: str = "allow_action",
    effect_type: EffectType = EffectType.ALLOW,
    authority: PolicyAuthority | None = None,
    scope: PolicyScope | None = None,
    priority: int = 0,
    effective_from: date = date(2024, 1, 1),
    effective_to: date | None = None,
    machine_executable: bool = True,
    exceptions: list | None = None,
    revision: int = 1,
    rule_type: RuleType = RuleType.APPROVAL_REQUIREMENT,
    is_explicit_override: bool = False,
    supersedes_rule_ids: list[str] | None = None,
    advice: list[Advice] | None = None,
) -> CanonicalRule:
    return CanonicalRule(
        policy_set_id="test-policy",
        policy_version_id="v1",
        rule_id=rule_id,
        rule_revision=revision,
        title=f"Rule {rule_id}",
        rule_type=rule_type,
        authority=authority or make_authority(),
        scope=scope or make_scope(),
        condition=condition,
        effect=Effect(type=effect_type, action=effect_action),
        priority=priority,
        effective_from=effective_from,
        effective_to=effective_to,
        machine_executable=machine_executable,
        exceptions=exceptions or [],
        is_explicit_override=is_explicit_override,
        supersedes_rule_ids=supersedes_rule_ids or [],
        advice=advice or [],
    )


def make_package(
    rules: list[CanonicalRule],
    effective_from: date = date(2024, 1, 1),
    aggregate_limits: list | None = None,
) -> ApprovedPolicyPackage:
    return ApprovedPolicyPackage(
        policy_set_id="test-policy",
        policy_version_id="v1",
        effective_from=effective_from,
        rules=rules,
        aggregate_limits=aggregate_limits or [],
    )
