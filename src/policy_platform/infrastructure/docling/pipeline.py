"""One-file extraction pipeline: source release to verified package.

This is the seam where the deterministic pieces meet. It runs the stages the
directive lists, records each one, and produces a package the existing
application can accept — without owning any of the review, approval, or
publication that follows.

WHY THE STAGES ARE RECORDED RATHER THAN JUST EXECUTED
------------------------------------------------------
PDF conversion of a 53-page document takes roughly 195 seconds, and dense
extraction adds many model calls on top. A pipeline that only returns a final
value gives an operator nothing when it dies at minute four, and no way to
resume. Each stage therefore records its inputs, outputs, status and timing, so
a failure names the step that failed and a retry can be reasoned about.

The stage records are extraction bookkeeping. They are deliberately *not* a
second review or approval state machine: the last stages are observations of
what the existing application decided, not decisions this pipeline makes.

WHAT RUNS WITHOUT A MODEL
--------------------------
Conversion, structural graph, reading plan, span resolution and coverage are all
deterministic. They are executed unconditionally, so a document can be ingested,
proven complete, and reviewed for fidelity even where dense extraction is
disabled or unconfigured. Candidate discovery is the only stage that needs a
model, and its absence degrades the run to `needs_review` rather than failing it.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.canonical_document import CanonicalDocument
from policy_platform.contracts.evidence_resolution import (
    EvidencePointer,
    build_coverage_report,
    resolve_evidence,
)
from policy_platform.contracts.extraction_package import (
    ApplicationHandoff,
    CanonicalDocumentRef,
    PolicyExtractionPackage,
    SourceReleaseRef,
    build_idempotency_key,
)
from policy_platform.contracts.graph_run import CoverageDisposition, GraphRunArtifact
from policy_platform.contracts.reading_plan import ReadingPlan, build_reading_plan
from policy_platform.contracts.structural_graph import (
    build_structural_graph,
    verify_structural_coverage,
)
from policy_platform.infrastructure.docling.converter import convert_document
from policy_platform.infrastructure.docling.verification import verify_package

StageStatus = Literal["ok", "skipped", "failed"]

#: The deterministic stages, in order. Named as constants so a stage record and
#: the code that produced it cannot drift apart through a typo.
STAGE_SOURCE_ACCEPTED = "source_accepted"
STAGE_CONVERTED = "docling_converted"
STAGE_CANONICAL_FROZEN = "canonical_artifact_frozen"
STAGE_STRUCTURE_BUILT = "deterministic_structure_built"
STAGE_GRAPH_DISCOVERY = "graph_discovery_completed"
STAGE_CONTEXT_UNITS = "context_units_assembled"
STAGE_SPANS_RESOLVED = "exact_spans_resolved"
STAGE_CANDIDATES = "canonical_candidates_proposed"
STAGE_VERIFIED = "verification_completed"


@dataclass
class StageRecord:
    """One executed stage, with the hashes needed to reason about a retry."""

    name: str
    status: StageStatus = "ok"
    input_hash: str = ""
    output_hash: str = ""
    detail: str = ""
    duration_seconds: float = 0.0


@dataclass
class ExtractionResult:
    """Everything one pipeline run produced.

    The canonical document, graph and plan are returned alongside the package
    because the review surfaces need them directly — rebuilding them to render a
    source explorer would be both slow and a second chance to diverge.
    """

    package: PolicyExtractionPackage
    document: CanonicalDocument
    plan: ReadingPlan
    stages: list[StageRecord] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(stage.status != "failed" for stage in self.stages)

    def stage(self, name: str) -> StageRecord | None:
        return next((s for s in self.stages if s.name == name), None)


class _StageTimer:
    """Records a stage's duration and status without repeating try/except.

    Every stage needs the same bookkeeping, and hand-writing it per stage is how
    one stage ends up silently unrecorded on the failure path — which is exactly
    the case an operator needs it for.
    """

    def __init__(self, records: list[StageRecord], name: str, input_hash: str = "") -> None:
        self.record = StageRecord(name=name, input_hash=input_hash)
        records.append(self.record)
        self._started = 0.0

    def __enter__(self) -> StageRecord:
        self._started = time.monotonic()
        return self.record

    def __exit__(self, exc_type, exc, _tb) -> bool:
        self.record.duration_seconds = round(time.monotonic() - self._started, 3)
        if exc is not None:
            self.record.status = "failed"
            self.record.detail = f"{exc_type.__name__}: {exc}"
        return False


def run_extraction(
    storage_path: str | Path,
    *,
    document_id: str = "",
    document_version_id: str = "",
    title: str = "",
    mime_type: str = "",
    converter=None,
    discover_candidates=None,
) -> ExtractionResult:
    """Run the deterministic pipeline for one source release.

    `discover_candidates` is injected rather than imported so the deterministic
    path never depends on a model being configured. When it is absent the run
    still produces a complete, verified, reviewable package — it simply carries
    no candidate rules.
    """

    path = Path(storage_path)
    stages: list[StageRecord] = []

    with _StageTimer(stages, STAGE_SOURCE_ACCEPTED) as record:
        source_bytes = path.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        record.output_hash = source_hash
        record.detail = f"{path.name} ({len(source_bytes)} bytes)"

    with _StageTimer(stages, STAGE_CONVERTED, source_hash) as record:
        document = convert_document(
            path,
            document_id=document_id or path.stem,
            source_hash=source_hash,
            converter=converter,
        )
        record.detail = f"{len(document.elements)} element(s), {document.page_count} page(s)"

    with _StageTimer(stages, STAGE_CANONICAL_FROZEN) as record:
        # Hashing the elements rather than the whole model keeps the value
        # stable against additive contract changes: a new optional field must
        # not make every stored citation look as though its source moved.
        canonical_document_hash = canonical_hash(
            [
                {
                    "id": element.element_id,
                    "type": element.element_type,
                    "text": element.text,
                    "fragments": [f.model_dump(include={"page", "start_offset", "end_offset"}) for f in element.source_fragments],
                }
                for element in document.elements
            ]
        )
        record.output_hash = canonical_document_hash
        failures = document.verify_fragments()
        if failures:
            record.status = "failed"
            record.detail = f"{len(failures)} fragment(s) do not resolve"
        else:
            record.detail = f"fidelity={document.fidelity}"

    with _StageTimer(stages, STAGE_STRUCTURE_BUILT, canonical_document_hash) as record:
        graph = build_structural_graph(document)
        problems = verify_structural_coverage(document, graph)
        if problems:
            record.status = "failed"
            record.detail = "; ".join(problems)
        else:
            record.detail = f"{len(graph.nodes)} node(s), {len(graph.edges)} edge(s)"

    with _StageTimer(stages, STAGE_CONTEXT_UNITS) as record:
        plan = build_reading_plan(document, graph)
        record.detail = f"{len(plan.units)} unit(s), exhaustive={plan.is_exhaustive}"
        if not plan.is_exhaustive:
            record.status = "failed"
            record.detail += f", {len(plan.uncovered_target_ids)} uncovered"

    graph_run: GraphRunArtifact | None = None
    pointers: list[EvidencePointer] = []
    with _StageTimer(stages, STAGE_GRAPH_DISCOVERY) as record:
        if discover_candidates is None:
            record.status = "skipped"
            record.detail = "candidate discovery not configured; deterministic stages only"
        else:
            graph_run, pointers = discover_candidates(document, graph, plan)
            record.detail = (
                f"{len(pointers)} pointer(s), status={graph_run.status if graph_run else 'unknown'}"
            )

    with _StageTimer(stages, STAGE_SPANS_RESOLVED) as record:
        resolution = resolve_evidence(document, pointers)
        record.detail = (
            f"{len(resolution.resolved)} resolved, {len(resolution.rejected)} rejected"
        )

    with _StageTimer(stages, STAGE_CANDIDATES) as record:
        dispositions = _dispositions_from_plan(plan, resolution.resolved, document, graph)
        coverage = build_coverage_report(document, graph, dispositions)
        record.detail = (
            f"coverage {coverage.accounted}/{coverage.total_leaf_elements}, "
            f"{len(coverage.unaccounted_element_ids)} unaccounted"
        )

    package = PolicyExtractionPackage(
        source_release=SourceReleaseRef(
            document_id=document.document_id,
            document_version_id=document_version_id,
            title=title or path.stem,
            source_hash=source_hash,
            mime_type=mime_type,
        ),
        canonical_document=CanonicalDocumentRef(
            document_id=document.document_id,
            canonical_hash=canonical_document_hash,
            parser=document.parser,
            converter_version=(
                document.conversion.converter_version if document.conversion else None
            ),
            page_count=document.page_count,
            element_count=len(document.elements),
        ),
        graph_run=graph_run,
        coverage=coverage,
        evidence_spans=resolution.resolved,
        rejected_spans=resolution.rejected,
        application_handoff=ApplicationHandoff(
            idempotency_key=build_idempotency_key(
                source_hash=source_hash,
                canonical_hash_value=canonical_document_hash,
                template_schema_hash=(
                    graph_run.config.template_schema_hash if graph_run else ""
                ),
                run_config_hash=canonical_hash(
                    graph_run.config.model_dump() if graph_run else {}
                ),
            )
        ),
    )

    with _StageTimer(stages, STAGE_VERIFIED) as record:
        package.verification = verify_package(package, document)
        record.detail = (
            f"{len(package.verification.blockers)} blocker(s), "
            f"{len(package.verification.warnings)} warning(s)"
        )
        if package.verification.blockers:
            record.status = "failed"

    return ExtractionResult(package=package, document=document, plan=plan, stages=stages)


def _dispositions_from_plan(
    plan: ReadingPlan, resolved, document: CanonicalDocument, graph: StructuralGraph
) -> dict[str, tuple[CoverageDisposition, str]]:
    """Assign each element the strongest role the run actually gave it.

    Ordering matters: an element cited as evidence is a policy target even if it
    also appeared as context elsewhere, and an element that was only ever
    context must not be reported as a target.

    Content elements that appear in no unit are deliberately left out, so
    `build_coverage_report` reports them as unaccounted rather than this function
    inventing a classification for them. That is the check that catches silent
    loss, and defaulting everything would disable it.
    """

    dispositions: dict[str, tuple[CoverageDisposition, str]] = {}

    for unit in plan.units:
        for element_id in unit.context_element_ids:
            reasons = unit.reasons_for(element_id)
            dispositions.setdefault(
                element_id,
                ("dependency", f"context for {unit.unit_id}: {', '.join(sorted(set(reasons)))}"),
            )

    for unit in plan.units:
        for element_id in unit.target_element_ids:
            dispositions[element_id] = (
                "supporting_context",
                f"read as a target in {unit.unit_id} but cited no evidence",
            )

    for span in resolved:
        dispositions[span.element_id] = (
            "policy_target",
            f"cited as {span.role} evidence",
        )

    _disposition_empty_headings(document, graph, dispositions)
    return dispositions


def _disposition_empty_headings(
    document: CanonicalDocument,
    graph: StructuralGraph,
    dispositions: dict[str, tuple[CoverageDisposition, str]],
) -> None:
    """Classify headings that govern no content.

    A heading is structural: it scopes rules rather than stating one, so it is
    never an extraction target. Headings that do govern content are already
    accounted for as `ancestor_heading` context of the units beneath them. A
    heading with nothing beneath it — a table-of-contents entry, a section label
    on its own line, a trailing appendix title — belongs to no unit and would
    otherwise be reported as unaccounted, which reads as lost policy content
    when it is nothing of the kind.

    Deliberately narrow. Only headings are classified here, and only those the
    structural graph confirms contain nothing. Widening this to "anything left
    over" would silence the very check that catches real loss.
    """

    containers = {edge.source for edge in graph.edges if edge.kind == "contains"}

    for element in document.elements:
        if element.element_id in dispositions:
            continue
        if element.element_type not in ("heading", "title"):
            continue
        if element.element_id in containers:
            continue
        dispositions[element.element_id] = (
            "non_normative",
            "section heading that governs no content",
        )
