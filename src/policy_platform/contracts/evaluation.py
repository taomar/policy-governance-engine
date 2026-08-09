"""Evaluation request/response contracts (Section 15)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvaluationStatus(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INDETERMINATE = "INDETERMINATE"
    ERROR = "ERROR"


class EvaluationRequest(BaseModel):
    policy_set_id: str
    policy_version_id: str | None = None
    use_active_version: bool = True
    evaluation_timestamp: datetime | None = None
    facts: dict[str, object | None] = Field(default_factory=dict)
    correlation_id: str | None = None
    calling_system_identity: str | None = None


class RuleEvaluationResult(BaseModel):
    rule_id: str
    rule_revision: int
    status: EvaluationStatus
    effect_action: str | None = None
    # The rule's effect type ("allow"/"deny"/"require_action") carried through
    # so consumers can distinguish a satisfied DENY from a satisfied ALLOW
    # without re-fetching the rule. Previously both landed in the same
    # `required_actions` bag with no way to tell them apart.
    effect_type: str | None = None
    missing_facts: list[str] = Field(default_factory=list)
    triggered_exceptions: list[str] = Field(default_factory=list)
    # Populated when status is NOT_APPLICABLE specifically because a
    # non-wildcard scope dimension didn't match the request's principal facts
    # (XACML Target mismatch) — e.g. "scope_mismatch:persona". None for the
    # other NOT_APPLICABLE causes. `rule_not_machine_executable` makes the
    # intentional documentation-only short circuit distinguishable from a
    # scope mismatch or an out-of-effect rule.
    not_applicable_reason: str | None = None
    # rule_id of the higher-precedence rule that won when this SATISFIED
    # rule's action conflicted with another SATISFIED rule's action for the
    # same effect type. None means this rule's outcome (if satisfied) stands.
    overridden_by: str | None = None
    # This rule's own `CanonicalRule.advice` text, surfaced whenever the rule
    # is SATISFIED (regardless of whether it's later overridden — this field
    # is per-rule transparency, matching `effect_action`/`effect_type`'s
    # existing "populated on SATISFIED, full stop" behavior). See
    # `EvaluationResponse.advice_notes` for the aggregated, override-aware view.
    advice: list[str] = Field(default_factory=list)


class AggregateBreach(BaseModel):
    """One aggregate limit whose contributing rules' summed amount exceeded
    `max_value` for this evaluation (Section 15 combined-cap gap; see
    `AggregateLimit` in contracts/policy.py for the grounding)."""

    aggregate_id: str
    description: str
    total: float
    max_value: float
    contributing_rule_ids: list[str] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    evaluation_id: str
    policy_set_id: str
    policy_version_id: str
    overall_status: EvaluationStatus
    outcome: str | None = None
    applicable_rules: list[str] = Field(default_factory=list)
    satisfied_rules: list[str] = Field(default_factory=list)
    failed_rules: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    # SATISFIED rules whose effect is allow/require_action only (bug fix: a
    # satisfied DENY rule's action previously landed here too, indistinguishable
    # from an ALLOW). See `denied_actions` for the DENY-effect counterpart.
    required_actions: list[str] = Field(default_factory=list)
    # SATISFIED rules whose effect is deny, kept on its own XACML Permit/Deny
    # axis rather than mixed into `required_actions`.
    denied_actions: list[str] = Field(default_factory=list)
    triggered_exceptions: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    rule_results: list[RuleEvaluationResult] = Field(default_factory=list)
    aggregate_breaches: list[AggregateBreach] = Field(default_factory=list)
    # XACML Advice, aggregated from every SATISFIED rule that actually
    # contributed to the outcome (i.e. not overridden away by the combining
    # algorithm) — same "winning side only" scoping as `required_actions`/
    # `denied_actions`, but collected across both sides since Advice is
    # informational regardless of Permit/Deny polarity.
    advice_notes: list[str] = Field(default_factory=list)
    result_hash: str
    evaluation_timestamp: datetime
