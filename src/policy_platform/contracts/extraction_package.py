"""The versioned extraction package handed to the existing application.

WHAT THIS IS
------------
One document, one extraction release, one artifact. It carries the canonical
rules, their exact evidence, the candidate graph, the coverage proof, the
verification findings, and the DMN/FEEL projection — together, so a reviewer
never has to reconcile several partial outputs that may disagree.

THE HANDOFF BOUNDARY
--------------------
``application_handoff`` is where extraction stops. The extractor does not
establish policy authority, create review work, approve anything, publish, or
write to Search. It produces a package and submits it through the existing
application's candidate-intake service, which owns everything after that point.

The references back to the application's own records (`existing_review_ref`,
`existing_release_ref`) are deliberately *observations*: extraction records what
the application decided, and never sets them itself. A field extraction could
write would become a second, competing source of truth about review state.

SEPARATION OF TEXT KINDS
------------------------
``exact_text`` inside evidence is the source's own characters and is never
rewritten. Display labels, normalized concepts, retrieval text, and FEEL
expressions live in different fields. Collapsing them is how a paraphrase ends
up presented as a quotation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.evidence_resolution import RejectedEvidence, ResolvedEvidence
from policy_platform.contracts.graph_run import CoverageReport, GraphRunArtifact

#: Version of the package envelope itself, distinct from the extraction
#: template version. A consumer must be able to tell "the schema of this file
#: changed" from "the thing that produced it changed".
PACKAGE_VERSION = "PolicyExtractionPackageV1"

#: Whether a rule can be handed to the review workbench as-is.
CandidateStatus = Literal["proposed", "requires_review", "not_projectable"]


class SourceReleaseRef(BaseModel):
    """The immutable source this package was extracted from."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    document_version_id: str = ""
    title: str = ""
    source_hash: str = ""
    mime_type: str = ""


class CanonicalDocumentRef(BaseModel):
    """The canonical artifact every span in this package resolves against.

    Identified by hash rather than by path: a span is only meaningful relative to
    one exact artifact, and a re-conversion that produced different text must not
    silently satisfy an older package's citations.
    """

    model_config = ConfigDict(extra="ignore")

    document_id: str
    canonical_hash: str = ""
    parser: str = ""
    converter_version: str | None = None
    page_count: int = 0
    element_count: int = 0


class RuleCandidate(BaseModel):
    """One atomic, independently evaluable rule proposed by extraction.

    Split rather than bundled: an obligation and the permission beside it are
    separately true or false, separately approvable, and separately citable. A
    combined rule forces a reviewer to accept or reject both at once.
    """

    model_config = ConfigDict(extra="ignore")

    rule_key: str = Field(description="Stable identity derived from verified spans.")
    title: str = ""
    modality: str | None = None
    actor: str | None = None
    action: str | None = None
    outcome: str | None = None
    scope: str | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    #: `evidence_hash` values from the resolved spans supporting this rule.
    #: Referenced rather than embedded so one span cited by three rules is
    #: stored once and cannot diverge between them.
    evidence_hashes: list[str] = Field(default_factory=list)
    graph_candidate_keys: list[str] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)
    status: CandidateStatus = "proposed"


class RuleCluster(BaseModel):
    """Related rules that together form one business decision.

    Clustering never erases the individual rules: each keeps its own identity
    and evidence, so a reviewer can reject one member without discarding the
    decision, and a citation still resolves to a single clause.
    """

    model_config = ConfigDict(extra="ignore")

    cluster_key: str
    title: str = ""
    rule_keys: list[str] = Field(default_factory=list)


class ProjectionCandidate(BaseModel):
    """An unapproved DMN/FEEL view of a cluster.

    Explicitly unapproved. Compilation, parity testing and executable status
    happen through the application's existing post-review flow, after the
    canonical semantics are approved — never here.
    """

    model_config = ConfigDict(extra="ignore")

    cluster_key: str
    projection_kind: str = "decision_table"
    feel_expressions: list[str] = Field(default_factory=list)
    status: Literal["candidate", "requires_review", "not_projectable"] = "candidate"
    unsupported_reason: str | None = None


class VerificationSummary(BaseModel):
    """Outcome of the independent verification pass."""

    model_config = ConfigDict(extra="ignore")

    #: Conditions that make the package unusable. Any entry means the package
    #: must not be handed over.
    blockers: list[str] = Field(default_factory=list)
    #: Uncertainty a reviewer should see but which does not invalidate the run.
    warnings: list[str] = Field(default_factory=list)
    spans_verified: int = 0
    spans_rejected: int = 0

    @property
    def ok(self) -> bool:
        return not self.blockers


class ApplicationHandoff(BaseModel):
    """The boundary into the existing application.

    ``idempotency_key`` is what makes a retry safe. Extraction can be re-run for
    many legitimate reasons — a restart, a transient model failure, an operator
    retry — and each must resolve to the same intake, not to a duplicate set of
    candidates in the review queue.
    """

    model_config = ConfigDict(extra="ignore")

    idempotency_key: str
    submitted: bool = False
    #: Observed from the application, never assigned by extraction.
    existing_candidate_refs: list[str] = Field(default_factory=list)
    existing_review_ref: str | None = None
    existing_release_ref: str | None = None
    search_projection_ref: str | None = None


class PolicyExtractionPackage(BaseModel):
    """Everything one extraction run hands to the application."""

    model_config = ConfigDict(extra="ignore")

    package_version: str = PACKAGE_VERSION
    source_release: SourceReleaseRef
    canonical_document: CanonicalDocumentRef
    graph_run: GraphRunArtifact | None = None
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    evidence_spans: list[ResolvedEvidence] = Field(default_factory=list)
    rejected_spans: list[RejectedEvidence] = Field(default_factory=list)
    canonical_rules: list[RuleCandidate] = Field(default_factory=list)
    rule_clusters: list[RuleCluster] = Field(default_factory=list)
    projections: list[ProjectionCandidate] = Field(default_factory=list)
    verification: VerificationSummary = Field(default_factory=VerificationSummary)
    application_handoff: ApplicationHandoff

    @property
    def is_handoff_ready(self) -> bool:
        """Whether this package may be submitted.

        Requires verification to pass *and* coverage to be complete. Either
        alone is insufficient: perfectly verified rules extracted from half a
        document are still half a policy.
        """

        return self.verification.ok and self.coverage.is_complete

    def evidence_for(self, rule_key: str) -> list[ResolvedEvidence]:
        """Resolve a rule's referenced spans back to the shared span list."""

        rule = next((r for r in self.canonical_rules if r.rule_key == rule_key), None)
        if rule is None:
            return []
        wanted = set(rule.evidence_hashes)
        return [span for span in self.evidence_spans if span.evidence_hash in wanted]

    def unsupported_projections(self) -> list[ProjectionCandidate]:
        return [p for p in self.projections if p.status != "candidate"]


def build_idempotency_key(
    *, source_hash: str, canonical_hash_value: str, template_schema_hash: str, run_config_hash: str
) -> str:
    """Derive the key that makes re-submission safe.

    Built from what actually determines the output: the source bytes, the
    canonical artifact, the extraction template, and the run configuration. A
    timestamp or run id would make every retry look new, which is exactly the
    duplication the key exists to prevent — while a change to any of these
    genuinely *is* a different extraction and should intake separately.
    """

    return canonical_hash(
        {
            "source_hash": source_hash,
            "canonical_hash": canonical_hash_value,
            "template_schema_hash": template_schema_hash,
            "run_config_hash": run_config_hash,
        }
    )


def rule_identity(
    *, document_id: str, evidence_hashes: list[str], modality: str | None, action: str | None
) -> str:
    """Derive a rule's stable identity from its verified evidence.

    Identity comes from *where the rule is* plus what it does, never from a
    model-generated title or its position in a list. Re-running extraction with
    a reworded title must therefore produce the same identity, so a diff shows
    the rewording rather than a deletion and an unrelated insertion.

    Evidence hashes are sorted because the order spans were emitted in is an
    artifact of the run, not a property of the rule.
    """

    return canonical_hash(
        {
            "document_id": document_id,
            "evidence": sorted(evidence_hashes),
            "modality": (modality or "").casefold(),
            "action": (action or "").casefold(),
        }
    )
