"""Allowlisted condition AST (Section 14.1).

Only the operators and node types defined here are legal. There is no `eval`,
no dynamic dispatch, no arbitrary code execution path anywhere in this module
or in the evaluator that interprets it.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class ConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "notEquals"
    GREATER_THAN = "greaterThan"
    GREATER_THAN_OR_EQUAL = "greaterThanOrEqual"
    LESS_THAN = "lessThan"
    LESS_THAN_OR_EQUAL = "lessThanOrEqual"
    IN = "in"
    NOT_IN = "notIn"
    CONTAINS = "contains"
    STARTS_WITH = "startsWith"
    ENDS_WITH = "endsWith"
    EXISTS = "exists"
    IS_NULL = "isNull"
    BEFORE = "before"
    AFTER = "after"
    ON_OR_BEFORE = "onOrBefore"
    ON_OR_AFTER = "onOrAfter"
    WITHIN_DURATION = "withinDuration"
    COUNT_EQUALS = "countEquals"
    COUNT_GREATER_THAN = "countGreaterThan"


class FactComparisonCondition(BaseModel):
    """Leaf condition node: compares a single fact against a literal value."""

    type: Literal["factComparison"] = "factComparison"
    fact: str
    operator: ConditionOperator
    value: object | None = None


class FactOperand(BaseModel):
    """A right-hand side that names another fact instead of a literal value.

    `factor` scales the referenced fact before comparison, which is how a
    percentage-of-a-base is encoded: 0.10 means "10% of". It is a plain
    multiplier and nothing more — there is deliberately no offset, no nested
    arithmetic and no expression string, because none of those appeared in the
    measured agent output and an unused general mechanism here would be a new
    surface to get wrong.
    """

    fact: str
    factor: float = 1.0


class FactRelativeComparisonCondition(BaseModel):
    """Leaf node: compares a fact against a multiple of *another* fact.

    Added because policy text routinely bounds one quantity by a proportion of
    another — "an annual increase not exceeding 10% of the employee's current
    basic salary" — and `FactComparisonCondition` can only compare a fact to a
    constant. Measured against live AD-103 output, every decision the
    formulator declared executable used this shape, so without it a complete
    and correct fact model still produced zero executable rules.

    Both facts are required at evaluation time: a missing *reference* fact is
    just as disqualifying as a missing subject fact, and the evaluator reports
    both so "which fact was missing" stays answerable.
    """

    type: Literal["factRelativeComparison"] = "factRelativeComparison"
    fact: str
    operator: ConditionOperator
    reference: FactOperand


class AllCondition(BaseModel):
    """Boolean AND over child conditions."""

    type: Literal["all"] = "all"
    all: list["ConditionNode"]


class AnyCondition(BaseModel):
    """Boolean OR over child conditions."""

    type: Literal["any"] = "any"
    any: list["ConditionNode"]


class NotCondition(BaseModel):
    """Boolean NOT over a single child condition."""

    type: Literal["not"] = "not"
    not_: "ConditionNode" = Field(alias="not")

    model_config = {"populate_by_name": True}


ConditionNode = Annotated[
    Union[
        FactComparisonCondition,
        FactRelativeComparisonCondition,
        AllCondition,
        AnyCondition,
        NotCondition,
    ],
    Field(discriminator="type"),
]

AllCondition.model_rebuild()
AnyCondition.model_rebuild()
NotCondition.model_rebuild()
