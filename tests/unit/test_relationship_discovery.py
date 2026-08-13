"""Relationship discovery: typed links that do not depend on executability.

The defect being closed: relationships used to be derived from a shared DMN
decision table, so a rule that stayed `ambiguous` or `enrichment_required` — the
case where a reviewer most needs to see what a rule depends on — was reported as
related to nothing. These tests assert the opposite property directly: every
rule below is non-executable, and every one still carries its table and its
section.

Similarity-based detectors (embedding and lexical) and the cross-reference
detector were removed after they were found to be unreachable: extraction
composes the live detectors directly and never called them. The tests that
exercised them went with them rather than being left to assert behaviour no
run can produce.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.relationships import (
    PolicyRelationship,
    PolicyRelationshipGraph,
    PolicyRelationshipType,
)
from policy_platform.infrastructure.correlation import relationship_discovery as rd
from tests.fixtures.policy_domains import (
    compliance_fixture,
    finance_procurement_fixture,
    it_hardware_fixture,
    labor_law_fixture,
    ordered_procedure_fixture,
)


def _live_graph(fixture) -> PolicyRelationshipGraph:
    """Compose exactly the detectors extraction runs, in the order it runs them."""

    anchors = _anchors_from(fixture)
    graph = PolicyRelationshipGraph()
    graph.extend(rd.discover_structural_relationships(anchors))
    graph.extend(rd.discover_semantic_role_relationships(anchors))
    graph.extend(rd.discover_enumeration_relationships(anchors))
    return graph


def _anchors_from(fixture, *, rule_kinds: dict[str, str] | None = None) -> list[rd.RuleAnchor]:
    """One anchor per non-heading element, all deliberately non-executable.

    `fact_paths` is left empty everywhere, which is exactly the state a rule is
    in when the DMN projection came back `enrichment_required`. If any assertion
    below passes only because a shared fact path existed, the test would not be
    testing what it claims to.
    """

    kinds = rule_kinds or {}
    anchors = []
    for element in fixture.elements:
        if element.is_heading:
            continue
        anchors.append(
            rd.RuleAnchor(
                rule_id=f"R-{element.element_id}",
                element_ids=[element.element_id],
                unit_id=f"U-{element.section_path[-1] if element.section_path else 'root'}",
                cluster_id=f"C-{element.section_path[0] if element.section_path else 'root'}",
                text=element.text,
                section_path=list(element.section_path),
                table_id=element.table_id,
                table_row_index=element.table_row_index,
                references=list(element.references),
                rule_kind=kinds.get(element.element_id, "obligation"),
                order=element.order,
            )
        )
    return anchors


# ---------------------------------------------------------------------------
# Structure: table, cluster, ordering
# ---------------------------------------------------------------------------


def test_table_rows_are_linked_to_their_table_without_any_dmn_projection() -> None:
    fixture = it_hardware_fixture()
    anchors = _anchors_from(fixture)

    edges = rd.discover_structural_relationships(anchors)
    table_edges = [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.TABLE_ROW_OF
    ]

    assert len(table_edges) == 2, "two non-anchor rows must each link to the table anchor"
    assert all(edge.target_rule_id == "R-IT-R1" for edge in table_edges)
    assert all("same_table" in edge.evidence.signals for edge in table_edges)
    assert all(edge.origin == "structural" for edge in table_edges)


def test_ordered_procedure_steps_are_linked_by_precedence() -> None:
    fixture = ordered_procedure_fixture()
    anchors = _anchors_from(fixture)

    edges = rd.discover_structural_relationships(anchors)
    precedes = [
        (edge.source_rule_id, edge.target_rule_id)
        for edge in edges
        if edge.relationship_type is PolicyRelationshipType.PRECEDES
    ]

    assert ("R-PRC-S1", "R-PRC-S2") in precedes
    assert ("R-PRC-S2", "R-PRC-S3") in precedes
    assert ("R-PRC-S3", "R-PRC-S4") in precedes


def test_precedence_is_not_claimed_across_sections() -> None:
    """An ordering claim across sections would be an assumption, not an observation."""

    fixture = ordered_procedure_fixture()
    anchors = _anchors_from(fixture)
    edges = rd.discover_structural_relationships(anchors)

    for edge in edges:
        if edge.relationship_type is not PolicyRelationshipType.PRECEDES:
            continue
        source = next(a for a in anchors if a.rule_id == edge.source_rule_id)
        target = next(a for a in anchors if a.rule_id == edge.target_rule_id)
        assert source.section_path == target.section_path


# ---------------------------------------------------------------------------
# Normative roles: exception, approval, definition
# ---------------------------------------------------------------------------


def test_exception_links_to_the_rule_it_qualifies() -> None:
    fixture = compliance_fixture()
    anchors = _anchors_from(
        fixture,
        rule_kinds={
            "CMP-P1": "prohibition",
            "CMP-P2": "exception",
            "CMP-P3": "evidence_requirement",
        },
    )

    edges = rd.discover_semantic_role_relationships(anchors)
    exceptions = [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.EXCEPTION_TO
    ]

    assert exceptions, "the exception must name the prohibition it carves out of"
    assert exceptions[0].source_rule_id == "R-CMP-P2"
    assert exceptions[0].target_rule_id == "R-CMP-P1"


def test_approval_requirement_links_to_the_rule_it_gates() -> None:
    fixture = finance_procurement_fixture()
    anchors = _anchors_from(
        fixture,
        rule_kinds={"FIN-P1": "obligation", "FIN-P4": "approval_requirement"},
    )

    edges = rd.discover_semantic_role_relationships(anchors)
    approvals = [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.APPROVAL_FOR
    ]
    assert approvals
    assert approvals[0].source_rule_id == "R-FIN-P4"


def test_definition_links_to_every_rule_that_uses_the_term() -> None:
    fixture = labor_law_fixture()
    anchors = _anchors_from(fixture, rule_kinds={"LL-P1": "definition", "LL-P2": "definition"})

    edges = rd.discover_semantic_role_relationships(anchors)
    definitions = [
        edge
        for edge in edges
        if edge.relationship_type is PolicyRelationshipType.DEFINITION_USED_BY
        and edge.source_rule_id == "R-LL-P1"
    ]

    assert any(edge.target_rule_id == "R-LL-P3" for edge in definitions), (
        "'continuous service' is defined in Article 2 and used in Article 74"
    )


# ---------------------------------------------------------------------------
# Graph semantics
# ---------------------------------------------------------------------------


def test_symmetric_edges_deduplicate_but_asymmetric_ones_do_not() -> None:
    graph = PolicyRelationshipGraph()
    forward = PolicyRelationship(
        relationship_type=PolicyRelationshipType.SAME_DECISION,
        source_rule_id="A",
        target_rule_id="B",
    )
    reverse = PolicyRelationship(
        relationship_type=PolicyRelationshipType.SAME_DECISION,
        source_rule_id="B",
        target_rule_id="A",
    )
    assert graph.add(forward) is True
    assert graph.add(reverse) is False

    override = PolicyRelationship(
        relationship_type=PolicyRelationshipType.OVERRIDES, source_rule_id="A", target_rule_id="B"
    )
    counter = PolicyRelationship(
        relationship_type=PolicyRelationshipType.OVERRIDES, source_rule_id="B", target_rule_id="A"
    )
    assert graph.add(override) is True
    assert graph.add(counter) is True, (
        "contradictory precedence claims must both survive so they can be reported"
    )


def test_stronger_evidence_wins_when_the_same_edge_is_discovered_twice() -> None:
    """Discovery order encodes evidence strength; the first edge is kept."""

    fixture = labor_law_fixture()
    anchors = _anchors_from(fixture)
    graph = PolicyRelationshipGraph()
    graph.extend(rd.discover_structural_relationships(anchors))
    before = len(graph.relationships)
    assert before, "the fixture must produce at least one structural edge"
    graph.extend(rd.discover_structural_relationships(anchors))
    assert len(graph.relationships) == before


def test_related_rule_ids_are_derivable_from_the_graph() -> None:
    fixture = it_hardware_fixture()
    anchors = _anchors_from(fixture)
    graph = PolicyRelationshipGraph()
    graph.extend(rd.discover_structural_relationships(anchors))

    related = graph.related_rule_ids("R-IT-R2")
    assert "R-IT-R1" in related


# ---------------------------------------------------------------------------
# Proximity is a candidate, never a finding
# ---------------------------------------------------------------------------


def test_window_co_location_is_a_candidate_not_a_finding() -> None:
    """Two rules printed near each other are not one decision.

    A retention rule and an audit rule that happen to share a window are
    adjacent on the page. Recording that as a `same_decision` *finding* would
    put layout into the record a reviewer trusts, and a reviewer reading
    "Related to: R-7" reasonably reads it as a statement about the policy.
    """

    unrelated = [
        rd.RuleAnchor(
            rule_id="R-retention",
            element_ids=["E1"],
            unit_id="U0001",
            cluster_id="U0001",
            text="Authorisation records must be retained for seven years from the transfer date.",
            section_path=["5. Records"],
            rule_kind="retention",
            order=0,
        ),
        rd.RuleAnchor(
            rule_id="R-audit",
            element_ids=["E2"],
            unit_id="U0001",
            cluster_id="U0001",
            text="An internal audit of access provisioning is performed each quarter.",
            section_path=["5. Records"],
            rule_kind="obligation",
            order=1,
        ),
    ]

    edges = rd.discover_structural_relationships(unrelated)
    same_decision = [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.SAME_DECISION
    ]

    assert same_decision, "co-location should still be surfaced for review"
    assert all(edge.state == "candidate" for edge in same_decision)
    assert all("same_window" in edge.evidence.signals for edge in same_decision)

    graph = PolicyRelationshipGraph()
    graph.extend(edges)
    assert graph.related_rule_ids("R-retention") == [], (
        "the flat view must contain only confirmed relations"
    )
    assert graph.candidates(), "the candidate remains visible in the typed graph"


def test_adjacent_prose_is_not_an_ordering_claim() -> None:
    """`precedes` needs procedural evidence, not adjacency."""

    prose = [
        rd.RuleAnchor(
            rule_id="R-a",
            element_ids=["E1"],
            unit_id="U1",
            cluster_id="U1",
            text="Restricted data must not leave the approved processing environment.",
            section_path=["5. Restricted data"],
            order=0,
        ),
        rd.RuleAnchor(
            rule_id="R-b",
            element_ids=["E2"],
            unit_id="U1",
            cluster_id="U1",
            text="Authorisation records must be retained for seven years.",
            section_path=["5. Restricted data"],
            order=1,
        ),
    ]

    edges = rd.discover_structural_relationships(prose)
    assert not [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.PRECEDES
    ]


def test_numbered_steps_are_a_confirmed_ordering_claim() -> None:
    fixture = ordered_procedure_fixture()
    anchors = _anchors_from(fixture)

    edges = rd.discover_structural_relationships(anchors)
    precedes = [
        edge for edge in edges if edge.relationship_type is PolicyRelationshipType.PRECEDES
    ]

    assert precedes
    assert all(edge.state == "confirmed" for edge in precedes)
    assert all("ordinal_marker" in edge.evidence.signals for edge in precedes)


def test_structural_edges_are_confirmed() -> None:
    table_edges = [
        edge
        for edge in rd.discover_structural_relationships(_anchors_from(it_hardware_fixture()))
        if edge.relationship_type is PolicyRelationshipType.TABLE_ROW_OF
    ]

    assert table_edges and all(edge.state == "confirmed" for edge in table_edges)


@pytest.mark.parametrize(
    "factory",
    [it_hardware_fixture, labor_law_fixture, finance_procurement_fixture, compliance_fixture],
    ids=lambda f: f().name,
)
def test_every_domain_produces_a_non_empty_graph_without_executable_rules(factory) -> None:
    fixture = factory()
    assert all(not anchor.fact_paths for anchor in _anchors_from(fixture))

    graph = _live_graph(fixture)

    assert graph.relationships, "a non-executable rule set must still have relationships"


# ---------------------------------------------------------------------------
# Positional role edges are candidates, never findings
#
# "The exception nearest above it" is a fact about the page, not about which
# rule the exception carves out of. Persisting it as `confirmed` presents a
# guess as a determination, and a reviewer reading a confirmed edge has no
# reason to check it.
# ---------------------------------------------------------------------------


def _role_anchors(*rows: tuple[str, str, str, str]) -> list[rd.RuleAnchor]:
    """(rule_id, section, kind, text) tuples in document order."""

    return [
        rd.RuleAnchor(
            rule_id=rule_id,
            element_ids=[f"E-{rule_id}"],
            text=text,
            section_path=[section],
            rule_kind=kind,
            order=index,
        )
        for index, (rule_id, section, kind, text) in enumerate(rows)
    ]


def _role_edges(anchors, relationship_type):
    return [
        edge
        for edge in rd.discover_semantic_role_relationships(anchors)
        if edge.relationship_type is relationship_type
    ]


def test_an_exception_following_two_rules_is_only_a_candidate() -> None:
    """Two plausible targets in one section: "nearest" is a coin flip."""

    anchors = _role_anchors(
        ("R1", "4.1", "obligation", "Requests must be submitted in writing."),
        ("R2", "4.1", "obligation", "Requests must be acknowledged within five days."),
        ("R3", "4.1", "exception", "This does not apply during a declared shutdown."),
    )

    edges = _role_edges(anchors, PolicyRelationshipType.EXCEPTION_TO)

    assert len(edges) == 1
    edge = edges[0]
    assert edge.state == "candidate", "a positional guess must not be presented as a finding"
    assert "ambiguous_target" in edge.evidence.signals, (
        "the reviewer must be told the platform picked rather than knew"
    )
    assert edge.evidence.score < 0.5


def test_a_single_candidate_target_is_still_positional_and_still_a_candidate() -> None:
    """Even unambiguous nearest-preceding is layout, not semantics."""

    anchors = _role_anchors(
        ("R1", "4.1", "obligation", "Requests must be submitted in writing."),
        ("R2", "4.1", "exception", "This does not apply during a declared shutdown."),
    )

    edges = _role_edges(anchors, PolicyRelationshipType.EXCEPTION_TO)

    assert len(edges) == 1
    assert edges[0].target_rule_id == "R1"
    assert edges[0].state == "candidate"
    assert "ambiguous_target" not in edges[0].evidence.signals


def test_an_approval_requirement_is_a_candidate_not_a_gate_claim() -> None:
    anchors = _role_anchors(
        ("R1", "6", "obligation", "Purchases must be recorded in the register."),
        ("R2", "6", "obligation", "Purchases must be reconciled monthly."),
        ("R3", "6", "approval_requirement", "Prior written approval is required."),
    )

    edges = _role_edges(anchors, PolicyRelationshipType.APPROVAL_FOR)

    assert edges and all(edge.state == "candidate" for edge in edges)


def test_an_exception_does_not_reach_across_a_section_boundary() -> None:
    """Proximity across sections is not even a candidate."""

    anchors = _role_anchors(
        ("R1", "4.1", "obligation", "Requests must be submitted in writing."),
        ("R2", "9.2", "exception", "This does not apply during a declared shutdown."),
    )

    assert _role_edges(anchors, PolicyRelationshipType.EXCEPTION_TO) == []


def test_a_definition_linked_by_its_own_term_is_confirmed() -> None:
    """The contrast case: the text establishes the target, not the layout."""

    anchors = _role_anchors(
        ("R1", "2", "definition", '"Continuous service" means uninterrupted employment.'),
        ("R2", "2", "obligation", "Continuous service is counted from the start date."),
    )

    edges = _role_edges(anchors, PolicyRelationshipType.DEFINITION_USED_BY)
    confirmed = [edge for edge in edges if edge.state == "confirmed"]

    assert confirmed, "a term that actually occurs in the other rule is evidence, not proximity"
    assert all("shared_term" in edge.evidence.signals for edge in confirmed)


def test_no_role_edge_is_ever_persisted_as_a_same_decision_claim() -> None:
    """Layout must not become the strongest claim the graph can make."""

    anchors = _role_anchors(
        ("R1", "4.1", "obligation", "Requests must be submitted in writing."),
        ("R2", "4.1", "exception", "This does not apply during a declared shutdown."),
        ("R3", "4.1", "approval_requirement", "Prior written approval is required."),
    )

    for edge in rd.discover_semantic_role_relationships(anchors):
        if edge.state != "confirmed":
            continue
        assert edge.relationship_type is not PolicyRelationshipType.SAME_DECISION
        assert edge.relationship_type is not PolicyRelationshipType.PRECEDES
        assert "nearest_preceding" not in edge.evidence.signals
