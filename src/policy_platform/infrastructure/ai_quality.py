"""Policy quality evaluation: deterministic structural checks + an AI
qualitative review layered on top, clearly labeled by provenance.

This is the "are these policies actually any good?" feature. Findings are
tagged `source: "deterministic"` (always exact — computed by inspecting the
persisted rule set with plain code, no LLM involved) or `source: "ai_review"`
(the model's judgment about gaps/redundancy/ambiguous wording — genuinely
useful, but not infallible, and never silently presented as fact).
"""
from __future__ import annotations

import collections
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
        if r.ambiguity_status.value == "blocking":
            findings.append(
                {
                    "severity": "high",
                    "category": "ambiguity",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) has ambiguity_status=blocking",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "Have a human reviewer formalize this rule's condition/wording before relying on it in automated evaluation.",
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

    findings.extend(_non_blocking_ambiguity_findings(rules))
    findings.extend(_machine_executability_findings(rules))
    findings.extend(_definition_effect_findings(rules))

    return findings


def _definition_effect_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report definitions that carry an authorization effect.

    A definition establishes vocabulary; it authorizes nothing. `EffectType`
    offers only allow/deny/require_action, so `_RULE_TYPE_MAP` has nowhere
    truthful to send `definition` and sends it to `allow`. The rule then asserts
    a permission its source never granted.

    That is not merely untidy, because a definition is often phrased negatively.
    Observed in the Saudi Labor Law extraction: "The periods designated for
    rest, prayers, and meals SHALL NOT BE INCLUDED in the actual working hours"
    became `allow: "be included in the actual working hours"` — the exact
    inverse of the source. Two separate AI reviews reported this as two findings
    ("definitions modeled with allow effects" and "semantic polarity errors");
    they are one defect, and the polarity reversal is the symptom rather than
    the cause.

    Severity distinguishes latent from active, because the difference is real.
    While a definition stays non-executable the evaluator returns NOT_APPLICABLE
    and nothing acts on the false permission. Supplying a `trusted_config` is
    what makes a rule executable, so the first config that covers a definition's
    vocabulary is also what turns this from a labelling error into an evaluator
    returning ALLOW for text that says "shall not".

    Reported here rather than fixed in the mapping deliberately: a truthful
    effect needs a fourth `EffectType`, which changes a published contract, the
    evaluator's outcome vocabulary and the effect badges in the UI. That is a
    design decision, not a defect fix. Surfacing it at the review boundary
    stops the rules being approved unnoticed in the meantime, which is what the
    review stage exists for.
    """

    offenders = [
        r
        for r in rules
        if r.rule_type.value == "definition" and r.effect.type.value in {"allow", "deny"}
    ]
    if not offenders:
        return []

    executable = [r for r in offenders if r.machine_executable]
    by_effect = collections.Counter(r.effect.type.value for r in offenders)
    effects = ", ".join(f"{name} ({count})" for name, count in by_effect.most_common())

    if executable:
        exposure = (
            f"{len(executable)} of them are machine-executable, so the evaluator can "
            f"already return that effect for text that may say the opposite."
        )
    else:
        exposure = (
            "None are machine-executable yet, so the evaluator returns not_applicable "
            "and nothing acts on the effect today. Supplying a trusted_config that "
            "covers their vocabulary is what would activate it."
        )

    return [
        {
            "severity": "high" if executable else "medium",
            "category": "definition_carries_effect",
            "finding": (
                f"{len(offenders)} definition rule(s) carry an authorization effect "
                f"[{effects}]. A definition establishes vocabulary and authorizes "
                f"nothing, and where its source is phrased negatively the effect "
                f"states the inverse of the text. {exposure}"
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Check these against their source text first: a definition whose "
                "wording is negative ('shall not be included', 'may not be deemed') "
                "now reads as a permission to do the thing the source excludes. "
                "The effect vocabulary has no neutral member, so a durable fix means "
                "adding one to EffectType and deciding what the evaluator returns for "
                "a definitional rule — a contract change worth making before any "
                "trusted_config lets these become executable."
            ),
            "source": "deterministic",
        }
    ]


def _non_blocking_ambiguity_findings(rules: list[CanonicalRule]) -> list[dict]:
    """One finding for the non-blocking ambiguity backlog, not one per rule.

    A per-rule finding is right when each row needs its own decision. Ambiguity
    that the extractor flagged for human judgment is a queue with a known size,
    and emitting one row per rule pushes genuinely distinct problems (duplicate
    ids, conflicting effects) off the end of a report that is read top-down.
    """
    flagged = [r for r in rules if r.ambiguity_status.value not in ("none", "blocking")]
    if not flagged:
        return []
    by_status = collections.Counter(r.ambiguity_status.value for r in flagged)
    breakdown = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    return [
        {
            "severity": "medium",
            "category": "ambiguity",
            "finding": (
                f"{len(flagged)} of {len(rules)} rule(s) need human judgment on wording ({breakdown})."
            ),
            "affected_rule_ids": [r.rule_id for r in flagged],
            "recommendation": (
                "Work these through the Review Queue. This records that the source wording needs a "
                "human decision — it is not an extraction failure."
            ),
            "source": "deterministic",
        }
    ]


def _machine_executability_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report non-executable rules by *cause*, and name the enrichment that unblocks them.

    Every rule whose DMN projection was not `executable` is non-executable, and
    when no trusted configuration was supplied that is every rule in the set --
    one systemic cause, not N independent defects. Reporting it per rule states
    the symptom N times and never states the cause, so the reader is left to
    infer that N rules were each extracted badly.

    The agent already said precisely what it was missing, as
    `DmnRequirementCode`s whose stated purpose is to make `enrichment_required`
    "actionable rather than a dead end" (contracts.formulation). Those codes are
    the actionable part of this finding, so they are surfaced here rather than
    left in the payload.
    """
    blocked = [r for r in rules if not r.machine_executable]
    if not blocked:
        return []

    requirements: collections.Counter[str] = collections.Counter()
    statuses: collections.Counter[str] = collections.Counter()
    for r in blocked:
        formulation = getattr(r, "formulation", None)
        for decision in getattr(formulation, "dmn_decisions", None) or []:
            statuses[getattr(decision.dmn_mapping_status, "value", str(decision.dmn_mapping_status))] += 1
            for code in decision.requirements or []:
                requirements[getattr(code, "value", str(code))] += 1

    share = f"{len(blocked)} of {len(rules)}"
    if requirements:
        top = ", ".join(f"{code} ({count})" for code, count in requirements.most_common(6))
        finding = (
            f"{share} rule(s) are not machine-executable. The formulation agent reported what it "
            f"was missing: {top}."
        )
        recommendation = (
            "These are not extraction defects. Supply the matching trusted configuration when "
            "extracting and re-run. Shape it as the specification's Section 84 example: key "
            "fact_model/output_model by the SOURCE TERM with a feel_expression mapping "
            '(e.g. {"age of the worker": {"feel_expression": "worker.ageYears", "type": "number"}}). '
            "Keying by the FEEL path instead is accepted silently but leaves the agent unable to "
            "connect source wording to the path, so it still reports FACT_MODEL_REQUIRED."
        )
        severity = "high"
    else:
        # No requirement codes at all: the rules did not come through the
        # formulation path, so there is nothing specific to ask for.
        finding = f"{share} rule(s) are not machine-executable and carry no DMN enrichment requirements."
        recommendation = "These rules need a precise condition before the evaluator can enforce them."
        severity = "medium"

    if statuses:
        finding += " DMN mapping status: " + ", ".join(
            f"{status} ({count})" for status, count in statuses.most_common()
        )

    return [
        {
            "severity": severity,
            "category": "not_machine_executable",
            "finding": finding,
            "affected_rule_ids": [r.rule_id for r in blocked],
            "recommendation": recommendation,
            "source": "deterministic",
        }
    ]


async def _run_ai_review(rules: list[CanonicalRule], findings: list[dict], policy_set_key: str) -> bool:
    """Append AI-review findings to `findings` in place, tagged source=ai_review.

    Best-effort: on any failure the deterministic findings already collected
    remain valid and are returned as-is (never fails the whole report).

    Returns True only when the review actually ran to completion. Callers must
    record *this* rather than the flag they passed in: a failed review produces
    a report with fewer findings, which reads as a cleaner policy set unless the
    report says the review never happened. When the review was expected and did
    not run, a finding is appended so the gap is visible in the report itself
    and not only in the server log.
    """
    settings = get_settings()
    if not rules:
        return False
    if not settings.ai_enabled:
        findings.append(
            {
                "severity": "medium",
                "category": "review_coverage",
                "finding": "AI review was requested but AI is disabled, so only deterministic checks ran.",
                "affected_rule_ids": [],
                "recommendation": "Enable AI to get ambiguity, conflict and gap findings.",
                "source": "deterministic",
            }
        )
        return False
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
        return True
    except Exception as exc:  # noqa: BLE001 - deterministic findings remain valid without AI review
        logger.warning("AI quality review failed for %s: %s", policy_set_key, exc)
        findings.append(
            {
                "severity": "medium",
                "category": "review_coverage",
                "finding": f"AI review did not complete, so only deterministic checks ran: {exc}",
                "affected_rule_ids": [],
                "recommendation": (
                    "Re-run the evaluation. If this repeats on a large policy set, the review sends every "
                    "rule in one request and may be exceeding the model's context window."
                ),
                "source": "deterministic",
            }
        )
        return False


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
        ai_review_used = await _run_ai_review(rules, findings, policy_set_key)
    else:
        ai_review_used = False

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="published",
            version_number=active.version_number,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
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
        ai_review_used = await _run_ai_review(rules, findings, policy_set_key)
    else:
        ai_review_used = False

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="candidates",
            version_number=None,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
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
