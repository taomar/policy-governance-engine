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
from policy_platform.infrastructure.formulation_mapping import _is_separator_predicate
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    CandidateRuleRepository,
    PolicySetRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

QUALITY_METHODOLOGY_VERSION = "2"

_AI_REVIEW_SYSTEM_PROMPT = """You are a senior policy analyst reviewing a versioned package of formalized \
governance rules. Deterministic structural findings are supplied separately. Identify only ADDITIONAL \
qualitative issues that require human judgment: reachable decision gaps, overlapping rules with competing \
outcomes and no precedence, material ambiguity, missing exception handling, unsafe governance boundaries, \
or consequential redundancy.

Accuracy rules:
1. Treat every issue as a POTENTIAL quality finding requiring human confirmation, not as a proven defect.
2. For a conflict, name the concrete input/state in which the affected rules can both apply, the outcome \
each rule directs, and why scope, effective dates, priority, explicit overrides, or supersession do not \
already resolve it.
3. For a gap, name the exact reachable boundary or workflow state left without an outcome and the adjacent \
rules that create the boundary.
4. Do not report a conflict when scopes or effective windows do not overlap, or when explicit precedence \
already identifies the controlling rule.
5. Do not infer laws, controls, or business requirements that are absent from the supplied policy package. \
You may report them as risks to confirm, never as violated requirements.
6. Do not repeat deterministic findings. Do not fabricate or alter rule IDs.
7. Explain the evaluator or operational failure mode, what would make the current state acceptable, what \
would make it unacceptable, and the specific questions a reviewer must answer.

Respond with one JSON object:
{"findings": [{
  "severity": "high"|"medium"|"low",
  "category": "snake_case",
  "summary": "one plain-language sentence",
  "finding": "specific evidence-based explanation naming the interaction and concrete boundary/state",
  "why_it_matters": "the evaluator, control, audit, or user consequence if confirmed",
  "acceptable_when": "the factual condition under which no policy change is required",
  "unacceptable_when": "the factual condition under which remediation is required",
  "review_questions": ["specific decision question", "..."],
  "affected_rule_ids": ["only IDs supplied in the input"],
  "recommendation": "smallest policy correction that closes the issue"
}]}

If there is no additional evidence-based issue, return {"findings": []}."""


def _quality_rule_context(rule: CanonicalRule) -> dict:
    """Decision-grade, bounded context for the qualitative review.

    Sending only title/description/condition made the model blind to the exact
    precedence and lifecycle fields it was expected to reason about. This keeps
    the payload bounded while including every field that can prove or disprove an
    overlap, gap, or exception claim.
    """
    formulation = getattr(rule, "formulation", None)
    canonical = getattr(formulation, "canonical", None)
    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "description": rule.description,
        "source_text": getattr(canonical, "source_text", "") if canonical else "",
        "rule_type": rule.rule_type.value,
        "effect": rule.effect.model_dump(mode="json"),
        "condition": rule.condition.model_dump(mode="json"),
        "scope": rule.scope.model_dump(mode="json"),
        "exceptions": [item.model_dump(mode="json") for item in rule.exceptions],
        "required_facts": [item.model_dump(mode="json") for item in rule.required_facts],
        "priority": rule.priority,
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
        "machine_executable": rule.machine_executable,
        "ambiguity_status": rule.ambiguity_status.value,
        "is_explicit_override": rule.is_explicit_override,
        "supersedes_rule_ids": list(rule.supersedes_rule_ids),
        "related_rule_ids": list(rule.related_rule_ids),
    }


def _normalize_ai_finding(raw: object, valid_rule_ids: set[str]) -> dict | None:
    """Validate one model finding before it becomes immutable quality evidence."""
    if not isinstance(raw, dict):
        return None

    severity = raw.get("severity")
    if severity not in {"high", "medium", "low"}:
        return None

    finding = str(raw.get("finding") or "").strip()
    if not finding:
        return None

    raw_references = raw.get("affected_rule_ids")
    if raw_references is not None and not isinstance(raw_references, list):
        logger.warning("Discarding AI quality finding with malformed rule references: %r", raw_references)
        return None
    references = raw_references if isinstance(raw_references, list) else []
    requested_ids = [str(value).strip() for value in references if str(value).strip()]
    unsupported_ids = [rule_id for rule_id in requested_ids if rule_id not in valid_rule_ids]
    if unsupported_ids:
        logger.warning("Discarding AI quality finding with unsupported rule references: %s", requested_ids)
        return None
    affected_rule_ids = list(dict.fromkeys(requested_ids))

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        summary = finding.split(".", 1)[0].strip()

    review_questions = raw.get("review_questions")
    questions = (
        [str(value).strip() for value in review_questions if str(value).strip()][:6]
        if isinstance(review_questions, list)
        else []
    )

    return {
        "severity": severity,
        "category": str(raw.get("category") or "qualitative_risk").strip() or "qualitative_risk",
        "summary": summary[:500],
        "finding": finding[:4000],
        "why_it_matters": str(raw.get("why_it_matters") or "").strip()[:2000],
        "acceptable_when": str(raw.get("acceptable_when") or "").strip()[:2000],
        "unacceptable_when": str(raw.get("unacceptable_when") or "").strip()[:2000],
        "review_questions": questions,
        "affected_rule_ids": affected_rule_ids,
        "recommendation": str(raw.get("recommendation") or "").strip()[:3000],
        "analysis_status": "requires_human_confirmation",
        "source": "ai_review",
    }


def _mark_deterministic_findings(findings: list[dict]) -> None:
    for finding in findings:
        if finding.get("source") == "deterministic":
            finding.setdefault("analysis_status", "confirmed")


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
    findings.extend(_definition_effect_findings(rules))
    findings.extend(_degenerate_predicate_findings(rules))
    findings.extend(_eligibility_polarity_findings(rules))

    return findings


def _definition_effect_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report definitions that carry an authorization effect.

    A definition establishes vocabulary; it authorizes nothing. `EffectType`
    used to offer only allow/deny/require_action, so `_RULE_TYPE_MAP` had
    nowhere truthful to send `definition` and sent it to `allow`. The rule
    then asserted a permission its source never granted.

    That was not merely untidy, because a definition is often phrased
    negatively. Observed in the Saudi Labor Law extraction: "The periods
    designated for rest, prayers, and meals SHALL NOT BE INCLUDED in the
    actual working hours" became `allow: "be included in the actual working
    hours"` — the exact inverse of the source. Two separate AI reviews
    reported this as two findings ("definitions modeled with allow effects"
    and "semantic polarity errors"); they are one defect, and the polarity
    reversal is the symptom rather than the cause.

    Severity distinguishes latent from active, because the difference is real.
    While a definition stays non-executable the evaluator returns NOT_APPLICABLE
    and nothing acts on the false permission. Supplying a `trusted_config` is
    what makes a rule executable, so the first config that covers a definition's
    vocabulary is also what turns this from a labelling error into an evaluator
    returning ALLOW for text that says "shall not".

    `EffectType.INFORMATIONAL` now exists precisely for this case, and
    `_RULE_TYPE_MAP` sends `definition`/`classification` there instead of
    `allow` — see `formulation_mapping.py`. This check stays, unchanged, as a
    regression/backfill guard: rows extracted (or mapped) before that fix,
    or any future rule_type wrongly routed to allow/deny, still surface here
    at the review boundary rather than being approved unnoticed.
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
            f"{len(executable)} of them are evaluated by comparison, so the evaluator can "
            f"already return that effect for text that may say the opposite."
        )
    else:
        exposure = (
            "None of them are evaluated by comparison, so nothing acts on the effect "
            "today — a judge reading the record would see the effect beside a "
            "definition that authorizes nothing."
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
                "New extraction maps definition/classification rules to the neutral "
                "informational effect. Re-extract or safely backfill these legacy rows "
                "before any trusted_config can make them executable, and keep this "
                "finding as a regression guard."
            ),
            "source": "deterministic",
        }
    ]


def _eligibility_polarity_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report `eligibility`-type rules whose `deny` effect names a grant, not a loss.

    Observed in the Saudi Labor Law extraction: six rules titled "... shall be
    exempted from the implementation of the provisions of this Law" were
    formulated with `rule_type: eligibility`, `effect.type: "deny"`,
    `effect.action: "be exempted from the implementation of the provisions of
    this Law"`. `effect.type` and `effect.action` are read together as one
    sentence by the evaluator (`_apply_combining_algorithm` puts a satisfied
    `deny` rule's action straight into `denied_actions`), so this reads as
    "denied: be exempted..." — i.e. the Law's provisions DO apply — the
    literal opposite of the source, which grants the exemption.

    Root cause: the single `RuleType.ELIGIBILITY` schema value covers both
    directions via the AI-facing `CanonicalRuleType.ELIGIBILITY` (→ `allow`)
    and `.INELIGIBILITY` (→ `deny`) in `_RULE_TYPE_MAP`. The formulator picked
    `ineligibility` for a grant-shaped exemption because the prompt's own
    worked example (fixed alongside this check) told it to. See
    policy_formulator_v1.md Section 14/15.1 (POLARITY TEST) for the
    GRANT-SHAPED vs. LOSS-SHAPED negation heuristic this guards against
    regressing.

    This is a structural, keyword-based heuristic (grant-shaped verbs paired
    with a `deny` effect), not a semantic proof: it can miss an inversion
    phrased without any of these verbs, and could in principle false-positive
    on a genuinely-intended denial that happens to reuse one of these words.
    It exists as a regression/backfill guard, the same way
    `_definition_effect_findings` guards its own polarity defect: rows
    formulated before the prompt fix, or any future slip, still surface here
    at the review boundary rather than being approved unnoticed.
    """

    grant_shaped_markers = (
        "exempt",
        "excus",
        "immune",
        "not subject to",
        "not bound by",
        "released from",
        "relieved of",
        "waived",
    )
    offenders = [
        r
        for r in rules
        if r.rule_type.value == "eligibility"
        and r.effect.type.value == "deny"
        and any(marker in r.effect.action.lower() for marker in grant_shaped_markers)
    ]
    if not offenders:
        return []

    return [
        {
            "severity": "high",
            "category": "eligibility_polarity_inversion",
            "finding": (
                f"{len(offenders)} eligibility rule(s) have effect.type='deny' but "
                f"effect.action names a grant (e.g. an exemption/release from a "
                f"burden), which reads as denying that grant — the opposite of what "
                f"the source establishes."
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Re-run formulation for these rules (or edit them manually) so a "
                "grant-shaped outcome (an exemption, a release from a burden) is "
                "classified eligibility/allow, not ineligibility/deny. See "
                "policy_formulator_v1.md Section 15.1 (POLARITY TEST)."
            ),
            "source": "deterministic",
        }
    ]


def _degenerate_predicate_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report rules whose canonical predicate is punctuation, not a relationship.

    Observed in the Saudi Labor Law extraction: a definition sourced from
    "Minor: Any person of 15 and below 18 years of age" was formulated with
    `predicate: ":"` — the source's own delimiter, echoed back as though it
    were the semantic relationship between subject and object, instead of
    being resolved to a copula such as "is defined as" (see the formulator
    prompt's Section 19.2). A predicate with no alphanumeric characters can
    never be a real relationship; that is always a decomposition slip, not a
    property of the source text, so this stays as a regression/backfill
    guard the same way `_definition_effect_findings` guards its own defect —
    rows formulated before the prompt fix, or any future slip, still surface
    here rather than being approved unnoticed.

    Reuses `formulation_mapping._is_separator_predicate` — the same
    punctuation-only test that already makes `_title_for`/`_effect_action`
    skip a degenerate predicate when building display strings — so "what
    counts as degenerate" has exactly one definition. That existing helper
    only cleans the *derived* title/effect text; it doesn't fix or report on
    the underlying stored `predicate` field itself, which is what this
    finding surfaces to reviewers.
    """

    offenders = []
    for r in rules:
        canonical = getattr(getattr(r, "formulation", None), "canonical", None)
        predicate = getattr(getattr(canonical, "rule", None), "predicate", None)
        if predicate is not None and _is_separator_predicate(predicate):
            offenders.append(r)

    if not offenders:
        return []

    return [
        {
            "severity": "medium",
            "category": "degenerate_predicate",
            "finding": (
                f"{len(offenders)} rule(s) have a predicate that is empty or pure punctuation "
                f'(e.g. ":"), echoing the source\'s delimiter instead of naming the '
                f"subject/object relationship."
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Re-run formulation for these rules (or edit them manually) so the predicate "
                'names the relationship in words (e.g. "is defined as", "means", "shall submit") '
                "rather than repeating source punctuation."
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
        rule_summaries = [_quality_rule_context(rule) for rule in rules]
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
        if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
            raise ValueError("AI quality review did not return a findings array")
        valid_rule_ids = {rule.rule_id for rule in rules}
        for raw_finding in parsed["findings"]:
            normalized = _normalize_ai_finding(raw_finding, valid_rule_ids)
            if normalized is not None:
                findings.append(normalized)
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
    _mark_deterministic_findings(findings)

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="published",
            version_number=active.version_number,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
            methodology_version=QUALITY_METHODOLOGY_VERSION,
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
        "methodology_version": QUALITY_METHODOLOGY_VERSION,
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
    _mark_deterministic_findings(findings)

    run_id = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="candidates",
            version_number=None,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
            methodology_version=QUALITY_METHODOLOGY_VERSION,
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
        "methodology_version": QUALITY_METHODOLOGY_VERSION,
    }
