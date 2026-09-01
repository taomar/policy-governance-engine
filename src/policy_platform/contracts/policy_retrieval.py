"""The retrieval-only external contract.

This is the light companion to ``case_decision_v2``. It returns the exact
published policy records selected for a scenario and stops before intent
classification, adjudication, prose generation, or receipt persistence.
"""
from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from policy_platform.contracts.case_decision import (
    LanguageRef,
    PolicySetRef,
    RetrievalRef,
    RuleSelectionRef,
    SizeRef,
    TokenUsageRef,
    VersionRef,
)

SCHEMA_VERSION: Final[str] = "policy_retrieval_v1"


class PolicyRetrievalQueryRef(BaseModel):
    """The caller's scenario; the processed form is in ``language``."""

    scenario: str
    scenario_hash: str


class RetrievedPolicyIdentity(BaseModel):
    """The stable identity of one selected published policy."""

    provision_id: str | None = None
    provision_key: str
    heading_path: list[str] = Field(default_factory=list)


class PolicyMatchRef(BaseModel):
    """Why this policy is in the returned set and which rules were retained."""

    best_rank: int | None = None
    best_score: float | None = None
    rule_selection: RuleSelectionRef | None = None


class RetrievedPolicyRecord(BaseModel):
    """One exact policy record that the decision path would have read."""

    policy: RetrievedPolicyIdentity
    match: PolicyMatchRef
    payload: dict[str, Any] = Field(
        description=(
            "The selected grounding_projection_v1 record. Large policies contain only the rules "
            "named by match.rule_selection; source evidence remains verbatim."
        )
    )


class PolicyRetrievalEnvelope(BaseModel):
    """Filtered policy JSON with no decision-shaped fields."""

    schema_version: Literal["policy_retrieval_v1"] = SCHEMA_VERSION
    correlation_id: str
    policy_set: PolicySetRef
    active_version: VersionRef | None = None
    query: PolicyRetrievalQueryRef
    retrieval: RetrievalRef
    policies: list[RetrievedPolicyRecord] = Field(default_factory=list)
    size: SizeRef
    language: LanguageRef
    token_usage: TokenUsageRef
    latency_ms: int
