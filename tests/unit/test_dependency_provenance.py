"""Tests for the immutable-dependency integrity gate.

Two things are being proven here. First, that the allowlist genuinely
distinguishes immutable upstream code from mutable runtime artifacts — a gate
that quietly ignored `.py` files would pass forever while proving nothing.
Second, that the verifier reports drift rather than swallowing it, since the
directive's acceptance gate depends on a *failing* build when an upstream file
is edited.

The integrity check itself only runs when the optional `graph` extra is
installed; the tests that need it skip cleanly otherwise, so the default test
run on a machine without torch stays green.
"""
from __future__ import annotations

from importlib import metadata

import pytest

from policy_platform.infrastructure.docling.dependency_provenance import (
    PINNED_DISTRIBUTIONS,
    DependencyIntegrityError,
    IntegrityReport,
    is_mutable_runtime_path,
    require_dependency_integrity,
    verify_dependency_integrity,
)


def _graph_extra_installed() -> bool:
    try:
        metadata.distribution("docling-graph")
    except metadata.PackageNotFoundError:
        return False
    return True


requires_graph_extra = pytest.mark.skipif(
    not _graph_extra_installed(),
    reason="optional 'graph' extra (docling-graph) is not installed",
)


class TestMutableRuntimeAllowlist:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            "docling_graph/.env",
            "docling_graph/__pycache__/config.cpython-311.pyc",
            "docling_graph/config.pyc",
            "docling_graph-1.9.1.dist-info/RECORD",
            "docling_graph-1.9.1.dist-info/INSTALLER",
            "docling_graph/outputs/graph.json",
            "docling_graph/.cache/chunks.json",
        ],
    )
    def test_runtime_artifacts_are_mutable(self, path: str) -> None:
        assert is_mutable_runtime_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "docling_graph/__init__.py",
            "docling_graph/core/graph_builder.py",
            "docling_graph/pipeline/dense.py",
            "docling_graph/templategen/renderer.py",
            "docling/backend/docx_backend.py",
            "docling_graph-1.9.1.dist-info/METADATA",
            "docling_graph-1.9.1.dist-info/licenses/LICENSE",
        ],
    )
    def test_upstream_source_is_immutable(self, path: str) -> None:
        """Package code, metadata and licences must all be hash-verified.

        METADATA and LICENSE are included deliberately: a dependency whose
        declared licence could be edited without failing the build would make
        the recorded provenance meaningless.
        """

        assert not is_mutable_runtime_path(path)

    def test_windows_separators_are_normalized(self) -> None:
        """RECORD paths use forward slashes, but callers may pass native ones."""

        assert is_mutable_runtime_path("docling_graph\\__pycache__\\config.cpython-311.pyc")


class TestIntegrityReport:
    def test_empty_report_is_ok(self) -> None:
        assert IntegrityReport().ok

    @pytest.mark.parametrize(
        "field_name",
        ["modified_files", "missing_files", "missing_distributions", "version_mismatches"],
    )
    def test_any_finding_fails_the_report(self, field_name: str) -> None:
        report = IntegrityReport()
        getattr(report, field_name).append("docling-graph: something")
        assert not report.ok
        assert report.failure_summary()

    def test_summary_names_every_failure_category(self) -> None:
        report = IntegrityReport(
            modified_files=["docling_graph/core/x.py"],
            missing_files=["docling_graph/core/y.py"],
            missing_distributions=["docling"],
            version_mismatches=["docling-graph expected 1.9.1, found 1.8.0"],
        )
        summary = report.failure_summary()
        assert "not installed" in summary
        assert "version mismatch" in summary
        assert "modified file" in summary
        assert "missing file" in summary


class TestVerification:
    def test_missing_distribution_is_reported_not_raised(self) -> None:
        """A report lists every problem; only `require_` raises.

        This matters for the review surface: an operator needs to see all
        integrity failures at once, not the first one.
        """

        report = verify_dependency_integrity(("definitely-not-a-real-distribution",))
        assert not report.ok
        assert "definitely-not-a-real-distribution" in report.missing_distributions

    def test_require_raises_on_missing_distribution(self) -> None:
        with pytest.raises(DependencyIntegrityError):
            require_dependency_integrity(("definitely-not-a-real-distribution",))

    @requires_graph_extra
    def test_pinned_version_is_installed(self) -> None:
        installed = metadata.version("docling-graph")
        assert installed == PINNED_DISTRIBUTIONS["docling-graph"]

    @requires_graph_extra
    def test_installed_dependencies_are_unmodified(self) -> None:
        """The acceptance gate: no upstream file may differ from its digest."""

        report = require_dependency_integrity()
        assert report.ok, report.failure_summary()

    @requires_graph_extra
    def test_verification_actually_checked_files(self) -> None:
        """Guard against a vacuous pass.

        If the allowlist or RECORD parsing ever broke such that zero files were
        compared, `ok` would still be True. Asserting a substantial file count
        makes that failure mode visible.
        """

        report = verify_dependency_integrity(("docling-graph",))
        graph = next(d for d in report.distributions if d.name == "docling-graph")
        assert graph.files_verified > 50

    @requires_graph_extra
    def test_docling_conversion_code_is_verified_not_just_the_metapackage(self) -> None:
        """`docling` is a meta-package; its code lives in `docling-slim`.

        Verifying only `docling` would check a handful of metadata files and
        report success while every conversion backend, pipeline and chunker
        went unchecked.
        """

        report = verify_dependency_integrity()
        by_name = {d.name: d for d in report.distributions}
        assert "docling-slim" in by_name
        assert by_name["docling-slim"].files_verified > 100

    @requires_graph_extra
    def test_provenance_records_license_and_homepage(self) -> None:
        report = verify_dependency_integrity(("docling-graph",))
        graph = next(d for d in report.distributions if d.name == "docling-graph")
        assert graph.version == PINNED_DISTRIBUTIONS["docling-graph"]
        assert graph.license_name is not None
        assert graph.homepage is not None
