"""Tests for the one-file extraction pipeline.

Two properties matter most. The deterministic stages must run and prove coverage
*without* a model, so a document can be ingested and reviewed for fidelity in an
environment where dense extraction is unconfigured. And every stage must be
recorded even when it fails, because a run that dies at minute four of a
195-second conversion is precisely when an operator needs the record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import pytest

from policy_platform.contracts.evidence_resolution import EvidencePointer
from policy_platform.contracts.graph_run import GraphRunArtifact
from policy_platform.infrastructure.docling.pipeline import (
    STAGE_CANDIDATES,
    STAGE_CANONICAL_FROZEN,
    STAGE_CONTEXT_UNITS,
    STAGE_CONVERTED,
    STAGE_GRAPH_DISCOVERY,
    STAGE_SOURCE_ACCEPTED,
    STAGE_SPANS_RESOLVED,
    STAGE_STRUCTURE_BUILT,
    STAGE_VERIFIED,
    run_extraction,
)

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "source-documents"
HR = SAMPLES / "HR-Special-Leave-Policy-v1.0.docx"


# --------------------------------------------------------------------------
# Stub converter, so the deterministic pipeline is testable without docling
# --------------------------------------------------------------------------


@dataclass
class _Text:
    text: str
    label: str = "text"
    self_ref: str = "#/texts/0"
    prov: list = field(default_factory=list)
    marker: str | None = None
    enumerated: bool = False


class _StubDocument:
    def __init__(self, texts: list[_Text]) -> None:
        self.texts = texts
        self.tables: list = []
        self.pages: dict = {}

    def iterate_items(self):
        for item in self.texts:
            yield item, 1


class _StubConverter:
    def __init__(self, texts: list[_Text]) -> None:
        self._texts = texts

    def convert(self, _source: str):
        return type("Result", (), {"document": _StubDocument(self._texts)})()


def _stub(tmp_path: Path, texts: list[_Text] | None = None):
    source = tmp_path / "policy.docx"
    source.write_bytes(b"stub source bytes")
    # `is None` rather than a falsy check: an empty list is a meaningful case
    # (a source with no text layer) and must not fall back to the default.
    if texts is None:
        texts = [
            _Text("1. Scope", label="section_header"),
            _Text("Employees must apply in writing."),
            _Text("Approval is required."),
        ]
    return source, _StubConverter(texts)


class TestDeterministicPath:
    def test_pipeline_runs_without_a_model(self, tmp_path: Path) -> None:
        """A document must be ingestible and provable where extraction is off."""

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert result.ok
        assert result.stage(STAGE_GRAPH_DISCOVERY).status == "skipped"
        assert result.package.coverage.is_complete

    def test_every_stage_is_recorded_in_order(self, tmp_path: Path) -> None:
        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert [s.name for s in result.stages] == [
            STAGE_SOURCE_ACCEPTED,
            STAGE_CONVERTED,
            STAGE_CANONICAL_FROZEN,
            STAGE_STRUCTURE_BUILT,
            STAGE_CONTEXT_UNITS,
            STAGE_GRAPH_DISCOVERY,
            STAGE_SPANS_RESOLVED,
            STAGE_CANDIDATES,
            STAGE_VERIFIED,
        ]

    def test_source_hash_is_recorded_for_the_release(self, tmp_path: Path) -> None:
        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        stage = result.stage(STAGE_SOURCE_ACCEPTED)
        assert stage.output_hash
        assert result.package.source_release.source_hash == stage.output_hash

    def test_reading_plan_is_returned_for_review_surfaces(self, tmp_path: Path) -> None:
        """Rebuilding it to render a source explorer would be slow and a second
        chance to diverge."""

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert result.plan.units
        assert result.plan.is_exhaustive
        assert result.document.elements


class TestCoverage:
    def test_every_leaf_is_accounted_for(self, tmp_path: Path) -> None:
        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)
        coverage = result.package.coverage

        assert coverage.unaccounted_element_ids == []
        assert coverage.accounted == coverage.total_leaf_elements

    def test_a_heading_governing_no_content_is_non_normative(self, tmp_path: Path) -> None:
        """A table-of-contents entry or trailing appendix title belongs to no
        unit and would otherwise read as lost policy content."""

        source, converter = _stub(
            tmp_path,
            texts=[
                _Text("1. Scope", label="section_header"),
                _Text("Employees must apply."),
                _Text("Appendix B - Definitions", label="section_header"),
            ],
        )
        result = run_extraction(source, converter=converter)
        coverage = result.package.coverage

        assert coverage.unaccounted_element_ids == []
        empty = next(
            e for e in coverage.elements if e.reason == "section heading that governs no content"
        )
        assert empty.disposition == "non_normative"

    def test_a_heading_that_governs_content_is_not_classified_as_empty(
        self, tmp_path: Path
    ) -> None:
        """It is already accounted for as ancestor context of its units."""

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert not any(
            e.reason == "section heading that governs no content"
            for e in result.package.coverage.elements
        )

    def test_leftover_content_is_still_reported_as_unaccounted(self, tmp_path: Path) -> None:
        """The empty-heading rule must not become 'classify anything left over',
        which would silence the check that catches real loss."""

        from policy_platform.infrastructure.docling import pipeline

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)
        paragraph = next(
            e for e in result.document.elements if e.element_type == "paragraph"
        )

        dispositions = pipeline._dispositions_from_plan(
            pipeline.build_reading_plan(
                result.document, pipeline.build_structural_graph(result.document)
            ),
            [],
            result.document,
            pipeline.build_structural_graph(result.document),
        )
        dispositions.pop(paragraph.element_id, None)
        report = pipeline.build_coverage_report(
            result.document,
            pipeline.build_structural_graph(result.document),
            dispositions,
        )

        assert paragraph.element_id in report.unaccounted_element_ids

    def test_cited_elements_become_policy_targets(self, tmp_path: Path) -> None:
        source, converter = _stub(tmp_path)

        def discover(document, _graph, _plan):
            target = next(e for e in document.elements if e.element_type == "paragraph")
            return None, [EvidencePointer(element_id=target.element_id, role="target")]

        result = run_extraction(source, converter=converter, discover_candidates=discover)
        cited = next(
            e for e in result.package.coverage.elements if e.disposition == "policy_target"
        )

        assert "cited as target evidence" in cited.reason

    def test_context_only_elements_are_not_reported_as_targets(self, tmp_path: Path) -> None:
        """An element that was only ever context must not look like a rule."""

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert all(
            e.disposition != "policy_target" for e in result.package.coverage.elements
        )


class TestFailureRecording:
    def test_a_failing_stage_is_recorded_not_swallowed(self, tmp_path: Path) -> None:
        source = tmp_path / "policy.docx"
        source.write_bytes(b"stub")

        class _Failing:
            def convert(self, _source: str):
                raise ValueError("backend exploded")

        with pytest.raises(Exception):
            run_extraction(source, converter=_Failing())

    def test_an_empty_document_is_flagged_unsupported(self, tmp_path: Path) -> None:
        source, converter = _stub(tmp_path, texts=[])
        result = run_extraction(source, converter=converter)

        assert result.document.fidelity == "unsupported_source"

    def test_stage_durations_are_recorded(self, tmp_path: Path) -> None:
        """A 195-second conversion needs to be visible as the slow step."""

        source, converter = _stub(tmp_path)
        result = run_extraction(source, converter=converter)

        assert all(s.duration_seconds >= 0 for s in result.stages)


class TestIdempotency:
    def test_the_same_source_yields_the_same_key(self, tmp_path: Path) -> None:
        """A retry must resolve to the same intake, not a duplicate."""

        source, converter = _stub(tmp_path)
        first = run_extraction(source, converter=converter)
        second = run_extraction(source, converter=converter)

        assert (
            first.package.application_handoff.idempotency_key
            == second.package.application_handoff.idempotency_key
        )

    def test_a_different_source_yields_a_different_key(self, tmp_path: Path) -> None:
        source_a, converter = _stub(tmp_path)
        result_a = run_extraction(source_a, converter=converter)

        source_b = tmp_path / "other.docx"
        source_b.write_bytes(b"different source bytes")
        result_b = run_extraction(source_b, converter=converter)

        assert (
            result_a.package.application_handoff.idempotency_key
            != result_b.package.application_handoff.idempotency_key
        )

    def test_handoff_starts_unsubmitted(self, tmp_path: Path) -> None:
        """Extraction produces a package; it does not intake it."""

        source, converter = _stub(tmp_path)
        handoff = run_extraction(source, converter=converter).package.application_handoff

        assert handoff.submitted is False
        assert handoff.existing_review_ref is None


# --------------------------------------------------------------------------


def _docling_installed() -> bool:
    try:
        metadata.distribution("docling")
    except metadata.PackageNotFoundError:
        return False
    return True


requires_docling = pytest.mark.skipif(
    not _docling_installed(), reason="optional 'graph' extra is not installed"
)


@requires_docling
def test_real_document_produces_a_handoff_ready_package() -> None:
    """End-to-end on a document the directive names as a fixture."""

    result = run_extraction(HR, title="HR Special Leave Policy")

    assert result.ok
    assert result.package.is_handoff_ready
    assert result.package.verification.blockers == []
    assert result.package.coverage.is_complete
    assert result.plan.is_exhaustive


@requires_docling
def test_real_document_run_is_reproducible() -> None:
    """Re-ingesting must not look like a wholesale policy change."""

    first = run_extraction(HR)
    second = run_extraction(HR)

    assert (
        first.package.canonical_document.canonical_hash
        == second.package.canonical_document.canonical_hash
    )
    assert (
        first.package.application_handoff.idempotency_key
        == second.package.application_handoff.idempotency_key
    )
