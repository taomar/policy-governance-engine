"""Domain layer: SQLAlchemy ORM entities (Section 23 subset).

See docs/data-model.md for the full entity mapping and lifecycle rules.
"""
from __future__ import annotations

from policy_platform.domain.base import Base
from policy_platform.domain.models import (
    ApprovedPolicyVersion,
    ApprovedRule,
    AuditEvent,
    CandidateRule,
    Clause,
    CorrelationFindingRow,
    CorrelationRun,
    DocumentVersion,
    Evaluation,
    EvidenceReference,
    ExtractionRun,
    OutboxMessage,
    PolicyAuthority,
    PolicySet,
    RuleException,
    SourceDocument,
)

__all__ = [
    "Base",
    "ApprovedPolicyVersion",
    "ApprovedRule",
    "AuditEvent",
    "CandidateRule",
    "Clause",
    "CorrelationFindingRow",
    "CorrelationRun",
    "DocumentVersion",
    "Evaluation",
    "EvidenceReference",
    "ExtractionRun",
    "OutboxMessage",
    "PolicyAuthority",
    "PolicySet",
    "RuleException",
    "SourceDocument",
]
