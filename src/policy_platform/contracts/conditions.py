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
    """Leaf condition node: compares a single fact against a value."""

    type: Literal["factComparison"] = "factComparison"
    fact: str
    operator: ConditionOperator
    value: object | None = None


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
    Union[FactComparisonCondition, AllCondition, AnyCondition, NotCondition],
    Field(discriminator="type"),
]

AllCondition.model_rebuild()
AnyCondition.model_rebuild()
NotCondition.model_rebuild()
