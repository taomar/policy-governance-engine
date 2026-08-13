"""Deterministic preview of a *draft* aggregate limit, before it is saved.

The whole reason aggregate limits felt meaningless was that you authored one
blind: you picked rules and a fact name, saved, published, and only then found
out whether it did anything. Usually it did nothing, silently (see
`aggregate_eligibility` for the two ways that happens).

This module answers "what would this cap actually do?" *before* the reviewer
commits to it.

The one design rule that matters here: **the preview runs the real evaluator.**
It builds the candidate `AggregateLimit`, splices it into the active published
package, and calls `evaluate_policy`. It never re-implements
`_evaluate_aggregate_limits`' arithmetic. A preview that reimplemented the sum
would be a second source of truth about the cap, free to drift from the engine
and to reassure the reviewer about behaviour that never happens — which is the
exact failure this feature already had.

Nothing here mutates anything. The spliced package is an in-memory copy.
"""
from __future__ import annotations

from dataclasses import dataclass

from policy_platform.contracts.evaluation import EvaluationRequest, EvaluationStatus
from policy_platform.contracts.policy import (
    AggregateLimit,
    AggregateLimitContribution,
    ApprovedPolicyPackage,
)
from policy_platform.evaluator.engine import evaluate_policy

#: Key used for the spliced-in draft. Prefixed so it cannot collide with a real
#: saved aggregate_key and so it is obvious in any log line that this was a
#: preview rather than a published cap.
PREVIEW_AGGREGATE_ID = "__preview__"


@dataclass(frozen=True)
class ContributionOutcome:
    """What one contributing rule did during the preview evaluation."""

    rule_id: str
    amount_fact: str
    rule_status: str
    contributed: bool
    amount: float | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "amount_fact": self.amount_fact,
            "rule_status": self.rule_status,
            "contributed": self.contributed,
            "amount": self.amount,
            "reason": self.reason,
        }


def _explain(
    status: EvaluationStatus | None, overridden_by: str | None, amount: object | None
) -> tuple[bool, str]:
    """Why a contribution counted or did not, in the engine's own terms.

    Mirrors the order of the checks in `_evaluate_aggregate_limits` so the
    explanation names the *first* thing that stopped the contribution, which is
    the one the reviewer has to fix.
    """

    if status is None:
        return False, "The rule was not evaluated in this version."
    if status != EvaluationStatus.SATISFIED:
        return False, (
            f"The rule returned {status.value}, and only a SATISFIED rule contributes to a cap."
        )
    if overridden_by:
        return False, f"The rule was satisfied but overridden by '{overridden_by}', so it does not contribute."
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return False, (
            "No numeric value was supplied for this fact, so the evaluator counts it as nothing. "
            "This is the silent-zero case: the cap looks configured but never adds this rule up."
        )
    return True, "Satisfied, not overridden, and a numeric amount was supplied."


def preview_aggregate_limit(
    package: ApprovedPolicyPackage,
    *,
    contributing_rules: list[dict],
    max_value: float,
    facts: dict[str, object | None],
    description: str = "",
) -> dict:
    """Evaluate `facts` against `package` with a draft cap spliced in.

    Returns the per-rule breakdown, the engine-computed total, and whether the
    cap was breached — all read back out of the real `EvaluationResponse` rather
    than recomputed here.
    """

    contributions = [
        AggregateLimitContribution(rule_id=c["rule_id"], amount_fact=c["amount_fact"])
        for c in contributing_rules
    ]
    draft = AggregateLimit(
        aggregate_id=PREVIEW_AGGREGATE_ID,
        description=description or "Draft aggregate limit preview",
        contributing_rules=contributions,
        aggregator="SUM",
        max_value=max_value,
    )

    # `model_copy` keeps the published package untouched; only the copy carries
    # the draft cap, and only for the duration of this call.
    preview_package = package.model_copy(
        update={"aggregate_limits": [*package.aggregate_limits, draft]}
    )

    response = evaluate_policy(
        preview_package,
        EvaluationRequest(
            policy_set_id=package.policy_set_id,
            policy_version_id=package.policy_version_id,
            use_active_version=False,
            facts=facts,
        ),
    )

    results_by_id = {r.rule_id: r for r in response.rule_results}
    outcomes: list[ContributionOutcome] = []
    counted_total = 0.0
    for contribution in contributions:
        result = results_by_id.get(contribution.rule_id)
        amount = facts.get(contribution.amount_fact)
        contributed, reason = _explain(
            result.status if result else None,
            result.overridden_by if result else None,
            amount,
        )
        if contributed:
            counted_total += float(amount)  # type: ignore[arg-type]
        outcomes.append(
            ContributionOutcome(
                rule_id=contribution.rule_id,
                amount_fact=contribution.amount_fact,
                rule_status=result.status.value if result else "NOT_EVALUATED",
                contributed=contributed,
                amount=float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) else None,
                reason=reason,
            )
        )

    breach = next(
        (b for b in response.aggregate_breaches if b.aggregate_id == PREVIEW_AGGREGATE_ID), None
    )
    contributing_count = sum(1 for o in outcomes if o.contributed)

    return {
        "max_value": max_value,
        "total": breach.total if breach is not None else counted_total,
        "breached": breach is not None,
        "contributing_count": contributing_count,
        "contributions": [o.to_dict() for o in outcomes],
        "overall_status": response.overall_status.value,
        # The honest headline. A cap where nothing contributed is not "within
        # limits" — it is inert, and calling it a pass would repeat the exact
        # false reassurance this feature was guilty of before.
        "verdict": (
            "breached"
            if breach is not None
            else ("within_limit" if contributing_count > 0 else "inert")
        ),
    }
