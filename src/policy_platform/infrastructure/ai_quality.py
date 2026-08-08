"""Policy quality evaluation: deterministic structural checks + an AI
qualitative review layered on top, clearly labeled by provenance.

This is the "are these policies actually any good?" feature. Findings are
tagged `source: "deterministic"` (always exact — computed by inspecting the
persisted rule set with plain code, no LLM involved) or `source: "ai_review"`
(the model's judgment about gaps/redundancy/ambiguous wording — genuinely
useful, but not infallible, and never silently presented as fact).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    CandidateRuleRepository,
    PolicySetRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

_AI_REVIEW_SYSTEM_PROMPT = """You are a senior policy analyst reviewing a company's formalized \
governance rules for quality issues. You are given: (1) the full list of currently-approved rules \
(id, type, effect, condition, scope, description) and (2) a list of deterministic structural findings \
already computed by code. Identify ADDITIONAL qualitative issues: gaps (an area the rules seem to leave \
uncovered), redundancy (rules that overlap or restate each other), unclear/ambiguous wording remaining in \
descriptions, missing exception handling, or business risk you notice. Do not repeat the deterministic \
findings you were given verbatim — add analysis beyond them.

Respond with a JSON object: {"findings": [ {"severity": "high"|"medium"|"low", "category": str, \
"finding": str, "affected_rule_ids": [str], "recommendation": str}, ... ]}. If you find nothing beyond \
the deterministic findings, return {"findings": []}. Be specific and reference rule_id/title where \
possible; do not fabricate rule ids that were not given to you."""


def _deterministic_findings(rules: list[CanonicalRule]) -> list[dict]:
    findings: list[dict] = []

    seen_ids: dict[str, int] = {}
    for r in rules:
        seen_ids[r.rule_id] = seen_ids.get(r.rule_id, 0) + 1
    for rid, count in seen_ids.items():
        if count > 1:
            findings.append(
                {
                    "severity": "high",
                    "category": "duplicate_rule_id",
                    "finding": f"rule_id '{rid}' appears {count} times in the same approved version",
                    "affected_rule_ids": [rid],
                    "recommendation": "Ensure every rule_id is unique within a policy version.",
                    "source": "deterministic",
                }
            )

    for r in rules:
        if r.ambiguity_status.value != "none":
            findings.append(
                {
                    "severity": "high" if r.ambiguity_status.value == "blocking" else "medium",
                    "category": "ambiguity",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) has ambiguity_status={r.ambiguity_status.value}",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "Have a human reviewer formalize this rule's condition/wording before relying on it in automated evaluation.",
                    "source": "deterministic",
                }
            )
        if not r.machine_executable:
            findings.append(
                {
                    "severity": "medium",
                    "category": "not_machine_executable",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) is marked machine_executable=false",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "This rule cannot be enforced by the deterministic evaluator yet; it needs a precise condition.",
                    "source": "deterministic",
                }
            )
        if r.effective_to is not None and r.effective_to < date.today():
            findings.append(
                {
                    "severity": "medium",
                    "category": "expired_rule",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) has effective_to={r.effective_to} in the past but is still in the active version",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "Remove or update this rule's effective_to, or supersede it in a new version.",
                    "source": "deterministic",
                }
            )
        fact_names = {f.name for f in r.required_facts}
        for exc in r.exceptions:
            if exc.condition is not None and hasattr(exc.condition, "fact"):
                if exc.condition.fact not in fact_names:
                    findings.append(
                        {
                            "severity": "low",
                            "category": "orphan_exception_fact",
                            "finding": (
                                f"Exception '{exc.exception_id}' on rule '{r.rule_id}' references fact "
                                f"'{exc.condition.fact}' which is not declared in required_facts"
                            ),
                            "affected_rule_ids": [r.rule_id],
                            "recommendation": "Add the fact to required_facts so callers know to supply it.",
                            "source": "deterministic",
                        }
                    )

    # Conflicting-effect heuristic: same rule_type + same effect.action but opposite allow/deny.
    by_type_action: dict[tuple[str, str], list[CanonicalRule]] = {}
    for r in rules:
        by_type_action.setdefault((r.rule_type.value, r.effect.action), []).append(r)
    for (rtype, action), group in by_type_action.items():
        effects = {r.effect.type.value for r in group}
        if {"allow", "deny"} <= effects:
            findings.append(
                {
                    "severity": "high",
                    "category": "conflicting_effect",
                    "finding": (
                        f"Multiple rules of type '{rtype}' target the same action '{action}' but disagree "
                        f"(some allow, some deny): {[r.rule_id for r in group]}"
                    ),
                    "affected_rule_ids": [r.rule_id for r in group],
                    "recommendation": "Review scope/condition/priority to confirm these are meant to coexist, or consolidate them.",
                    "source": "deterministic",
                }
            )

    return findings


async def _run_ai_review(rules: list[CanonicalRule], findings: list[dict], policy_set_key: str) -> None:
    """Append AI-review findings to `findings` in place, tagged source=ai_review.

    Best-effort: on any failure the deterministic findings already collected
    remain valid and are returned as-is (never fails the whole report).
    """
    settings = get_settings()
    if not (settings.ai_enabled and rules):
        return
    try:
        ai_client = AzureOpenAIClient(settings)
        rule_summaries = [
            {
                "rule_id": r.rule_id,
                "title": r.title,
                "description": r.description,
                "rule_type": r.rule_type.value,
                "effect": {"type": r.effect.type.value, "action": r.effect.action},
                "scope": r.scope.model_dump(mode="json"),
                "condition": r.condition,
                "ambiguity_status": r.ambiguity_status.value,
            }
            for r in rules
        ]
        user_content = json.dumps(
            {
                "approved_rules": rule_summaries,
                "deterministic_findings_already_found": findings,
            },
            indent=2,
            default=str,
        )
        raw = await ai_client.chat(
            [
                {"role": "system", "content": _AI_REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            deployment=settings.azure_openai_deployment,
            json_mode=True,
            # See openai_client.chat() docstring: gpt-5.6-sol is a reasoning
            # model and needs a generous budget or it returns empty content.
            max_tokens=8000,
            timeout=180.0,
        )
        parsed = json.loads(raw)
        for f in parsed.get("findings", []):
            f["source"] = "ai_review"
            findings.append(f)
    except Exception as exc:  # noqa: BLE001 - deterministic findings remain valid without AI review
        logger.warning("AI quality review failed for %s: %s", policy_set_key, exc)


async def evaluate_policy_set_quality(
    session: AsyncSession,
    *,
    policy_set_key: str,
    use_ai_review: bool = True,
    record_run: bool = True,
    triggered_by: str = "",
) -> dict:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    active = await version_repo.get_active_version(policy_set.id)
    if active is None:
        raise ValueError(f"policy set '{policy_set_key}' has no active approved version")

    package = approved_policy_version_to_package(active)
    rules = package.rules

    candidate_repo = CandidateRuleRepository(session)
    pending_candidates = await candidate_repo.list_by_policy_set(policy_set.id, review_status="candidate")

    findings = _deterministic_findings(rules)
    findings.append(
        {
            "severity": "low",
            "category": "review_backlog",
            "finding": f"{len(pending_candidates)} candidate rule(s) awaiting human review",
            "affected_rule_ids": [],
            "recommendation": "Review the pending candidates in the Review Queue." if pending_candidates else "",
            "source": "deterministic",
        }
    )

    if use_ai_review:
        await _run_ai_review(rules, findings, policy_set_key)

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="published",
            version_number=active.version_number,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=use_ai_review,
            triggered_by=triggered_by,
        )
        await session.commit()
        run_id = str(run.id)

    return {
        "policy_set_key": policy_set_key,
        "scope": "published",
        "version_number": active.version_number,
        "rule_count": len(rules),
        "findings": findings,
        "quality_run_id": run_id,
    }


async def evaluate_candidate_quality(
    session: AsyncSession,
    *,
    policy_set_key: str,
    use_ai_review: bool = True,
    review_statuses: tuple[str, ...] = ("candidate", "approved"),
    record_run: bool = True,
    triggered_by: str = "",
) -> dict:
    """Evaluate quality of AI-extracted candidate rules *before* they are published.

    This lets a reviewer see structural + AI-flagged issues (duplicate ids,
    ambiguity, conflicting effects, gaps, redundancy) on freshly-extracted
    candidates while they are still in the "candidate"/"approved" (unpublished)
    state, instead of only being able to run a quality check after publish.
    Rejected and already-published candidates are excluded by default.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidates = []
    for status in review_statuses:
        candidates.extend(await candidate_repo.list_by_policy_set(policy_set.id, review_status=status))

    rules: list[CanonicalRule] = []
    parse_errors: list[dict] = []
    for c in candidates:
        try:
            rules.append(CanonicalRule.model_validate(c.payload_json))
        except Exception as exc:  # noqa: BLE001 - a bad candidate shouldn't abort the whole report
            parse_errors.append(
                {
                    "severity": "high",
                    "category": "invalid_candidate_payload",
                    "finding": f"Candidate rule '{c.id}' failed schema validation: {exc}",
                    "affected_rule_ids": [str(c.id)],
                    "recommendation": "Reject or manually correct this candidate; it cannot be published as-is.",
                    "source": "deterministic",
                }
            )

    findings = _deterministic_findings(rules) + parse_errors

    if use_ai_review:
        await _run_ai_review(rules, findings, policy_set_key)

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="candidates",
            version_number=None,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=use_ai_review,
            triggered_by=triggered_by,
        )
        await session.commit()
        run_id = str(run.id)

    return {
        "policy_set_key": policy_set_key,
        "scope": "candidates",
        "version_number": None,
        "rule_count": len(rules),
        "candidate_statuses_included": list(review_statuses),
        "findings": findings,
        "quality_run_id": run_id,
    }
