"""Graph run configuration, health, and coverage contracts.

WHY A RUN ARTIFACT EXISTS AT ALL
--------------------------------
Dense extraction is not a function call with a return value; it is a multi-phase
process that can partially fail. Skeleton batches can be truncated and retried,
chunks can yield nothing and be re-examined, nodes can be merged by an LLM
reconciliation pass, and some chunks can end up dropped entirely. A caller that
sees only the returned graph cannot tell a document that genuinely contained
twelve rules from one that contained forty and lost twenty-eight.

The directive's ninth architecture decision is that uncertainty must be
explicit: a run may complete as ``needs_review``, but it must never hide dropped
chunks, unresolved evidence, synthetic parents, or mapping gaps behind a generic
success state. This module is where that requirement is given a type.

PROVENANCE STRENGTH IS NOT A CONFIDENCE SCORE
---------------------------------------------
Docling Graph resolves each node's location through a fixed ladder — verbatim,
observed, document scope, unresolved — and never guesses. Those values are
recorded here unchanged rather than collapsed into a number, because they mean
categorically different things: ``verbatim`` is an exact location, ``observed``
means "somewhere in these chunks", and averaging the two produces a figure that
describes neither.

Only ``verbatim`` provenance is a candidate for exact evidence, and even then
the application resolves the span itself from the canonical artifact. The other
strengths route material to review.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: How precisely a candidate was located in the source. Mirrors Docling Graph's
#: resolution ladder exactly; adding a value here without a corresponding
#: upstream concept would invent certainty that the extractor never expressed.
ProvenanceStrength = Literal["verbatim", "observed", "derived", "unresolved"]

#: Terminal state of one extraction run. There is deliberately no plain
#: "success": a run either produced reviewable output, or it did not.
RunStatus = Literal["ready_for_review", "needs_review", "failed", "unsupported_source"]

#: What a canonical element turned out to be. Every leaf element must receive
#: exactly one of these, which is what makes "nothing was silently dropped" a
#: checkable claim rather than an assertion.
CoverageDisposition = Literal[
    "policy_target",
    "supporting_context",
    "dependency",
    "non_normative",
    "duplicate_structure",
    "unresolved",
]

#: Dispositions that represent accounted-for content. `unresolved` is
#: deliberately excluded: it is the honest record of material the run could not
#: classify, and counting it as covered would defeat the entire measurement.
_ACCOUNTED = frozenset(
    {
        "policy_target",
        "supporting_context",
        "dependency",
        "non_normative",
        "duplicate_structure",
    }
)


class GraphRunConfig(BaseModel):
    """The effective extraction configuration for one run.

    Defaults follow the directive's conservative starting point. Two are worth
    stating explicitly because they trade throughput for correctness:

    ``dense_dedupe="off"`` — similar policy clauses may differ only by a
    negation, a threshold, a date, or a unit. The standard dedupe pass includes
    an LLM reconciliation call, and a merge performed before evidence
    verification silently destroys one of two genuinely different rules.

    ``parallel_workers=1`` — sequential execution gives stable ordering while
    the integration is being qualified. Concurrency is raised only once equality
    tests show no semantic or linkage change.
    """

    model_config = ConfigDict(extra="ignore")

    processing_mode: str = "many-to-one"
    extraction_contract: str = "dense"
    use_chunking: bool = True
    provenance: str = "detailed"
    dense_dedupe: str = "off"
    parallel_workers: int = Field(default=1, ge=1)
    chunk_token_target: int = Field(default=768, ge=1)
    skeleton_batch_tokens: int = Field(default=1536, ge=1)
    dense_fill_nodes_cap: int = Field(default=5, ge=1)

    template_name: str = ""
    template_schema_hash: str = ""
    model_provider: str | None = None
    model_deployment: str | None = None
    docling_version: str | None = None
    docling_graph_version: str | None = None


class GraphRunStats(BaseModel):
    """Counters the extractor reports, recorded rather than summarised.

    ``skeleton_batches_failed`` and ``dropped_chunk_ids`` are the two the
    directive names as hard coverage signals: a batch that could not be split or
    retried far enough loses whatever entities its chunks contained, and that
    loss is invisible in the returned graph.
    """

    model_config = ConfigDict(extra="ignore")

    chunks_total: int = 0
    chunks_with_nodes: int = 0
    skeleton_batches: int = 0
    skeleton_batches_failed: int = 0
    dropped_chunk_ids: list[int] = Field(default_factory=list)
    coverage_pass_recovered: int = 0
    nodes_discovered: int = 0
    nodes_after_merge: int = 0
    merges_applied: int = 0
    merges_vetoed: int = 0
    synthetic_parents: int = 0
    orphan_nodes: int = 0
    provenance_counts: dict[str, int] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retries: int = 0
    duration_seconds: float = 0.0

    @property
    def chunk_coverage(self) -> float:
        """Share of chunks that produced at least one candidate.

        A *useful* diagnostic, not a coverage proof. Some chunks are legitimately
        boilerplate, and a document can score highly here while the specific
        clause a reviewer needs was never discovered. Policy coverage is measured
        over canonical elements, in `CoverageReport`.
        """

        if not self.chunks_total:
            return 0.0
        return self.chunks_with_nodes / self.chunks_total

    @property
    def merge_retention(self) -> float:
        """Share of discovered nodes surviving the merge phase."""

        if not self.nodes_discovered:
            return 0.0
        return self.nodes_after_merge / self.nodes_discovered

    @property
    def has_dropped_content(self) -> bool:
        return bool(self.dropped_chunk_ids) or self.skeleton_batches_failed > 0


class ElementCoverage(BaseModel):
    """One canonical element's disposition, with the reason it was assigned."""

    model_config = ConfigDict(extra="ignore")

    element_id: str
    disposition: CoverageDisposition
    reason: str = ""
    candidate_keys: list[str] = Field(
        default_factory=list,
        description="Candidate identities that account for this element.",
    )


class CoverageReport(BaseModel):
    """Per-element accounting over the canonical document.

    This is the policy-coverage proof the directive requires, and it is
    deliberately separate from the extractor's chunk statistics.
    """

    model_config = ConfigDict(extra="ignore")

    total_leaf_elements: int = 0
    elements: list[ElementCoverage] = Field(default_factory=list)
    #: Leaves with no disposition at all. Distinct from `unresolved`, which is a
    #: deliberate "could not classify"; these were never considered, which is the
    #: silent loss the coverage gate exists to catch.
    unaccounted_element_ids: list[str] = Field(default_factory=list)

    @property
    def accounted(self) -> int:
        return sum(1 for e in self.elements if e.disposition in _ACCOUNTED)

    @property
    def unresolved(self) -> int:
        return sum(1 for e in self.elements if e.disposition == "unresolved")

    @property
    def coverage_ratio(self) -> float:
        if not self.total_leaf_elements:
            return 1.0
        return self.accounted / self.total_leaf_elements

    @property
    def is_complete(self) -> bool:
        """True only when every leaf was considered and none is unresolved."""

        return (
            not self.unaccounted_element_ids
            and self.unresolved == 0
            and len(self.elements) == self.total_leaf_elements
        )


class GraphRunGateFinding(BaseModel):
    """One reason a run cannot be presented as complete."""

    model_config = ConfigDict(extra="ignore")

    code: str
    severity: Literal["blocker", "warning"]
    detail: str


class GraphRunArtifact(BaseModel):
    """Everything recorded about one graph discovery run.

    Persisted so a run is reproducible and auditable after the process that
    produced it is gone: without the configuration and version fields, a graph
    that no longer reproduces cannot be explained.
    """

    model_config = ConfigDict(extra="ignore")

    run_id: str
    document_id: str
    source_hash: str = ""
    canonical_hash: str = ""
    config: GraphRunConfig = Field(default_factory=GraphRunConfig)
    stats: GraphRunStats = Field(default_factory=GraphRunStats)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    findings: list[GraphRunGateFinding] = Field(default_factory=list)
    status: RunStatus = "needs_review"
    error: str | None = None

    @property
    def blockers(self) -> list[GraphRunGateFinding]:
        return [f for f in self.findings if f.severity == "blocker"]


def evaluate_coverage_gates(artifact: GraphRunArtifact) -> GraphRunArtifact:
    """Apply the coverage gates and set the terminal status.

    Returns a copy rather than mutating, so the raw extractor output and the
    gated verdict remain separable when a decision is later questioned.

    The gates encode one rule: a run may admit uncertainty, but it may never
    conceal loss. Dropped chunks, failed skeleton batches, and elements that
    were never considered are blockers; unresolved material and weak provenance
    are warnings that route to review.
    """

    findings: list[GraphRunGateFinding] = []

    if artifact.stats.dropped_chunk_ids:
        findings.append(
            GraphRunGateFinding(
                code="dropped_chunks",
                severity="blocker",
                detail=(
                    f"{len(artifact.stats.dropped_chunk_ids)} chunk(s) were dropped: "
                    f"{artifact.stats.dropped_chunk_ids[:10]}"
                ),
            )
        )

    if artifact.stats.skeleton_batches_failed:
        findings.append(
            GraphRunGateFinding(
                code="skeleton_batches_failed",
                severity="blocker",
                detail=(
                    f"{artifact.stats.skeleton_batches_failed} skeleton batch(es) failed; "
                    "their content was not discovered"
                ),
            )
        )

    if artifact.coverage.unaccounted_element_ids:
        findings.append(
            GraphRunGateFinding(
                code="unaccounted_elements",
                severity="blocker",
                detail=(
                    f"{len(artifact.coverage.unaccounted_element_ids)} canonical element(s) "
                    "received no coverage disposition"
                ),
            )
        )

    if artifact.coverage.unresolved:
        findings.append(
            GraphRunGateFinding(
                code="unresolved_elements",
                severity="warning",
                detail=(
                    f"{artifact.coverage.unresolved} canonical element(s) could not be "
                    "classified and require review"
                ),
            )
        )

    weak = sum(
        artifact.stats.provenance_counts.get(strength, 0)
        for strength in ("observed", "derived", "unresolved")
    )
    if weak:
        findings.append(
            GraphRunGateFinding(
                code="weak_provenance",
                severity="warning",
                detail=(
                    f"{weak} candidate(s) lack verbatim provenance and are not eligible "
                    "for exact evidence without span resolution"
                ),
            )
        )

    if artifact.stats.synthetic_parents:
        findings.append(
            GraphRunGateFinding(
                code="synthetic_parents",
                severity="warning",
                detail=(
                    f"{artifact.stats.synthetic_parents} node(s) were attached to a "
                    "synthesised parent rather than a discovered one"
                ),
            )
        )

    if artifact.stats.orphan_nodes:
        findings.append(
            GraphRunGateFinding(
                code="orphan_nodes",
                severity="warning",
                detail=f"{artifact.stats.orphan_nodes} candidate(s) have no parent link",
            )
        )

    if artifact.status == "failed" or artifact.error:
        status: RunStatus = "failed"
    elif artifact.status == "unsupported_source":
        status = "unsupported_source"
    elif any(f.severity == "blocker" for f in findings):
        status = "failed"
    elif findings:
        status = "needs_review"
    else:
        status = "ready_for_review"

    return artifact.model_copy(update={"findings": findings, "status": status})
