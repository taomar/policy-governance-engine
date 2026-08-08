"""Deterministic whole-policy-set summary, with an optional AI-generated
plain-English narrative layered on top.

Mirrors `ai_compare.py`'s pattern: every fact in `stats` is computed directly
from the persisted `ApprovedPolicyPackage` (rule counts, scope coverage,
explicit overrides, advice/obligations, aggregate limits) — never invented by
the LLM. The LLM is only asked to narrate that already-correct stats block in
plain English for a non-technical reader (a new employee, an auditor, an
executive); its narrative is clearly labeled as AI commentary, not a second
source of truth, and the deterministic `stats` block is always returned even
when AI is disabled or the call fails.
"""
from __future__ import annotations

import json
import logging
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import ApprovedPolicyVersionRepository, PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

_NARRATIVE_SYSTEM_PROMPT = """You write a plain-English executive summary of an entire policy set for a \
non-technical reader (e.g. a new employee, an auditor, or an executive who will never read individual rule \
definitions). You are given a deterministic JSON breakdown (rule counts by type/effect/category, who and where \
it applies to, explicit overrides, obligations) plus a compact digest of every rule's title, one-line \
description, and effect, grouped by rule type. Write 1-2 short paragraphs describing what this policy set \
governs and who it applies to, followed by a short bulleted list of the most important or notable rules \
(key thresholds, approval chains, exceptions, explicit overrides). Do not invent any rule, number, or scope \
value beyond what is in the JSON provided.

Formatting rules (strict): write plain prose only. Do NOT use markdown syntax of any kind — no ** for bold, \
no # headings, no numbered lists. For the bulleted list, start each line with a single "- " and nothing else \
(no bold label before the colon); put the key term in plain words as the start of the sentence instead, e.g. \
"- Requests above $10,000 need Director approval." rather than "- **Approval thresholds:** ...". Separate the \
intro paragraph(s) from the bullet list with a blank line."""


def _scope_coverage(rules: list[CanonicalRule]) -> dict[str, list[str]]:
    """Union of every rule's scope dimensions — a deterministic answer to
    "who/where does this policy set apply to" without needing an LLM."""
    jurisdictions: set[str] = set()
    organizational_units: set[str] = set()
    personas: set[str] = set()
    processes: set[str] = set()
    for rule in rules:
        jurisdictions.update(rule.scope.jurisdictions)
        organizational_units.update(rule.scope.organizational_units)
        personas.update(rule.scope.personas)
        processes.update(rule.scope.processes)
    return {
        "jurisdictions": sorted(jurisdictions),
        "organizational_units": sorted(organizational_units),
        "personas": sorted(personas),
        "processes": sorted(processes),
    }


def _grouped_rule_digest(rules: list[CanonicalRule]) -> dict[str, list[dict]]:
    """Compact per-rule_type listing (title/description/effect only — no raw
    condition JSON) so even a 200-rule policy set stays a modest token budget.
    The AI needs real substantive content to summarize from, but the exact
    executable condition logic isn't needed for a high-level narrative."""
    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule.rule_type.value, []).append(
            {
                "title": rule.title,
                "description": rule.description,
                "effect": f"{rule.effect.type.value}: {rule.effect.action}",
            }
        )
    return grouped


async def summarize_policy_set(
    session: AsyncSession,
    *,
    policy_set_key: str,
    version_number: int | None = None,
    use_ai_narrative: bool = True,
) -> dict:
    """`version_number=None` summarizes the currently active published
    version. Raises `ValueError` (→ 404 at the router) if the policy set, the
    requested version, or an active version don't exist.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    if version_number is None:
        version = await version_repo.get_active_version(policy_set.id)
        if version is None:
            raise ValueError(f"policy set '{policy_set_key}' has no active published version")
    else:
        all_versions = await version_repo.list_all_versions(policy_set.id)
        by_number = {v.version_number: v for v in all_versions}
        if version_number not in by_number:
            raise ValueError(f"version {version_number} not found for policy set '{policy_set_key}'")
        version = by_number[version_number]

    package = approved_policy_version_to_package(version)
    rules = package.rules

    by_rule_type = Counter(rule.rule_type.value for rule in rules)
    by_effect = Counter(rule.effect.type.value for rule in rules)
    by_ambiguity_status = Counter(rule.ambiguity_status.value for rule in rules)
    by_category = Counter(rule.category or "Uncategorized" for rule in rules)
    overrides = [rule for rule in rules if rule.is_explicit_override]
    advice_rules = [rule for rule in rules if rule.advice]

    stats = {
        "total_rules": len(rules),
        "by_rule_type": dict(by_rule_type),
        "by_effect": dict(by_effect),
        "by_ambiguity_status": dict(by_ambiguity_status),
        "by_category": dict(by_category),
        "scope_coverage": _scope_coverage(rules),
        "explicit_overrides_count": len(overrides),
        "explicit_overrides": [{"rule_id": rule.rule_id, "title": rule.title} for rule in overrides],
        "advice_rules_count": len(advice_rules),
        "aggregate_limits_count": len(package.aggregate_limits),
        "rules_with_sunset_date": sum(1 for rule in rules if rule.effective_to is not None),
    }

    result = {
        "policy_set_key": policy_set_key,
        "policy_set_name": policy_set.name,
        "version_number": version.version_number,
        "is_active": version.is_active,
        "effective_from": version.effective_from.isoformat() if version.effective_from else None,
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "stats": stats,
        "narrative": None,
    }

    settings = get_settings()
    if use_ai_narrative and settings.ai_enabled and rules:
        try:
            ai_client = AzureOpenAIClient(settings)
            payload = {
                "policy_set_name": policy_set.name,
                "stats": stats,
                "rules_by_type": _grouped_rule_digest(rules),
            }
            narrative = await ai_client.chat(
                [
                    {"role": "system", "content": _NARRATIVE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
                ],
                deployment=settings.azure_openai_fast_deployment,
                max_tokens=900,
            )
            result["narrative"] = narrative
        except Exception as exc:  # noqa: BLE001 - the deterministic stats block is still valid without a narrative
            logger.warning("AI narrative generation failed for policy-set summary: %s", exc)
            result["narrative"] = None

    return result
