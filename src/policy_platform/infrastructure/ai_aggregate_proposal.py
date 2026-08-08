"""AI-assisted discovery of rule groups that should share a combined cap.

The job this does is *discovery*, which is the part a human is genuinely bad
at: spotting that three separately-authored leave rules are really drawing on
one shared annual ceiling. It does not decide eligibility and it does not
decide whether the limit is correct — see below.

Design, mirroring `ai_test_proposal.py`'s "AI drafts, deterministic code and
human review decide":

- **Eligibility is computed first, deterministically**, by
  `aggregate_eligibility.assess_rules`, and only eligible rules are ever shown
  to the model. This is not a token optimisation. A rule is eligible only if the
  evaluator could actually count it, and both failure modes are silent (see that
  module's docstring). Letting the model nominate contributors would let it
  invent an `amount_fact` that scores zero forever while looking perfectly
  reasonable in the UI.
- **Every proposal is re-validated against real data** after the model replies:
  each `rule_id` must be in the eligible set, and each `amount_fact` must be one
  of *that rule's own* declared numeric facts. A proposal that fails is skipped
  with a reason rather than silently repaired, because a repaired grouping is no
  longer the grouping the model justified.
- **Nothing is persisted here.** This returns proposals; the reviewer previews
  and saves them. An aggregate limit changes evaluation outcomes for every
  future request against the policy set, so it is not something an AI call
  should be able to bring into existence on its own.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.aggregate_eligibility import EligibilityReport, assess_rules
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    PolicySetRepository,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-aggregate-proposal-v1"

VALID_REASONING_EFFORTS = ("low", "medium", "high")

#: A combined cap needs at least two contributors to mean anything — a cap over
#: one rule is that rule's own threshold and belongs in its condition.
MIN_CONTRIBUTORS = 2

_SYSTEM_PROMPT = """You are a policy analyst looking for CROSS-RULE COMBINED CAPS in an approved policy set.

A combined cap (OMG DMN "Collect" hit policy with a SUM aggregator) exists when several separate rules each \
grant or consume some amount of the SAME underlying finite resource, and the real-world policy limits their \
COMBINED total — not just each rule individually. The classic example is statutory leave: a rule granting 60 \
days for one reason and another granting 15 days/year for a different reason, where the law also says the two \
together may not exceed 70 days in a year. Each rule is correct on its own; only together do they need a \
ceiling, and no single rule can express that because no rule can see another rule's outcome.

You are given ONLY the rules that are already technically capable of contributing to a cap. Each one lists its \
`numeric_facts`: the exact declared fact names whose values the evaluator is able to sum. You MUST choose \
`amount_fact` from that rule's own `numeric_facts` list. Never invent a fact name, never borrow one from a \
different rule, and never reference a rule_id that was not given to you — a wrong fact name makes the cap \
silently count zero forever.

Only propose a group when the rules genuinely draw on one shared, finite pool. Do NOT group rules merely \
because they are the same rule_type, sit in the same category, or happen to use similarly-named numeric facts. \
Two unrelated monetary limits are not a combined cap. If the rules do not justify any grouping, return an \
empty list — that is a correct and useful answer, and far better than an invented one.

For `max_value`, prefer a ceiling actually stated or clearly implied by the rules' own text. If the rules \
establish that a shared ceiling exists but never state its number, still propose the group, set \
`max_value_confidence` to "unstated" and put your best defensible figure in `max_value` so the reviewer has \
something concrete to correct. Set `max_value_confidence` to "stated" only when a number really is present in \
the source text.

`period` is the window the cap resets over ("year", "quarter", "month", "rolling-12-months") or null if the cap \
is a lifetime or per-case total.

Respond with a JSON object:
{"groups": [ {
  "aggregate_key": short stable kebab-case slug, e.g. "combined-annual-leave-cap",
  "description": one or two sentences a policy reviewer can check, naming the shared resource and the ceiling,
  "rationale": why these specific rules draw on ONE pool - cite the rules' own wording,
  "max_value": number,
  "max_value_confidence": "stated" | "unstated",
  "period": string or null,
  "contributing_rules": [ {"rule_id": str, "amount_fact": str, "why": short reason this rule consumes the pool} ]
} ]}
Every group must contain at least two contributing rules. If nothing qualifies, return {"groups": []}."""


def _rule_summary(eligibility) -> dict:
    """What the model is allowed to see: identity, meaning, and the exact set of
    fact names it may choose from. `numeric_facts` is the closed vocabulary for
    `amount_fact` — anything outside it is rejected in validation below."""

    return {
        "rule_id": eligibility.rule_id,
        "title": eligibility.title,
        "numeric_facts": [{"name": f.name, "data_type": f.data_type} for f in eligibility.numeric_facts],
    }


def _enrich_summaries(report: EligibilityReport, rules_by_id: dict) -> list[dict]:
    """Add the prose the model needs to judge whether a pool is really shared.

    Eligibility alone cannot answer "is this the same resource?" — that lives in
    the rule's description and effect, so both are included for eligible rules.
    """

    summaries = []
    for elig in report.eligible:
        summary = _rule_summary(elig)
        rule = rules_by_id.get(elig.rule_id)
        if rule is not None:
            summary["description"] = rule.description
            summary["rule_type"] = rule.rule_type.value
            summary["category"] = rule.category
            summary["effect"] = rule.effect.model_dump(mode="json")
        summaries.append(summary)
    return summaries


def _validate_group(raw: dict, allowed: dict[str, set[str]]) -> tuple[dict | None, str | None]:
    """Return (validated_group, None) or (None, skip_reason). Never raises.

    `allowed` maps rule_id -> the set of numeric fact names declared by *that*
    rule. Both halves are enforced: an unknown rule_id and a fact borrowed from
    a different rule are equally capable of producing a cap that never fires.
    """

    key = str(raw.get("aggregate_key") or "").strip()
    if not key:
        return None, "group missing 'aggregate_key'"

    max_value = raw.get("max_value")
    if not isinstance(max_value, (int, float)) or isinstance(max_value, bool):
        return None, f"group '{key}': 'max_value' must be a number"
    if max_value <= 0:
        return None, f"group '{key}': 'max_value' must be greater than zero"

    raw_contributions = raw.get("contributing_rules")
    if not isinstance(raw_contributions, list):
        return None, f"group '{key}': 'contributing_rules' must be a list"

    contributions: list[dict] = []
    seen: set[str] = set()
    for item in raw_contributions:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "").strip()
        amount_fact = str(item.get("amount_fact") or "").strip()
        if rule_id not in allowed:
            return None, f"group '{key}': rule '{rule_id}' is not an eligible rule in this version"
        if amount_fact not in allowed[rule_id]:
            return None, (
                f"group '{key}': '{amount_fact}' is not a declared numeric fact of rule "
                f"'{rule_id}' (allowed: {sorted(allowed[rule_id]) or 'none'})"
            )
        if rule_id in seen:
            # Two contributions from one rule would double-count that rule's
            # amount against the shared cap.
            return None, f"group '{key}': rule '{rule_id}' listed more than once"
        seen.add(rule_id)
        contributions.append(
            {"rule_id": rule_id, "amount_fact": amount_fact, "why": str(item.get("why") or "")}
        )

    if len(contributions) < MIN_CONTRIBUTORS:
        return None, (
            f"group '{key}': needs at least {MIN_CONTRIBUTORS} contributing rules, got {len(contributions)}"
        )

    confidence = str(raw.get("max_value_confidence") or "").strip().lower()
    if confidence not in {"stated", "unstated"}:
        confidence = "unstated"

    period = raw.get("period")
    period = str(period).strip() if isinstance(period, str) and period.strip() else None

    return {
        "aggregate_key": key,
        "description": str(raw.get("description") or ""),
        "rationale": str(raw.get("rationale") or ""),
        "max_value": float(max_value),
        "max_value_confidence": confidence,
        "period": period,
        "aggregator": "SUM",
        "contributing_rules": contributions,
    }, None


async def propose_aggregate_limits(
    session: AsyncSession, *, policy_set_key: str, reasoning_effort: str = "medium", guidance: str = ""
) -> dict:
    """Discover candidate combined caps in a policy set's active version.

    Returns the deterministic eligibility report alongside any AI proposals, so
    the caller can explain an empty result. "No proposals" and "no rule in this
    version can contribute to a cap at all" look identical to a reviewer, and
    they need completely different actions.

    `guidance` is an optional reviewer steer, passed as user content so it can
    bias what the model looks for without redefining the output contract or the
    validation applied to every proposal.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        reasoning_effort = "medium"

    policy_set = await PolicySetRepository(session).get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    active = await ApprovedPolicyVersionRepository(session).get_active_version(policy_set.id)
    if active is None:
        raise ValueError(
            f"policy set '{policy_set_key}' has no active approved version to look for combined caps in"
        )

    package = approved_policy_version_to_package(active)
    report = assess_rules(list(package.rules))
    base_result = {
        "policy_set_key": policy_set_key,
        "version_number": active.version_number,
        "reasoning_effort": reasoning_effort,
        "prompt_version": PROMPT_VERSION,
        "eligibility": report.to_dict(),
        "proposals": [],
        "skipped": [],
    }

    # Short-circuit before spending a model call on a question with only one
    # possible answer. This is also the branch that fires for every policy set
    # today, so it has to explain itself properly rather than just returning [].
    if not report.can_build_limit:
        base_result["skipped"] = [
            (
                f"{report.eligible and len(report.eligible) or 0} of {len(report.rules)} rules in this "
                f"version can contribute to a combined cap; at least {MIN_CONTRIBUTORS} are required."
            )
        ]
        return base_result

    rules_by_id = {r.rule_id: r for r in package.rules}
    allowed = {e.rule_id: {f.name for f in e.numeric_facts} for e in report.eligible}

    request_payload: dict = {"eligible_rules": _enrich_summaries(report, rules_by_id)}
    steer = guidance.strip()
    if steer:
        request_payload["reviewer_guidance"] = steer

    ai_client = AzureOpenAIClient(settings)
    raw = await ai_client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(request_payload, indent=2, default=str)},
        ],
        deployment=settings.azure_openai_deployment,
        json_mode=True,
        max_tokens=8000,
        timeout=180.0,
        reasoning_effort=reasoning_effort,
    )

    parsed = json.loads(raw)
    groups = parsed.get("groups") or []
    if not isinstance(groups, list):
        groups = []

    proposals: list[dict] = []
    skipped: list[str] = []
    used_keys: set[str] = set()
    for item in groups:
        if not isinstance(item, dict):
            skipped.append("proposal was not an object")
            continue
        validated, reason = _validate_group(item, allowed)
        if validated is None:
            skipped.append(reason or "invalid proposal")
            continue
        # Distinct keys matter: `aggregate_key` is the unique identifier per
        # policy set, so two proposals sharing one would make the second
        # un-saveable without the reviewer understanding why.
        if validated["aggregate_key"] in used_keys:
            skipped.append(f"duplicate aggregate_key '{validated['aggregate_key']}'")
            continue
        used_keys.add(validated["aggregate_key"])
        proposals.append(validated)

    base_result["proposals"] = proposals
    base_result["skipped"] = skipped
    logger.info(
        "aggregate limit discovery for '%s': %d eligible rules, %d proposals, %d skipped",
        policy_set_key,
        len(report.eligible),
        len(proposals),
        len(skipped),
    )
    return base_result
