"""Deterministic version comparison, with an optional AI-generated narrative
layered on top.

The diff itself (added/removed/changed rule ids, field-level deltas) is
always computed deterministically from the persisted `ApprovedPolicyVersion`
snapshots — never by the LLM — so it is exact and reproducible. The LLM is
only asked to summarize that already-correct diff in plain English; its
narrative is clearly labeled as AI commentary, not a second source of truth.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import ApprovedPolicyVersionRepository, PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

_COMPARE_FIELDS = ["title", "description", "rule_type", "effect", "condition", "priority", "effective_from", "effective_to"]

_NARRATIVE_SYSTEM_PROMPT = """You summarize a policy-version diff for a non-technical policy \
administrator. You are given a deterministic JSON diff (added rules, removed rules, changed rules \
with the specific fields that changed). Write a short plain-English summary (3-6 sentences or a short \
bullet list) of the practical impact of these changes. Do not invent any changes beyond what is in the \
diff JSON."""


def _rule_dict(rule: CanonicalRule) -> dict:
    return rule.model_dump(mode="json")


def _diff_rule(a: CanonicalRule, b: CanonicalRule) -> dict | None:
    a_d, b_d = _rule_dict(a), _rule_dict(b)
    changed_fields = {}
    for field in _COMPARE_FIELDS:
        if a_d.get(field) != b_d.get(field):
            changed_fields[field] = {"before": a_d.get(field), "after": b_d.get(field)}
    return changed_fields or None


async def compare_versions(
    session: AsyncSession, *, policy_set_key: str, version_a: int, version_b: int, use_ai_narrative: bool = True
) -> dict:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    all_versions = await version_repo.list_all_versions(policy_set.id)
    by_number = {v.version_number: v for v in all_versions}
    if version_a not in by_number:
        raise ValueError(f"version {version_a} not found for policy set '{policy_set_key}'")
    if version_b not in by_number:
        raise ValueError(f"version {version_b} not found for policy set '{policy_set_key}'")

    package_a = approved_policy_version_to_package(by_number[version_a])
    package_b = approved_policy_version_to_package(by_number[version_b])
    rules_a = {r.rule_id: r for r in package_a.rules}
    rules_b = {r.rule_id: r for r in package_b.rules}

    added = [_rule_dict(rules_b[rid]) for rid in rules_b.keys() - rules_a.keys()]
    removed = [_rule_dict(rules_a[rid]) for rid in rules_a.keys() - rules_b.keys()]
    changed = []
    unchanged_count = 0
    for rid in rules_a.keys() & rules_b.keys():
        diff = _diff_rule(rules_a[rid], rules_b[rid])
        if diff:
            changed.append({"rule_id": rid, "title": rules_b[rid].title, "changed_fields": diff})
        else:
            unchanged_count += 1

    result = {
        "policy_set_key": policy_set_key,
        "version_a": version_a,
        "version_b": version_b,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "narrative": None,
    }

    settings = get_settings()
    if use_ai_narrative and settings.ai_enabled and (added or removed or changed):
        try:
            ai_client = AzureOpenAIClient(settings)
            diff_summary = {
                "added": [{"rule_id": r["rule_id"], "title": r["title"]} for r in added],
                "removed": [{"rule_id": r["rule_id"], "title": r["title"]} for r in removed],
                "changed": changed,
            }
            narrative = await ai_client.chat(
                [
                    {"role": "system", "content": _NARRATIVE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(diff_summary, indent=2, default=str)},
                ],
                deployment=settings.azure_openai_fast_deployment,
                max_tokens=600,
            )
            result["narrative"] = narrative
        except Exception as exc:  # noqa: BLE001 - the deterministic diff is still valid without a narrative
            logger.warning("AI narrative generation failed for compare: %s", exc)
            result["narrative"] = None

    return result
