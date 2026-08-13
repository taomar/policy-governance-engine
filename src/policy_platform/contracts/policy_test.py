"""PolicyTest / PolicyTestRun contracts (Section 21.6 / 11.6 / 9.11 step 6).

Provider-neutral, DB-free representation of a saved test case and its
execution result — mirrors `policy_platform.domain.models.PolicyTest` /
`PolicyTestRun` the same way `contracts.policy.CanonicalRule` mirrors
`ApprovedRule`. Kept dependency-free from SQLAlchemy so
`evaluator/test_runner.py` (the pure execution function) never needs a
database session, exactly like `evaluator/engine.py`.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from policy_platform.contracts.evaluation import EvaluationResponse, EvaluationStatus


class PolicyTestKind(str, Enum):
    """Section 21.6's required test categories."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    MISSING_FACT = "missing_fact"
    SCOPE = "scope"
    EFFECTIVE_DATE = "effective_date"
    EXCEPTION = "exception"
    PRECEDENCE = "precedence"


class PolicyTestRunStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class PolicyTestCase(BaseModel):
    """A saved test's inputs + expected assertions — the shape
    `evaluator/test_runner.run_policy_test` consumes. Constructed from a
    `PolicyTest` ORM row by `infrastructure/policy_tests/policy_test_execution.py`, or
    directly by unit tests with no DB involved at all.
    """

    name: str
    test_kind: PolicyTestKind
    input_facts: dict[str, object | None] = Field(default_factory=dict)
    evaluation_timestamp: datetime | None = None
    expected_overall_status: EvaluationStatus
    expected_rule_id: str | None = None
    expected_rule_status: EvaluationStatus | None = None
    expected_missing_facts: list[str] | None = None


class PolicyTestExecutionResult(BaseModel):
    """The outcome of actually running a `PolicyTestCase` through the real
    deterministic evaluator (`evaluate_policy`) — never AI-decided."""

    status: PolicyTestRunStatus
    explanation: str
    response: EvaluationResponse
