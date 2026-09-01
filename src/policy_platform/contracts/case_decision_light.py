"""Compact external projection of a full stored case-decision receipt."""
from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

from policy_platform.contracts.case_decision import (
    CitationSourceRef,
    InformationOutcome,
    MissingInformationItem,
    PolicySetRef,
    TokenUsageRef,
    VerificationRequirementItem,
    VerdictOutcome,
    VersionRef,
)

SCHEMA_VERSION: Final[str] = "case_decision_light_v1"
ResponseType = Literal["informational", "decision", "mixed", "not_evaluated"]


class LightRequestRef(BaseModel):
    scenario: str
    scenario_hash: str


class LightAskedRef(BaseModel):
    information_requested: bool
    verdict_requested: bool
    classifier_version: str | None = None


class LightOutcomeRef(BaseModel):
    information: InformationOutcome
    verdict: VerdictOutcome


class LightInformationRef(BaseModel):
    status: str
    answer: str = ""
    explanation: str | None = None
    note: str = ""


class LightVerdictRef(BaseModel):
    status: str
    reached: bool
    decision: str = ""
    explanation: str = ""
    missing_information: list[MissingInformationItem] = Field(default_factory=list)
    verification_requirements: list[VerificationRequirementItem] = Field(default_factory=list)
    note: str = ""


class LightPolicyRef(BaseModel):
    provision_id: str | None = None
    provision_key: str | None = None
    heading_path: list[str] = Field(default_factory=list)


class LightCitationRef(BaseModel):
    rule_id: str
    policy: LightPolicyRef | None = None
    source: CitationSourceRef
    serves: list[Literal["information", "verdict"]] = Field(default_factory=list)


class LightRetrievalRef(BaseModel):
    status: str
    method: str | None = None
    policies_retained: int | None = None
    rule_rescued_policies: int | None = None
    reason: str | None = None


class LightTraceRef(BaseModel):
    classifier_version: str | None = None
    prompt_version: str | None = None
    plan_profile: str | None = None
    selector_catalogue_version: str | None = None
    model_deployment: str | None = None
    stage_latency_ms: dict[str, int] | None = None
    token_usage: TokenUsageRef | None = None


class CaseDecisionLightEnvelope(BaseModel):
    """Essential decision output; the full receipt remains available by URL."""

    schema_version: Literal["case_decision_light_v1"] = SCHEMA_VERSION
    response_type: ResponseType
    decision_id: str
    correlation_id: str
    idempotency_key: str | None = None
    policy_set: PolicySetRef
    active_version: VersionRef | None = None
    request: LightRequestRef
    asked: LightAskedRef
    outcome: LightOutcomeRef
    information: LightInformationRef | None = None
    verdict: LightVerdictRef | None = None
    retrieval: LightRetrievalRef
    policies: list[LightPolicyRef] = Field(default_factory=list)
    citations: list[LightCitationRef] = Field(default_factory=list)
    trace: LightTraceRef
    decision_hash: str
    hash_basis: str
    receipt_url: str
    latency_ms: int
