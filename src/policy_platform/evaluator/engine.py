"""Deterministic policy evaluation engine (Section 15).

This is the ONLY place where an ApprovedPolicyPackage + facts are combined
into a runtime decision. It must remain free of any AI/Search/network call
(Section 5.4, ADR-0002, ADR-0003).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.conditions import ConditionNode
from policy_platform.contracts.evaluation import (
    AggregateBreach,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationStatus,
    RuleEvaluationResult,
)
from policy_platform.contracts.policy import ApprovedPolicyPackage, CanonicalRule, EffectType
from policy_platform.evaluator.conditions import ConditionOutcome, evaluate_condition
from policy_platform.evaluator.facts import canonicalize_facts
from policy_platform.evaluator.precedence import order_rules_by_precedence

# Reserved fact keys that carry principal/context attributes for Target
# (scope) matching, following the same `entity.property` dotted convention
# used in the spec's own Section 14 JSON example. See
# `contracts.policy.PrincipalContext.to_facts()` for the producer side.
_SCOPE_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("jurisdiction", "subject.jurisdiction"),
    ("organizationalUnit", "subject.organizationalUnit"),
    ("persona", "subject.persona"),
    ("process", "context.process"),
)


def _rule_is_in_effect(rule: CanonicalRule, at: date) -> bool:
    if rule.effective_from > at:
        return False
    if rule.effective_to is not None and rule.effective_to < at:
        return False
    return True


def _match_scope_dimension(values: list[str], fact_value: object | None) -> str:
    """Match one Target/scope dimension against a fact value.

    Returns "match", "mismatch", or "missing":
    - An unrestricted dimension (empty list or `["*"]`) always matches.
    - A restricted dimension with the fact present: matches only if the fact
      value is one of the listed values (XACML Target evaluation).
    - A restricted dimension with the fact absent: "missing" — Section
      5.5/5.7's "missing facts are not false, never invent a determination"
      principle applied to Target matching, not just Condition evaluation.
    """
    if not values or values == ["*"]:
        return "match"
    if fact_value is None:
        return "missing"
    if str(fact_value) in values:
        return "match"
    return "mismatch"


def _match_target(
    rule: CanonicalRule, facts: dict[str, object | None]
) -> tuple[str, str | None, str | None]:
    """Evaluate a rule's `PolicyScope` (XACML Target) against principal/context
    facts. Returns (result, dimension_name, missing_fact_key); result is one
    of "match" (all dimensions matched or unrestricted), "mismatch" (a
    restricted dimension's value conflicted with the fact -> NOT_APPLICABLE),
    or "missing" (a restricted dimension's fact was absent -> INDETERMINATE).
    The first non-matching dimension found is reported; dimensions are
    checked in the fixed order above for determinism.
    """
    scope_values = {
        "jurisdiction": rule.scope.jurisdictions,
        "organizationalUnit": rule.scope.organizational_units,
        "persona": rule.scope.personas,
        "process": rule.scope.processes,
    }
    for dim_name, fact_key in _SCOPE_DIMENSIONS:
        outcome = _match_scope_dimension(scope_values[dim_name], facts.get(fact_key))
        if outcome != "match":
            return outcome, dim_name, fact_key
    return "match", None, None


def _evaluate_rule(rule: CanonicalRule, facts: dict[str, object | None]) -> RuleEvaluationResult:
    if not rule.machine_executable:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            status=EvaluationStatus.NOT_APPLICABLE,
            not_applicable_reason="rule_not_machine_executable",
        )

    target_outcome, target_dim, target_fact_key = _match_target(rule, facts)
    if target_outcome == "mismatch":
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            status=EvaluationStatus.NOT_APPLICABLE,
            not_applicable_reason=f"scope_mismatch:{target_dim}",
        )
    if target_outcome == "missing":
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            status=EvaluationStatus.INDETERMINATE,
            missing_facts=[target_fact_key] if target_fact_key else [],
        )

    condition_result = evaluate_condition(rule.condition, facts)

    triggered_exceptions: list[str] = []
    for exc in rule.exceptions:
        if exc.condition is None:
            continue
        exc_result = evaluate_condition(exc.condition, facts)
        if exc_result.outcome == ConditionOutcome.TRUE:
            triggered_exceptions.append(exc.exception_id)

    match condition_result.outcome:
        case ConditionOutcome.INDETERMINATE:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_revision=rule.rule_revision,
                status=EvaluationStatus.INDETERMINATE,
                missing_facts=sorted(condition_result.missing_facts),
                triggered_exceptions=triggered_exceptions,
            )
        case ConditionOutcome.FALSE:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_revision=rule.rule_revision,
                status=EvaluationStatus.NOT_SATISFIED,
                triggered_exceptions=triggered_exceptions,
            )
        case ConditionOutcome.TRUE:
            if triggered_exceptions:
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_revision=rule.rule_revision,
                    status=EvaluationStatus.NOT_SATISFIED,
                    effect_action=rule.effect.action,
                    effect_type=rule.effect.type.value,
                    triggered_exceptions=triggered_exceptions,
                )
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_revision=rule.rule_revision,
                status=EvaluationStatus.SATISFIED,
                effect_action=rule.effect.action,
                effect_type=rule.effect.type.value,
                triggered_exceptions=triggered_exceptions,
                advice=[a.text for a in rule.advice],
            )
    raise AssertionError("unreachable")  # pragma: no cover


def _apply_combining_algorithm(
    rule_results: list[RuleEvaluationResult],
) -> tuple[list[RuleEvaluationResult], str | None, list[str], list[str], list[str]]:
    """Combining algorithm for SATISFIED rules with conflicting effects
    (Section 15.2 step 7 "apply explicit precedence").

    `rule_results` must already be in precedence order (i.e. built by
    iterating `order_rules_by_precedence`'s output) — this function does not
    re-sort, it only reads that order.

    A "conflict" is exactly the XACML Permit/Deny axis: SATISFIED rules whose
    effect is `deny` versus SATISFIED rules whose effect is `allow` or
    `require_action` (the latter treated together, since `require_action` is
    this codebase's Obligation-like effect attached to a Permit, not a
    separate axis). Multiple SATISFIED rules on the *same* side never
    conflict with each other — they all coexist and contribute (this mirrors
    DMN's "Collect" hit policy: gather every matching output rather than
    force one winner, unless a policy question is genuinely adversarial).

    When both sides are non-empty, the combining algorithm applied is
    precedence-ordered "first-applicable" (a named XACML combining-algorithm
    family): the highest-precedence SATISFIED rule overall decides the
    winning side; every SATISFIED rule on the losing side is marked
    `overridden_by` that rule's id and excluded from the returned action
    lists (but remains visible in `rule_results` for transparency).

    Returns (updated_rule_results, outcome, required_actions, denied_actions, advice_notes).
    """

    satisfied = [r for r in rule_results if r.status == EvaluationStatus.SATISFIED]
    if not satisfied:
        return rule_results, None, [], [], []

    allow_like = {EffectType.ALLOW.value, EffectType.REQUIRE_ACTION.value}
    allow_side = [r for r in satisfied if r.effect_type in allow_like]
    deny_side = [r for r in satisfied if r.effect_type == EffectType.DENY.value]
    # Rules whose effect is neither allow-like nor deny (currently only
    # INFORMATIONAL, from a `definition`/`classification` rule_type) never
    # compete on the allow/deny axis. They are excluded from `winner`
    # selection below so one being top-precedence can't force a spurious
    # "side" (e.g. `winner in allow_side` is False for an informational
    # rule, which previously made it default onto the deny side even with
    # no actual DENY rule present). They remain in `satisfied` and still
    # reach `winning_side_current`/advice when there is no real conflict.
    axis_satisfied = [r for r in satisfied if r.effect_type in allow_like or r.effect_type == EffectType.DENY.value]
    if not axis_satisfied:
        # Every satisfied rule is purely informational: nothing to combine
        # or override, but their advice (if any) should still surface.
        return rule_results, None, [], [], sorted({a for r in satisfied for a in r.advice})

    winner = axis_satisfied[0]  # already precedence-ordered
    winning_side = allow_side if winner in allow_side else deny_side
    losing_side = deny_side if winning_side is allow_side else allow_side

    if allow_side and deny_side:
        overridden_ids = {r.rule_id for r in losing_side}
        rule_results = [
            r.model_copy(update={"overridden_by": winner.rule_id}) if r.rule_id in overridden_ids else r
            for r in rule_results
        ]
        winning_side_current = [r for r in rule_results if r.rule_id in {w.rule_id for w in winning_side}]
    else:
        winning_side_current = satisfied

    required_actions = sorted(
        {r.effect_action for r in winning_side_current if r.effect_action and r.effect_type in allow_like}
    )
    denied_actions = sorted(
        {r.effect_action for r in winning_side_current if r.effect_action and r.effect_type == EffectType.DENY.value}
    )
    # Advice is informational and polarity-agnostic (see `Advice` docstring),
    # so it's collected from the whole winning side regardless of effect
    # type — unlike required_actions/denied_actions, which split by polarity.
    advice_notes = sorted({a for r in winning_side_current for a in r.advice})
    outcome = winner.effect_action

    return rule_results, outcome, required_actions, denied_actions, advice_notes


def _evaluate_aggregate_limits(
    package: ApprovedPolicyPackage,
    rule_results: list[RuleEvaluationResult],
    facts: dict[str, object | None],
) -> list[AggregateBreach]:
    """Section 15 combined-cap gap: sum contributing rules' amounts and flag
    any `AggregateLimit` whose total exceeds `max_value` (OMG DMN "Collect"
    hit policy with a SUM aggregator; see `AggregateLimit` for full grounding).

    A rule contributes its `amount_fact` value only when that rule is
    SATISFIED and not overridden away by the combining algorithm above (an
    overridden-out DENY/ALLOW loser does not contribute to a cap it lost the
    right to apply). Missing amount facts contribute 0 rather than raising —
    the per-rule INDETERMINATE/missing-fact status already surfaced that gap
    on the rule itself; this step only aggregates what was actually decided.
    """

    breaches: list[AggregateBreach] = []
    results_by_id = {r.rule_id: r for r in rule_results}
    for agg in package.aggregate_limits:
        total = 0.0
        contributing_ids: list[str] = []
        for contribution in agg.contributing_rules:
            result = results_by_id.get(contribution.rule_id)
            if result is None or result.status != EvaluationStatus.SATISFIED or result.overridden_by:
                continue
            amount = facts.get(contribution.amount_fact)
            if isinstance(amount, (int, float)):
                total += float(amount)
                contributing_ids.append(contribution.rule_id)
        if contributing_ids and total > agg.max_value:
            breaches.append(
                AggregateBreach(
                    aggregate_id=agg.aggregate_id,
                    description=agg.description,
                    total=total,
                    max_value=agg.max_value,
                    contributing_rule_ids=contributing_ids,
                )
            )
    return breaches


def evaluate_policy(
    package: ApprovedPolicyPackage,
    request: EvaluationRequest,
    *,
    evaluation_id: str | None = None,
    evaluation_timestamp: datetime | None = None,
) -> EvaluationResponse:
    """Evaluate `request.facts` against `package` and return a stable result.

    Deterministic guarantees (Section 27.5):
    - The same (package, canonicalized facts) pair always yields the same
      `result_hash`.
    - No AI/Search/network call occurs anywhere in this function or its
      callees.
    """

    eval_time = evaluation_timestamp or request.evaluation_timestamp or datetime.now(timezone.utc)
    if not isinstance(eval_time, datetime):
        eval_time = datetime.combine(eval_time, datetime.min.time(), tzinfo=timezone.utc)
    as_of_date = eval_time.date()
    canonical_facts = canonicalize_facts(request.facts)

    applicable_rules = [r for r in package.rules if _rule_is_in_effect(r, as_of_date)]
    ordered_rules = order_rules_by_precedence(applicable_rules)

    rule_results: list[RuleEvaluationResult] = [_evaluate_rule(r, canonical_facts) for r in ordered_rules]

    satisfied = [r.rule_id for r in rule_results if r.status == EvaluationStatus.SATISFIED]
    failed = [r.rule_id for r in rule_results if r.status == EvaluationStatus.NOT_SATISFIED]
    indeterminate_rules = [r for r in rule_results if r.status == EvaluationStatus.INDETERMINATE]
    missing_facts = sorted({f for r in indeterminate_rules for f in r.missing_facts})
    triggered_exceptions = sorted({e for r in rule_results for e in r.triggered_exceptions})

    rule_results, outcome, required_actions, denied_actions, advice_notes = _apply_combining_algorithm(rule_results)
    aggregate_breaches = _evaluate_aggregate_limits(package, rule_results, canonical_facts)

    if indeterminate_rules:
        overall_status = EvaluationStatus.INDETERMINATE
    elif satisfied:
        overall_status = EvaluationStatus.SATISFIED
    elif not applicable_rules:
        overall_status = EvaluationStatus.NOT_APPLICABLE
    else:
        overall_status = EvaluationStatus.NOT_SATISFIED

    evidence_refs = sorted(
        {
            f"{ev.document_version_id}#{ev.clause_id}"
            for r in ordered_rules
            for ev in r.evidence
            if r.rule_id in satisfied
        }
    )

    hash_payload = {
        "policy_set_id": package.policy_set_id,
        "policy_version_id": package.policy_version_id,
        "facts": canonical_facts,
        "as_of_date": as_of_date.isoformat(),
        "overall_status": overall_status.value,
        "satisfied_rules": satisfied,
        "failed_rules": failed,
        "missing_facts": missing_facts,
        "triggered_exceptions": triggered_exceptions,
        "required_actions": required_actions,
        "denied_actions": denied_actions,
        "aggregate_breaches": [b.model_dump() for b in aggregate_breaches],
        "advice_notes": advice_notes,
    }
    result_hash = canonical_hash(hash_payload)

    return EvaluationResponse(
        evaluation_id=evaluation_id or str(uuid.uuid4()),
        policy_set_id=package.policy_set_id,
        policy_version_id=package.policy_version_id,
        overall_status=overall_status,
        outcome=outcome,
        applicable_rules=[r.rule_id for r in ordered_rules],
        satisfied_rules=satisfied,
        failed_rules=failed,
        missing_facts=missing_facts,
        required_actions=required_actions,
        denied_actions=denied_actions,
        triggered_exceptions=triggered_exceptions,
        evidence_references=evidence_refs,
        rule_results=rule_results,
        aggregate_breaches=aggregate_breaches,
        advice_notes=advice_notes,
        result_hash=result_hash,
        evaluation_timestamp=eval_time,
    )
