"""Tests for independent package verification.

The distinction being protected is hard failure versus reviewable uncertainty.
A hard failure means the package asserts something untrue and cannot be reviewed
into correctness; a reviewable condition means the package is honest but
uncertain. Conflating them either blocks documents for being expressive, or ships
a package that reads as complete while being false.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.evidence_resolution import ResolvedEvidence
from policy_platform.contracts.extraction_package import (
    ApplicationHandoff,
    CanonicalDocumentRef,
    PolicyExtractionPackage,
    ProjectionCandidate,
    RuleCandidate,
    RuleCluster,
    SourceReleaseRef,
    rule_identity,
)
from policy_platform.contracts.graph_run import (
    CoverageReport,
    ElementCoverage,
    GraphRunArtifact,
    GraphRunGateFinding,
)
from policy_platform.infrastructure.docling.verification import verify_package

TEXT = "Employees must apply in writing."


def _document(text: str = TEXT) -> CanonicalDocument:
    return CanonicalDocument(
        document_id="DOC",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text=text)],
        elements=[
            CanonicalElement(
                element_id="E1",
                element_type="paragraph",
                logical_order=0,
                text=text,
                source_fragments=[
                    SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
                ],
            )
        ],
        parser="docling",
    )


def _span(text: str = TEXT, evidence_hash: str = "h1") -> ResolvedEvidence:
    return ResolvedEvidence(
        element_id="E1",
        role="target",
        exact_text=text,
        page=1,
        page_start_offset=0,
        page_end_offset=len(text),
        element_start_offset=0,
        element_end_offset=len(text),
        evidence_hash=evidence_hash,
    )


def _rule(**overrides) -> RuleCandidate:
    explicit_key = overrides.pop("rule_key", None)
    fields = {
        "evidence_hashes": ["h1"],
        "modality": "must",
        "action": "apply",
        "actor": "Employees",
    }
    fields.update(overrides)
    derived = rule_identity(
        document_id="DOC",
        evidence_hashes=fields["evidence_hashes"],
        modality=fields.get("modality"),
        action=fields.get("action"),
    )
    return RuleCandidate(rule_key=explicit_key or derived, **fields)


def _package(**overrides) -> PolicyExtractionPackage:
    base = {
        "source_release": SourceReleaseRef(document_id="DOC"),
        "canonical_document": CanonicalDocumentRef(document_id="DOC"),
        "coverage": CoverageReport(
            total_leaf_elements=1,
            elements=[ElementCoverage(element_id="E1", disposition="policy_target")],
        ),
        "evidence_spans": [_span()],
        "canonical_rules": [_rule()],
        "application_handoff": ApplicationHandoff(idempotency_key="k"),
    }
    base.update(overrides)
    return PolicyExtractionPackage(**base)


class TestCleanPackage:
    def test_a_sound_package_passes(self) -> None:
        summary = verify_package(_package(), _document())
        assert summary.ok
        assert summary.blockers == []
        assert summary.spans_verified == 1


class TestHardFailures:
    def test_evidence_that_does_not_round_trip_blocks(self) -> None:
        """The one check that cannot be delegated to the resolver.

        A package can be assembled, cached, serialized and transported between
        resolution and verification.
        """

        package = _package(evidence_spans=[_span(text="Employees may apply in writing.")])
        summary = verify_package(package, _document())

        assert not summary.ok
        assert any("round-trip" in b for b in summary.blockers)

    def test_a_mismatched_canonical_document_blocks(self) -> None:
        package = _package(canonical_document=CanonicalDocumentRef(document_id="OTHER"))
        summary = verify_package(package, _document())

        assert any("does not match" in b for b in summary.blockers)

    def test_unaccounted_coverage_blocks(self) -> None:
        coverage = CoverageReport(
            total_leaf_elements=2,
            elements=[ElementCoverage(element_id="E1", disposition="policy_target")],
            unaccounted_element_ids=["E2"],
        )
        summary = verify_package(_package(coverage=coverage), _document())

        assert any("coverage disposition" in b for b in summary.blockers)

    def test_a_rule_with_no_evidence_blocks(self) -> None:
        """The package would assert a policy exists with nothing behind it."""

        rule = RuleCandidate(rule_key="r1", evidence_hashes=[])
        summary = verify_package(_package(canonical_rules=[rule]), _document())

        assert any("no verified evidence" in b for b in summary.blockers)

    def test_a_rule_citing_a_missing_span_blocks(self) -> None:
        rule = _rule(evidence_hashes=["h1", "h_missing"])
        summary = verify_package(_package(canonical_rules=[rule]), _document())

        assert any("absent from the package" in b for b in summary.blockers)

    def test_identity_not_derived_from_evidence_blocks(self) -> None:
        """A zero-tolerance gate: such an identity changes when a title is
        reworded and silently breaks every stored reference."""

        rule = _rule(rule_key="Employees-Must-Apply-Rule")
        summary = verify_package(_package(canonical_rules=[rule]), _document())

        assert any("not derived from its verified evidence" in b for b in summary.blockers)

    def test_duplicate_rule_identities_block(self) -> None:
        rule = _rule()
        summary = verify_package(_package(canonical_rules=[rule, rule.model_copy()]), _document())

        assert any("duplicate rule identity" in b for b in summary.blockers)

    def test_a_cluster_referencing_an_unknown_rule_blocks(self) -> None:
        """Publishing a decision with a missing branch."""

        package = _package(rule_clusters=[RuleCluster(cluster_key="c1", rule_keys=["nope"])])
        summary = verify_package(package, _document())

        assert any("unknown rule" in b for b in summary.blockers)

    def test_an_empty_cluster_blocks(self) -> None:
        package = _package(rule_clusters=[RuleCluster(cluster_key="c1")])
        summary = verify_package(package, _document())

        assert any("contains no rules" in b for b in summary.blockers)

    def test_a_failed_graph_run_blocks(self) -> None:
        """Rules a run did produce do not make a lossy run sound."""

        run = GraphRunArtifact(
            run_id="R1",
            document_id="DOC",
            status="failed",
            findings=[
                GraphRunGateFinding(
                    code="dropped_chunks", severity="blocker", detail="2 chunks were dropped"
                )
            ],
        )
        summary = verify_package(_package(graph_run=run), _document())

        assert any("dropped" in b for b in summary.blockers)
        assert any("failed state" in b for b in summary.blockers)


class TestReviewableConditions:
    @pytest.mark.parametrize("field", ["modality", "actor"])
    def test_undetermined_fields_warn_rather_than_block(self, field: str) -> None:
        """Honest uncertainty is what the package is for."""

        summary = verify_package(_package(canonical_rules=[_rule(**{field: None})]), _document())

        assert summary.ok
        assert any(field in w for w in summary.warnings)

    def test_unresolved_facts_warn(self) -> None:
        rule = _rule(unresolved_facts=["threshold units not stated"])
        summary = verify_package(_package(canonical_rules=[rule]), _document())

        assert summary.ok
        assert any("unresolved fact" in w for w in summary.warnings)

    def test_an_unprojectable_rule_warns_rather_than_blocks(self) -> None:
        """Blocking would refuse whole documents for being expressive."""

        package = _package(
            rule_clusters=[RuleCluster(cluster_key="c1", rule_keys=[_rule().rule_key])],
            projections=[
                ProjectionCandidate(
                    cluster_key="c1",
                    status="not_projectable",
                    unsupported_reason="temporal recurrence has no FEEL equivalent",
                )
            ],
        )
        summary = verify_package(package, _document())

        assert summary.ok
        assert any("not_projectable" in w for w in summary.warnings)

    def test_a_projection_without_a_cluster_warns(self) -> None:
        package = _package(projections=[ProjectionCandidate(cluster_key="ghost")])
        summary = verify_package(package, _document())

        assert summary.ok
        assert any("no matching rule cluster" in w for w in summary.warnings)

    def test_graph_run_warnings_are_carried_through(self) -> None:
        run = GraphRunArtifact(
            run_id="R1",
            document_id="DOC",
            findings=[
                GraphRunGateFinding(
                    code="weak_provenance", severity="warning", detail="3 candidates lack verbatim"
                )
            ],
        )
        summary = verify_package(_package(graph_run=run), _document())

        assert summary.ok
        assert any("weak_provenance" in w or "verbatim" in w for w in summary.warnings)


class TestProjectionParity:
    """The acceptance gate: zero supported DMN compilation or parity failures.

    Deliberately asymmetric with `TestReviewableConditions`. Failing to project
    is reviewable, because an inexpressible rule is still a valid policy rule.
    A projection that *disagrees* with its canonical rule is a hard failure,
    because it would execute something the approved policy does not say, and a
    reviewer reading the canonical rule would have no way to see it.
    """

    def _decision(self, entries: list[str], status=None):
        from policy_platform.contracts.formulation import (
            DmnDecision,
            DmnDecisionTable,
            DmnMappingStatus,
            DmnTableInput,
            DmnTableOutput,
            DmnTableRule,
        )

        return DmnDecision(
            dmn_mapping_status=status or DmnMappingStatus.EXECUTABLE,
            source_rule_indexes=[0],
            decision_table=DmnDecisionTable(
                hit_policy="UNIQUE",
                inputs=[
                    DmnTableInput(
                        label="expense.amount", expression="expense.amount", type="number"
                    )
                ],
                outputs=[DmnTableOutput(label="Outcome", name="outcome", type="string")],
                rules=[DmnTableRule(input_entries=entries, output_entries=['"approved"'])],
            ),
        )

    def test_a_faithful_projection_passes(self) -> None:
        package = _package(dmn_decisions=[self._decision([">=100"])])
        summary = verify_package(package, _document())

        assert summary.ok

    def test_an_executable_decision_that_does_not_compile_blocks(self) -> None:
        """It asserts it is executable while containing FEEL nothing can run."""

        package = _package(dmn_decisions=[self._decision(['date("2026-01-01")'])])
        summary = verify_package(package, _document())

        assert not summary.ok
        assert any("does not compile" in b for b in summary.blockers)

    def test_a_non_executable_decision_warns_rather_than_blocks(self) -> None:
        from policy_platform.contracts.formulation import DmnMappingStatus

        package = _package(
            dmn_decisions=[
                self._decision([">=100"], status=DmnMappingStatus.ENRICHMENT_REQUIRED)
            ]
        )
        summary = verify_package(package, _document())

        assert summary.ok
        assert any("no parity check performed" in w for w in summary.warnings)

    def test_a_disagreeing_projection_blocks(self) -> None:
        """Injected disagreement must be caught, or the gate proves nothing."""

        from policy_platform.infrastructure.docling import verification as module

        original = module.check_parity

        def failing(decision, source_rule_indexes=None, name=""):
            from policy_platform.infrastructure.projection.dmn_parity import ParityMismatch, ParityReport

            return ParityReport(
                scenarios_run=1,
                mismatches=[
                    ParityMismatch(
                        decision_name="d",
                        rule_index=0,
                        facts={"expense.amount": 100},
                        canonical="TRUE",
                        dmn="FALSE",
                    )
                ],
            )

        module.check_parity = failing
        try:
            summary = verify_package(_package(dmn_decisions=[self._decision([">=100"])]), _document())
        finally:
            module.check_parity = original

        assert not summary.ok
        assert any("parity failure" in b for b in summary.blockers)

    def test_a_package_with_no_projection_is_unaffected(self) -> None:
        """Most documents produce no executable projection at all."""

        assert verify_package(_package(), _document()).ok


class TestIndependence:
    def test_verifying_without_the_document_is_reported(self) -> None:
        """A package verified without re-reading the source has not had its
        central claim tested."""

        summary = verify_package(_package())

        assert any("could not be re-verified" in w for w in summary.warnings)

    def test_structural_checks_still_run_without_the_document(self) -> None:
        rule = RuleCandidate(rule_key="r1", evidence_hashes=[])
        summary = verify_package(_package(canonical_rules=[rule]))

        assert not summary.ok
        assert any("no verified evidence" in b for b in summary.blockers)

    def test_every_problem_is_reported_not_just_the_first(self) -> None:
        """A reviewer needs the whole list, not one item at a time."""

        coverage = CoverageReport(
            total_leaf_elements=2,
            elements=[],
            unaccounted_element_ids=["E2"],
        )
        package = _package(
            coverage=coverage,
            canonical_rules=[RuleCandidate(rule_key="r1", evidence_hashes=[])],
            rule_clusters=[RuleCluster(cluster_key="c1", rule_keys=["nope"])],
        )
        summary = verify_package(package, _document())

        assert len(summary.blockers) >= 3
