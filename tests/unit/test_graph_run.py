"""Tests for graph run health, coverage accounting, and gate evaluation.

The gates encode one rule: a run may admit uncertainty, but it may never
conceal loss. These tests therefore concentrate on the difference between
"uncertain" (which routes to review) and "lost" (which must fail), because
collapsing the two is exactly the generic success state the directive forbids.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.graph_run import (
    CoverageReport,
    ElementCoverage,
    GraphRunArtifact,
    GraphRunConfig,
    GraphRunStats,
    evaluate_coverage_gates,
)


def _artifact(**kwargs) -> GraphRunArtifact:
    base = {"run_id": "RUN-1", "document_id": "DOC-1"}
    base.update(kwargs)
    return GraphRunArtifact(**base)


def _covered(count: int, disposition: str = "policy_target") -> CoverageReport:
    return CoverageReport(
        total_leaf_elements=count,
        elements=[
            ElementCoverage(element_id=f"E{i}", disposition=disposition) for i in range(count)
        ],
    )


class TestConservativeDefaults:
    def test_dedupe_is_off_by_default(self) -> None:
        """Similar clauses differ only by a negation, threshold, date or unit.

        Merging before evidence verification destroys one of two real rules.
        """

        assert GraphRunConfig().dense_dedupe == "off"

    def test_execution_is_sequential_by_default(self) -> None:
        assert GraphRunConfig().parallel_workers == 1

    def test_dense_contract_with_detailed_provenance(self) -> None:
        config = GraphRunConfig()
        assert config.extraction_contract == "dense"
        assert config.provenance == "detailed"
        assert config.use_chunking is True


class TestStats:
    def test_chunk_coverage_is_a_ratio(self) -> None:
        stats = GraphRunStats(chunks_total=10, chunks_with_nodes=8)
        assert stats.chunk_coverage == pytest.approx(0.8)

    def test_chunk_coverage_of_an_empty_run_is_zero_not_an_error(self) -> None:
        assert GraphRunStats().chunk_coverage == 0.0

    def test_merge_retention_reveals_over_merging(self) -> None:
        stats = GraphRunStats(nodes_discovered=100, nodes_after_merge=40)
        assert stats.merge_retention == pytest.approx(0.4)

    @pytest.mark.parametrize(
        ("stats", "expected"),
        [
            (GraphRunStats(), False),
            (GraphRunStats(dropped_chunk_ids=[3]), True),
            (GraphRunStats(skeleton_batches_failed=1), True),
        ],
    )
    def test_dropped_content_is_detected_from_either_signal(
        self, stats: GraphRunStats, expected: bool
    ) -> None:
        assert stats.has_dropped_content is expected


class TestCoverageAccounting:
    def test_complete_coverage_requires_every_leaf(self) -> None:
        assert _covered(3).is_complete

    def test_a_leaf_with_no_disposition_breaks_completeness(self) -> None:
        """Never-considered content is the silent loss the gate exists to catch."""

        report = _covered(3)
        report.unaccounted_element_ids = ["E9"]
        assert not report.is_complete

    def test_unresolved_is_not_counted_as_covered(self) -> None:
        """Counting an honest 'could not classify' as covered defeats the measure."""

        report = CoverageReport(
            total_leaf_elements=2,
            elements=[
                ElementCoverage(element_id="E0", disposition="policy_target"),
                ElementCoverage(element_id="E1", disposition="unresolved"),
            ],
        )
        assert report.accounted == 1
        assert report.unresolved == 1
        assert report.coverage_ratio == pytest.approx(0.5)
        assert not report.is_complete

    @pytest.mark.parametrize(
        "disposition",
        [
            "policy_target",
            "supporting_context",
            "dependency",
            "non_normative",
            "duplicate_structure",
        ],
    )
    def test_non_policy_dispositions_still_count_as_accounted(self, disposition: str) -> None:
        """'This is a page header' is an answer, not a gap."""

        assert _covered(1, disposition).is_complete

    def test_empty_document_is_trivially_covered(self) -> None:
        assert CoverageReport().coverage_ratio == 1.0
        assert CoverageReport().is_complete


class TestGates:
    def test_clean_run_is_ready_for_review(self) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(coverage=_covered(5), stats=GraphRunStats(chunks_total=5, chunks_with_nodes=5))
        )
        assert artifact.status == "ready_for_review"
        assert artifact.findings == []

    def test_dropped_chunks_fail_the_run(self) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(coverage=_covered(5), stats=GraphRunStats(dropped_chunk_ids=[2, 7]))
        )
        assert artifact.status == "failed"
        assert {f.code for f in artifact.blockers} == {"dropped_chunks"}

    def test_failed_skeleton_batches_fail_the_run(self) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(coverage=_covered(5), stats=GraphRunStats(skeleton_batches_failed=2))
        )
        assert artifact.status == "failed"
        assert any(f.code == "skeleton_batches_failed" for f in artifact.blockers)

    def test_unaccounted_elements_fail_the_run(self) -> None:
        report = _covered(3)
        report.unaccounted_element_ids = ["E9", "E10"]
        artifact = evaluate_coverage_gates(_artifact(coverage=report))
        assert artifact.status == "failed"
        assert any(f.code == "unaccounted_elements" for f in artifact.blockers)

    def test_unresolved_elements_route_to_review_rather_than_failing(self) -> None:
        """Admitted uncertainty is acceptable; concealed loss is not."""

        report = CoverageReport(
            total_leaf_elements=2,
            elements=[
                ElementCoverage(element_id="E0", disposition="policy_target"),
                ElementCoverage(element_id="E1", disposition="unresolved"),
            ],
        )
        artifact = evaluate_coverage_gates(_artifact(coverage=report))

        assert artifact.status == "needs_review"
        assert artifact.blockers == []
        assert any(f.code == "unresolved_elements" for f in artifact.findings)

    @pytest.mark.parametrize("strength", ["observed", "derived", "unresolved"])
    def test_weak_provenance_warns_but_does_not_fail(self, strength: str) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(
                coverage=_covered(2),
                stats=GraphRunStats(provenance_counts={"verbatim": 5, strength: 3}),
            )
        )
        assert artifact.status == "needs_review"
        assert any(f.code == "weak_provenance" for f in artifact.findings)

    def test_verbatim_only_provenance_raises_no_warning(self) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(coverage=_covered(2), stats=GraphRunStats(provenance_counts={"verbatim": 8}))
        )
        assert artifact.status == "ready_for_review"

    def test_synthetic_parents_and_orphans_are_reported(self) -> None:
        artifact = evaluate_coverage_gates(
            _artifact(
                coverage=_covered(2),
                stats=GraphRunStats(synthetic_parents=1, orphan_nodes=4),
            )
        )
        codes = {f.code for f in artifact.findings}
        assert {"synthetic_parents", "orphan_nodes"} <= codes
        assert artifact.status == "needs_review"

    def test_unsupported_source_is_preserved_not_overwritten(self) -> None:
        """An image-only source must stay distinguishable from a failed run."""

        artifact = evaluate_coverage_gates(
            _artifact(status="unsupported_source", coverage=_covered(0))
        )
        assert artifact.status == "unsupported_source"

    def test_recorded_error_always_fails(self) -> None:
        artifact = evaluate_coverage_gates(_artifact(coverage=_covered(3), error="backend timeout"))
        assert artifact.status == "failed"

    def test_gate_evaluation_does_not_mutate_the_input(self) -> None:
        """The raw extractor output and the gated verdict stay separable."""

        original = _artifact(coverage=_covered(2), stats=GraphRunStats(dropped_chunk_ids=[1]))
        gated = evaluate_coverage_gates(original)

        assert original.findings == []
        assert original.status == "needs_review"
        assert gated.status == "failed"

    def test_a_run_never_reports_plain_success(self) -> None:
        """There is deliberately no status meaning 'done, nothing to look at'."""

        from policy_platform.contracts.graph_run import RunStatus
        from typing import get_args

        assert "success" not in get_args(RunStatus)
        assert "completed" not in get_args(RunStatus)
