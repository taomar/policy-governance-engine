"""Contracts for cross-rule correlation analysis.

A policy set is not a bag of independent rules. Two rules can contradict each
other, one can be a specialization or an explicit exception of another, a newer
one can supersede an older one, and a pair can simply duplicate each other. A
reviewer approving rules one at a time cannot see any of that: each rule reads
correctly on its own, and the defect exists only in the relationship.

These shapes mirror Sections 51-53 and 79-84 of
`prompts/contradiction_detector_v1.md`, which is the governing specification.
Two of its rules drive the design here more than anything else:

- **Section 53 forbids confidence scores.** A model asked for a probability
  will supply one, and a number like `0.91` reads as measurement when it is
  actually invention. `analysis_status` replaces it with four states a reviewer
  can act on differently.
- **Section 52 separates severity from confidence.** Severity is about impact
  if the finding is real; status is about whether it is real. Collapsing them
  loses the distinction between "certainly a minor overlap" and "possibly a
  critical contradiction", which need opposite handling.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Section 51. The complete, closed set of relationship classifications. Closed
#: on purpose: an open vocabulary would let the model coin a new label per
#: finding, and findings that cannot be grouped cannot be triaged.
FindingClassification = Literal[
    "DIRECT_CONTRADICTION",
    "PARTIAL_CONTRADICTION",
    "OUTCOME_CONTRADICTION",
    "POTENTIAL_CONTRADICTION",
    "OVERLAP",
    "GENERAL_SPECIFIC_OVERLAP",
    "OVERLAP_REQUIRES_PRECEDENCE",
    "COMPATIBLE",
    "SPECIALIZATION",
    "EXCEPTION",
    "CONDITIONAL_RESTRICTION",
    "SUPERSEDED",
    "TEMPORALLY_SEPARATED",
    "DUPLICATE",
    "SEMANTIC_DUPLICATE",
    "NORMATIVE_STRENGTH_DIFFERENCE",
    "GUIDANCE_VS_REQUIREMENT",
    "COVERAGE_GAP",
    "AMBIGUOUS_CONFLICT",
    "INDEPENDENT",
]

#: Section 52. Impact if the finding is real — deliberately not confidence.
FindingSeverity = Literal["critical", "high", "medium", "low", "informational"]

#: Section 53. Replaces the confidence score the specification bans.
AnalysisStatus = Literal["confirmed", "potential", "ambiguous", "resolved"]

#: Classifications that describe a genuine problem needing a human decision, as
#: opposed to ones that merely record a benign relationship. Used to decide what
#: surfaces to a reviewer by default, so a correct `INDEPENDENT` finding does
#: not bury a real contradiction.
ACTIONABLE_CLASSIFICATIONS: frozenset[str] = frozenset(
    {
        "DIRECT_CONTRADICTION",
        "PARTIAL_CONTRADICTION",
        "OUTCOME_CONTRADICTION",
        "POTENTIAL_CONTRADICTION",
        "OVERLAP_REQUIRES_PRECEDENCE",
        "COVERAGE_GAP",
        "AMBIGUOUS_CONFLICT",
        "DUPLICATE",
        "SEMANTIC_DUPLICATE",
    }
)


class FindingEvidence(BaseModel):
    """One rule's contribution to a finding.

    `source_text` is required by Section 113 to be an exact quote. It is not
    re-verified here because, unlike Stage 1 extraction, the input to this agent
    is already-structured rules rather than raw document text — but it is
    retained so a reviewer can see precisely which words the model reasoned
    from, rather than only its conclusion.
    """

    model_config = ConfigDict(extra="ignore")

    policy_index: int
    #: Filled in by the application from `policy_index`. The model addresses
    #: rules by their position in the supplied batch (Section 80), never by
    #: identifier, so it cannot invent a rule that was not sent to it.
    rule_id: str = ""
    source_text: str = ""
    relevant_semantics: dict = Field(default_factory=dict)


class FindingOverlap(BaseModel):
    """Section 83. The formal region in which two rules both apply."""

    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    fact: str | None = None
    scope: str | None = None


class CorrelationFinding(BaseModel):
    """One relationship between two or more rules."""

    model_config = ConfigDict(extra="ignore")

    finding_id: str = ""
    policy_indexes: list[int] = Field(default_factory=list)
    #: Resolved by the application from `policy_indexes`.
    rule_ids: list[str] = Field(default_factory=list)
    classification: FindingClassification
    analysis_status: AnalysisStatus = "potential"
    severity: FindingSeverity = "informational"
    reason: str = ""
    evidence: list[FindingEvidence] = Field(default_factory=list)
    overlap: FindingOverlap | None = None
    #: Section 84. What a human would have to supply to settle an ambiguous
    #: finding — a definition, a precedence configuration, an effective date.
    requirements: list[str] = Field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return self.classification in ACTIONABLE_CLASSIFICATIONS


class CorrelationSummary(BaseModel):
    """Section 79 counts."""

    model_config = ConfigDict(extra="ignore")

    rules_analyzed: int = 0
    confirmed_contradictions: int = 0
    potential_conflicts: int = 0
    overlaps: int = 0
    gaps: int = 0
    duplicates: int = 0
    resolved_relationships: int = 0


class CorrelationAnalysis(BaseModel):
    """The agent's complete output for one comparison group."""

    model_config = ConfigDict(extra="ignore")

    summary: CorrelationSummary = Field(default_factory=CorrelationSummary)
    findings: list[CorrelationFinding] = Field(default_factory=list)
