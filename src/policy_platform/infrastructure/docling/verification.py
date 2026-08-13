"""Independent verification of an extraction package.

WHY A SEPARATE PASS
-------------------
The pass that *proposes* a package cannot also be the pass that *accepts* it.
A component that built a rule from a span has already decided the span was
right; asking it to confirm its own decision tests nothing. Verification here is
deliberately mechanical and adversarial: it re-derives what it can from the
canonical artifact and reports what it cannot.

The goal is not "the model is always right". It is **zero silent loss and zero
unsupported certainty**. A semantic mistake a reviewer can see and correct is an
acceptable outcome; a package that looks complete while missing a clause is not.

HARD FAILURE VERSUS REVIEWABLE UNCERTAINTY
-------------------------------------------
The distinction is the whole point of the module, and it is not a severity
scale. A hard failure means the package asserts something untrue — evidence that
does not round-trip, coverage that is missing, identity derived from a display
label. Those cannot be reviewed into correctness, because a reviewer reading the
package would be reading a false statement.

Reviewable conditions mean the package is honest but uncertain: weak provenance,
an ambiguous actor, an unsupported DMN construct. A human can resolve those, and
surfacing them is exactly what the package is for.
"""
from __future__ import annotations

from policy_platform.contracts.canonical_document import CanonicalDocument
from policy_platform.contracts.extraction_package import (
    PolicyExtractionPackage,
    VerificationSummary,
    rule_identity,
)
from policy_platform.infrastructure.projection.dmn_parity import check_parity, compile_decision

#: Rules whose evidence is entirely absent are not merely uncertain: the package
#: is asserting a policy exists with nothing behind it.
_UNSUPPORTED_RULE = "rule has no verified evidence"


def verify_package(
    package: PolicyExtractionPackage, document: CanonicalDocument | None = None
) -> VerificationSummary:
    """Re-check a package independently of whatever produced it.

    `document` is optional so the structural checks can run where the canonical
    artifact is not to hand, but its absence is itself reported: a package
    verified without re-reading the source has not had its central claim tested.
    """

    blockers: list[str] = []
    warnings: list[str] = []

    _check_evidence_round_trip(package, document, blockers, warnings)
    _check_coverage(package, blockers)
    _check_rule_support(package, blockers, warnings)
    _check_identity_independence(package, blockers)
    _check_cluster_membership(package, blockers)
    _check_projections(package, warnings)
    _check_projection_parity(package, blockers, warnings)
    _check_graph_health(package, blockers, warnings)

    return VerificationSummary(
        blockers=blockers,
        warnings=warnings,
        spans_verified=len(package.evidence_spans),
        spans_rejected=len(package.rejected_spans),
    )


def _check_evidence_round_trip(
    package: PolicyExtractionPackage,
    document: CanonicalDocument | None,
    blockers: list[str],
    warnings: list[str],
) -> None:
    """Re-slice every span from the canonical text rather than trusting it.

    This is the one check that cannot be delegated. The resolver already
    verified each span when it created it, but verification exists precisely to
    not take that on trust — a package can be assembled, cached, serialized, and
    transported between the two points.
    """

    if document is None:
        warnings.append(
            "canonical document unavailable: evidence round-trip could not be re-verified"
        )
        return

    if package.canonical_document.document_id != document.document_id:
        blockers.append(
            "canonical document does not match the package "
            f"({package.canonical_document.document_id} vs {document.document_id})"
        )
        return

    for span in package.evidence_spans:
        try:
            page_text = document.page_text(span.page)
        except KeyError:
            blockers.append(f"evidence {span.evidence_hash[:12]}: page {span.page} not in document")
            continue

        if page_text[span.page_start_offset : span.page_end_offset] != span.exact_text:
            blockers.append(
                f"evidence {span.evidence_hash[:12]} on page {span.page} does not round-trip "
                "to its canonical locator"
            )


def _check_coverage(package: PolicyExtractionPackage, blockers: list[str]) -> None:
    if package.coverage.unaccounted_element_ids:
        blockers.append(
            f"{len(package.coverage.unaccounted_element_ids)} canonical element(s) were never "
            "given a coverage disposition"
        )


def _check_rule_support(
    package: PolicyExtractionPackage, blockers: list[str], warnings: list[str]
) -> None:
    """Every rule must cite evidence, and every citation must exist."""

    known = {span.evidence_hash for span in package.evidence_spans}

    for rule in package.canonical_rules:
        if not rule.evidence_hashes:
            blockers.append(f"rule {rule.rule_key}: {_UNSUPPORTED_RULE}")
            continue

        dangling = [h for h in rule.evidence_hashes if h not in known]
        if dangling:
            blockers.append(
                f"rule {rule.rule_key} cites {len(dangling)} span(s) absent from the package"
            )

        if not rule.modality:
            warnings.append(f"rule {rule.rule_key}: modality was not determined")
        if not rule.actor:
            warnings.append(f"rule {rule.rule_key}: actor was not determined")
        if rule.unresolved_facts:
            warnings.append(
                f"rule {rule.rule_key}: {len(rule.unresolved_facts)} unresolved fact(s)"
            )


def _check_identity_independence(package: PolicyExtractionPackage, blockers: list[str]) -> None:
    """Re-derive each rule's identity and compare.

    A rule whose stored identity does not match the one derived from its
    evidence has an identity that came from somewhere else — a display label, a
    list position, a generated name. That is a zero-tolerance gate, because such
    an identity changes when the model rewords a title and silently breaks every
    stored reference to the rule.
    """

    seen: set[str] = set()
    for rule in package.canonical_rules:
        expected = rule_identity(
            document_id=package.canonical_document.document_id,
            evidence_hashes=rule.evidence_hashes,
            modality=rule.modality,
            action=rule.action,
        )
        if rule.rule_key != expected:
            blockers.append(
                f"rule {rule.rule_key}: identity is not derived from its verified evidence"
            )
        if rule.rule_key in seen:
            blockers.append(f"rule {rule.rule_key}: duplicate rule identity in the package")
        seen.add(rule.rule_key)


def _check_cluster_membership(package: PolicyExtractionPackage, blockers: list[str]) -> None:
    """A cluster pointing at a rule that is not present would publish a
    decision with a missing branch."""

    known = {rule.rule_key for rule in package.canonical_rules}
    for cluster in package.rule_clusters:
        missing = [key for key in cluster.rule_keys if key not in known]
        if missing:
            blockers.append(
                f"cluster {cluster.cluster_key} references {len(missing)} unknown rule(s)"
            )
        if not cluster.rule_keys:
            blockers.append(f"cluster {cluster.cluster_key} contains no rules")


def _check_projections(package: PolicyExtractionPackage, warnings: list[str]) -> None:
    """Unsupported constructs are reviewable, never blocking.

    A rule that cannot be projected to DMN is still a valid policy rule; it
    simply is not executable. Blocking on it would refuse whole documents for
    being expressive.

    Note the asymmetry with `_check_projection_parity`: *failing to project* is
    reviewable, but a projection that disagrees with its canonical rule is a
    hard failure, because it would execute something the policy does not say.
    """

    known_clusters = {cluster.cluster_key for cluster in package.rule_clusters}
    for projection in package.projections:
        if projection.cluster_key not in known_clusters:
            warnings.append(
                f"projection for {projection.cluster_key} has no matching rule cluster"
            )
        if projection.status != "candidate":
            warnings.append(
                f"projection for {projection.cluster_key} is {projection.status}"
                + (f": {projection.unsupported_reason}" if projection.unsupported_reason else "")
            )


def _check_projection_parity(
    package: PolicyExtractionPackage, blockers: list[str], warnings: list[str]
) -> None:
    """Compile every supported projection and prove it matches its canonical rule.

    This is the acceptance gate "zero supported DMN/FEEL compilation or parity
    failures". A projection that disagrees with the canonical rule it claims to
    represent is a hard failure and not a review item: the canonical rule is the
    semantic authority, so a disagreeing projection would execute something the
    approved policy does not say — and a reviewer reading the canonical rule
    would have no way to see it.
    """

    for decision in package.dmn_decisions:
        report = compile_decision(decision)
        if report.status == "not_projectable":
            # Compilation failure of an *executable* decision is a blocker: the
            # decision asserts it is executable while containing FEEL nothing
            # can run.
            blockers.append(
                f"{report.decision_name}: declared executable but does not compile "
                f"({'; '.join(report.errors[:3])})"
            )
            continue
        if report.status == "requires_review":
            warnings.append(f"{report.decision_name}: not executable, no parity check performed")
            continue

        parity = check_parity(decision)
        for mismatch in parity.mismatches:
            blockers.append(f"canonical/DMN parity failure — {mismatch.describe()}")
        for skipped in parity.skipped:
            warnings.append(f"parity skipped: {skipped}")


def _check_graph_health(
    package: PolicyExtractionPackage, blockers: list[str], warnings: list[str]
) -> None:
    """Carry the run's own coverage verdict into the package verdict.

    A package built on a run that dropped chunks is not made sound by the rules
    it did produce, so a run-level blocker stays a blocker here.
    """

    run = package.graph_run
    if run is None:
        return

    for finding in run.findings:
        if finding.severity == "blocker":
            blockers.append(f"graph run: {finding.detail}")
        else:
            warnings.append(f"graph run: {finding.detail}")

    if run.status == "failed":
        blockers.append("graph run terminated in a failed state")
