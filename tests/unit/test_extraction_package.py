"""Tests for the versioned extraction package.

The package is the handoff boundary, so the properties under test are the ones
that keep that boundary honest: identity that survives rewording, an idempotency
key that makes retries safe, and a readiness rule that cannot be satisfied by
half a document.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.evidence_resolution import RejectedEvidence, ResolvedEvidence
from policy_platform.contracts.extraction_package import (
    PACKAGE_VERSION,
    ApplicationHandoff,
    CanonicalDocumentRef,
    PolicyExtractionPackage,
    ProjectionCandidate,
    RuleCandidate,
    RuleCluster,
    SourceReleaseRef,
    VerificationSummary,
    build_idempotency_key,
    rule_identity,
)
from policy_platform.contracts.graph_run import CoverageReport, ElementCoverage


def _span(element_id: str, text: str, evidence_hash: str, role: str = "target") -> ResolvedEvidence:
    return ResolvedEvidence(
        element_id=element_id,
        role=role,  # type: ignore[arg-type]
        exact_text=text,
        page=1,
        page_start_offset=0,
        page_end_offset=len(text),
        element_start_offset=0,
        element_end_offset=len(text),
        evidence_hash=evidence_hash,
    )


def _coverage(count: int = 2, complete: bool = True) -> CoverageReport:
    report = CoverageReport(
        total_leaf_elements=count,
        elements=[
            ElementCoverage(element_id=f"E{i}", disposition="policy_target") for i in range(count)
        ],
    )
    if not complete:
        report.unaccounted_element_ids = ["E99"]
    return report


def _package(**overrides) -> PolicyExtractionPackage:
    base = {
        "source_release": SourceReleaseRef(document_id="DOC", source_hash="a" * 64),
        "canonical_document": CanonicalDocumentRef(document_id="DOC", canonical_hash="b" * 64),
        "coverage": _coverage(),
        "application_handoff": ApplicationHandoff(idempotency_key="k"),
    }
    base.update(overrides)
    return PolicyExtractionPackage(**base)


class TestHandoffReadiness:
    def test_verified_and_covered_package_is_ready(self) -> None:
        assert _package().is_handoff_ready

    def test_a_blocker_prevents_handoff(self) -> None:
        package = _package(
            verification=VerificationSummary(blockers=["evidence did not round-trip"])
        )
        assert not package.is_handoff_ready

    def test_incomplete_coverage_prevents_handoff(self) -> None:
        """Perfectly verified rules from half a document are still half a policy."""

        assert not _package(coverage=_coverage(complete=False)).is_handoff_ready

    def test_warnings_do_not_prevent_handoff(self) -> None:
        """Visible uncertainty is the intended outcome, not a failure."""

        package = _package(
            verification=VerificationSummary(warnings=["3 candidates lack verbatim provenance"])
        )
        assert package.is_handoff_ready


class TestEvidenceReferencing:
    def test_rules_reference_shared_spans_rather_than_embedding_them(self) -> None:
        """One span cited by three rules must not diverge between them."""

        package = _package(
            evidence_spans=[_span("E1", "A clause.", "h1"), _span("E2", "An exception.", "h2")],
            canonical_rules=[
                RuleCandidate(rule_key="r1", evidence_hashes=["h1", "h2"]),
                RuleCandidate(rule_key="r2", evidence_hashes=["h2"]),
            ],
        )

        assert [s.exact_text for s in package.evidence_for("r1")] == ["A clause.", "An exception."]
        assert [s.exact_text for s in package.evidence_for("r2")] == ["An exception."]

    def test_unknown_rule_resolves_to_no_evidence(self) -> None:
        assert _package().evidence_for("missing") == []

    def test_rejected_spans_are_carried_not_discarded(self) -> None:
        """A rejected citation is a review signal, not noise to drop."""

        package = _package(
            rejected_spans=[
                RejectedEvidence(element_id="E9", role="target", code="unknown_element")
            ]
        )
        assert len(package.rejected_spans) == 1


class TestRuleIdentity:
    def test_identity_survives_a_reworded_title(self) -> None:
        """A diff must show a rewording, not a deletion plus an insertion."""

        first = rule_identity(
            document_id="DOC", evidence_hashes=["h1"], modality="must", action="apply"
        )
        second = rule_identity(
            document_id="DOC", evidence_hashes=["h1"], modality="must", action="Apply"
        )
        assert first == second

    def test_identity_ignores_the_order_spans_were_emitted_in(self) -> None:
        forwards = rule_identity(
            document_id="DOC", evidence_hashes=["h1", "h2"], modality="must", action="apply"
        )
        backwards = rule_identity(
            document_id="DOC", evidence_hashes=["h2", "h1"], modality="must", action="apply"
        )
        assert forwards == backwards

    def test_different_evidence_gives_a_different_rule(self) -> None:
        first = rule_identity(
            document_id="DOC", evidence_hashes=["h1"], modality="must", action="apply"
        )
        second = rule_identity(
            document_id="DOC", evidence_hashes=["h2"], modality="must", action="apply"
        )
        assert first != second

    def test_negation_changes_identity(self) -> None:
        """'must' and 'must_not' are different rules, not one reworded rule."""

        must = rule_identity(
            document_id="DOC", evidence_hashes=["h1"], modality="must", action="exceed"
        )
        must_not = rule_identity(
            document_id="DOC", evidence_hashes=["h1"], modality="must_not", action="exceed"
        )
        assert must != must_not

    def test_same_text_in_another_document_is_a_different_rule(self) -> None:
        one = rule_identity(
            document_id="DOC-A", evidence_hashes=["h1"], modality="must", action="apply"
        )
        two = rule_identity(
            document_id="DOC-B", evidence_hashes=["h1"], modality="must", action="apply"
        )
        assert one != two


class TestIdempotency:
    def _key(self, **overrides) -> str:
        base = {
            "source_hash": "a" * 64,
            "canonical_hash_value": "b" * 64,
            "template_schema_hash": "c" * 64,
            "run_config_hash": "d" * 64,
        }
        base.update(overrides)
        return build_idempotency_key(**base)

    def test_identical_inputs_give_the_same_key(self) -> None:
        """A retry must resolve to the same intake, not a duplicate queue entry."""

        assert self._key() == self._key()

    @pytest.mark.parametrize(
        "field",
        ["source_hash", "canonical_hash_value", "template_schema_hash", "run_config_hash"],
    )
    def test_any_determining_input_changes_the_key(self, field: str) -> None:
        """Each of these genuinely is a different extraction."""

        assert self._key() != self._key(**{field: "f" * 64})

    def test_key_is_a_pure_function_of_its_inputs(self) -> None:
        """A timestamp or run id would make every retry look new, which is the
        duplication the key exists to prevent.

        Pinned to a fixed digest rather than merely asserting repeatability:
        any added entropy, and any change to the derivation itself, fails here
        instead of silently producing duplicate intakes in production.
        """

        assert self._key() == "a95ef2f4f03e07df538263c09a7e70ee6a6e109c7ded0694b8adc1078a8b5421"


class TestClusteringAndProjection:
    def test_clustering_preserves_individual_rules(self) -> None:
        """A reviewer must be able to reject one member without losing the rest."""

        package = _package(
            canonical_rules=[RuleCandidate(rule_key="r1"), RuleCandidate(rule_key="r2")],
            rule_clusters=[RuleCluster(cluster_key="c1", rule_keys=["r1", "r2"])],
        )

        assert len(package.canonical_rules) == 2
        assert package.rule_clusters[0].rule_keys == ["r1", "r2"]

    def test_projections_are_candidates_by_default(self) -> None:
        """Compilation and parity happen after approval, never here."""

        assert ProjectionCandidate(cluster_key="c1").status == "candidate"

    def test_unsupported_constructs_are_surfaced(self) -> None:
        package = _package(
            projections=[
                ProjectionCandidate(cluster_key="c1"),
                ProjectionCandidate(
                    cluster_key="c2",
                    status="not_projectable",
                    unsupported_reason="temporal recurrence has no FEEL equivalent",
                ),
            ]
        )
        unsupported = package.unsupported_projections()

        assert len(unsupported) == 1
        assert unsupported[0].unsupported_reason


class TestBoundary:
    def test_application_references_default_to_unset(self) -> None:
        """Extraction observes the application's decisions; it never makes them."""

        handoff = ApplicationHandoff(idempotency_key="k")
        assert handoff.existing_review_ref is None
        assert handoff.existing_release_ref is None
        assert handoff.search_projection_ref is None
        assert handoff.submitted is False

    def test_package_version_is_distinct_from_template_version(self) -> None:
        """A consumer must distinguish an envelope change from a producer change."""

        from policy_platform.contracts.policy_document_graph import TEMPLATE_VERSION

        assert PACKAGE_VERSION != TEMPLATE_VERSION
        assert _package().package_version == PACKAGE_VERSION

    def test_package_serializes_round_trip(self) -> None:
        """It crosses a service boundary, so it must survive serialization."""

        package = _package(
            evidence_spans=[_span("E1", "A clause.", "h1")],
            canonical_rules=[RuleCandidate(rule_key="r1", evidence_hashes=["h1"])],
        )
        restored = PolicyExtractionPackage.model_validate(package.model_dump())

        assert restored.evidence_for("r1")[0].exact_text == "A clause."

    def test_exact_text_is_not_mutated_by_serialization(self) -> None:
        text = "Costs must not exceed  5.0%  per annum."
        package = _package(evidence_spans=[_span("E1", text, "h1")])
        restored = PolicyExtractionPackage.model_validate(package.model_dump())

        assert restored.evidence_spans[0].exact_text == text
