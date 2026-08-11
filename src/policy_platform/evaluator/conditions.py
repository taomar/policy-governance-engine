"""Condition AST interpreter (Section 14.1 / ADR-0005).

Pure function: (condition, facts) -> ConditionResult. No I/O, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum

from policy_platform.contracts.conditions import (
    AllCondition,
    AnyCondition,
    ConditionNode,
    ConditionOperator,
    FactComparisonCondition,
    FactRelativeComparisonCondition,
    NotCondition,
)

_MISSING = object()


class ConditionOutcome(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    INDETERMINATE = "INDETERMINATE"


@dataclass
class ConditionResult:
    outcome: ConditionOutcome
    missing_facts: set[str] = field(default_factory=set)

    @staticmethod
    def true() -> "ConditionResult":
        return ConditionResult(ConditionOutcome.TRUE)

    @staticmethod
    def false() -> "ConditionResult":
        return ConditionResult(ConditionOutcome.FALSE)

    @staticmethod
    def indeterminate(missing: set[str]) -> "ConditionResult":
        return ConditionResult(ConditionOutcome.INDETERMINATE, missing)


def _coerce_comparable(value: object) -> object:
    """Coerce ISO date/datetime strings to comparable types where possible."""

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
    return value


def _evaluate_leaf(node: FactComparisonCondition, facts: dict[str, object | None]) -> ConditionResult:
    fact_present = node.fact in facts
    fact_value = facts.get(node.fact, _MISSING)

    # Rule 5.5: a missing required fact must produce INDETERMINATE, not FALSE.
    if node.operator == ConditionOperator.EXISTS:
        return ConditionResult.true() if fact_present and fact_value is not None else ConditionResult.false()
    if node.operator == ConditionOperator.IS_NULL:
        if not fact_present:
            return ConditionResult.indeterminate({node.fact})
        return ConditionResult.true() if fact_value is None else ConditionResult.false()

    if not fact_present or fact_value is None:
        return ConditionResult.indeterminate({node.fact})

    left = _coerce_comparable(fact_value)
    right = _coerce_comparable(node.value)

    op = node.operator
    try:
        match op:
            case ConditionOperator.EQUALS:
                result = left == right
            case ConditionOperator.NOT_EQUALS:
                result = left != right
            case ConditionOperator.GREATER_THAN:
                result = left > right
            case ConditionOperator.GREATER_THAN_OR_EQUAL:
                result = left >= right
            case ConditionOperator.LESS_THAN:
                result = left < right
            case ConditionOperator.LESS_THAN_OR_EQUAL:
                result = left <= right
            case ConditionOperator.IN:
                result = left in right  # type: ignore[operator]
            case ConditionOperator.NOT_IN:
                result = left not in right  # type: ignore[operator]
            case ConditionOperator.CONTAINS:
                result = right in left  # type: ignore[operator]
            case ConditionOperator.STARTS_WITH:
                result = str(left).startswith(str(right))
            case ConditionOperator.ENDS_WITH:
                result = str(left).endswith(str(right))
            case ConditionOperator.BEFORE:
                result = left < right
            case ConditionOperator.AFTER:
                result = left > right
            case ConditionOperator.ON_OR_BEFORE:
                result = left <= right
            case ConditionOperator.ON_OR_AFTER:
                result = left >= right
            case ConditionOperator.WITHIN_DURATION:
                # value is expected to be an ISO-8601 duration in days (int) for
                # this local implementation; a full ISO-8601 duration parser is
                # a documented future enhancement (see docs/known-limitations.md).
                if not isinstance(left, (datetime, date)):
                    return ConditionResult.indeterminate({node.fact})
                now = datetime.utcnow() if isinstance(left, datetime) else date.today()
                delta = abs((now - left).days) if isinstance(left, date) else abs((now - left).total_seconds() / 86400)
                result = delta <= float(right)  # type: ignore[arg-type]
            case ConditionOperator.COUNT_EQUALS:
                result = len(left) == right  # type: ignore[arg-type]
            case ConditionOperator.COUNT_GREATER_THAN:
                result = len(left) > right  # type: ignore[arg-type]
            case _:
                raise ValueError(f"Unsupported operator: {op}")
    except TypeError:
        # Incompatible types for comparison — treat as indeterminate rather
        # than silently failing, since this typically indicates a data-quality
        # problem rather than a genuine business "false".
        return ConditionResult.indeterminate({node.fact})

    return ConditionResult.true() if result else ConditionResult.false()


def _evaluate_relative_leaf(
    node: FactRelativeComparisonCondition, facts: dict[str, object | None]
) -> ConditionResult:
    """Compare a fact against a multiple of another fact.

    Both operands are required. A missing reference fact is reported alongside
    a missing subject fact rather than instead of it, so a caller asking "what
    would I need to supply to decide this rule?" gets the complete answer in
    one pass — the same guarantee `_evaluate_leaf` gives for the single-fact
    case (Rule 5.5: absent input is INDETERMINATE, never FALSE).

    Comparison operators only. `exists`/`isNull` ask about presence, which is a
    question about one fact and is already answerable through
    `FactComparisonCondition`; set membership and string operators have no
    meaning against a scaled number. Anything outside the ordered set is
    INDETERMINATE rather than an exception, matching how this module already
    treats an incomparable pair.
    """

    missing: set[str] = set()
    left_value = facts.get(node.fact, _MISSING)
    if node.fact not in facts or left_value is None:
        missing.add(node.fact)
    right_value = facts.get(node.reference.fact, _MISSING)
    if node.reference.fact not in facts or right_value is None:
        missing.add(node.reference.fact)
    if missing:
        return ConditionResult.indeterminate(missing)

    try:
        left = float(left_value)  # type: ignore[arg-type]
        right = float(right_value) * node.reference.factor  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # A non-numeric operand is a data-quality problem, not a business
        # "false" — the same reading `_evaluate_leaf` gives an incomparable
        # pair. Reporting FALSE here would silently deny a claim that was
        # never actually tested.
        return ConditionResult.indeterminate({node.fact, node.reference.fact})

    op = node.operator
    match op:
        case ConditionOperator.EQUALS:
            result = left == right
        case ConditionOperator.NOT_EQUALS:
            result = left != right
        case ConditionOperator.GREATER_THAN:
            result = left > right
        case ConditionOperator.GREATER_THAN_OR_EQUAL:
            result = left >= right
        case ConditionOperator.LESS_THAN:
            result = left < right
        case ConditionOperator.LESS_THAN_OR_EQUAL:
            result = left <= right
        case _:
            return ConditionResult.indeterminate({node.fact, node.reference.fact})

    return ConditionResult.true() if result else ConditionResult.false()


def evaluate_condition(node: ConditionNode, facts: dict[str, object | None]) -> ConditionResult:
    """Recursively evaluate a condition AST node against a fact bag.

    Semantics:
    - AND (`all`): FALSE short-circuits to FALSE even if other children are
      INDETERMINATE (a rule cannot be satisfied if any branch is definitely
      false). If no child is FALSE but at least one is INDETERMINATE, the
      result is INDETERMINATE. Otherwise TRUE.
    - OR (`any`): TRUE short-circuits to TRUE. If no child is TRUE but at
      least one is INDETERMINATE, the result is INDETERMINATE. Otherwise
      FALSE.
    - NOT: inverts TRUE/FALSE; INDETERMINATE propagates unchanged.
    """

    match node:
        case FactComparisonCondition():
            return _evaluate_leaf(node, facts)
        case FactRelativeComparisonCondition():
            return _evaluate_relative_leaf(node, facts)
        case AllCondition():
            missing: set[str] = set()
            saw_indeterminate = False
            for child in node.all:
                child_result = evaluate_condition(child, facts)
                if child_result.outcome == ConditionOutcome.FALSE:
                    return ConditionResult.false()
                if child_result.outcome == ConditionOutcome.INDETERMINATE:
                    saw_indeterminate = True
                    missing |= child_result.missing_facts
            return ConditionResult.indeterminate(missing) if saw_indeterminate else ConditionResult.true()
        case AnyCondition():
            missing = set()
            saw_indeterminate = False
            for child in node.any:
                child_result = evaluate_condition(child, facts)
                if child_result.outcome == ConditionOutcome.TRUE:
                    return ConditionResult.true()
                if child_result.outcome == ConditionOutcome.INDETERMINATE:
                    saw_indeterminate = True
                    missing |= child_result.missing_facts
            return ConditionResult.indeterminate(missing) if saw_indeterminate else ConditionResult.false()
        case NotCondition():
            child_result = evaluate_condition(node.not_, facts)
            if child_result.outcome == ConditionOutcome.INDETERMINATE:
                return child_result
            return ConditionResult.false() if child_result.outcome == ConditionOutcome.TRUE else ConditionResult.true()
        case _:
            raise ValueError(f"Unsupported condition node type: {type(node)!r}")
