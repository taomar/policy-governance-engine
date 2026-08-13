"""The bridge from drafted rules to relationship discovery.

`_relationship_anchors` is the only place the platform's own rule shape is
translated into the neutral `RuleAnchor` the detectors compare. A field read
from the wrong place there does not raise: it produces an empty anchor field,
the corresponding detector quietly never fires, and discovery reports success
while contributing nothing. That happened — `section_path` was first read from
`rule.scope`, which is the targeting scope and carries no document position, so
the hierarchy detector was dead while appearing to run.

These tests assert the anchors actually carry the source features, so the next
such mistake fails here rather than in a live extraction.
"""
from __future__ import annotations

from datetime import date

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
)
from policy_platform.contracts.policy import EvidenceReference, RuleFormulation, RuleType
from policy_platform.infrastructure.ai_extraction import _relationship_anchors
from policy_platform.infrastructure.correlation.relationship_discovery import (
    discover_structural_relationships,
)
from tests.fixtures.factories import make_rule


def _rule(
    rule_id: str,
    *,
    section: str,
    subsection: str = "",
    subject: str = "",
    predicate: str = "",
    source_text: str = "",
    rule_type: RuleType = RuleType.APPROVAL_REQUIREMENT,
):
    rule = make_rule(rule_id, AllCondition(all=[]), rule_type=rule_type)
    sections = [part for part in (section, subsection) if part]
    rule.evidence = [
        EvidenceReference(
            document_version_id="doc-1",
            source_hash="h" * 64,
            page=1,
            section=part,
            clause_id=f"clause-{rule_id}-{index}",
            start_offset=0,
            end_offset=10,
        )
        for index, part in enumerate(sections)
    ]
    rule.formulation = RuleFormulation(
        source_index=0,
        canonical=CanonicalPolicy(
            source_text=source_text or f"text for {rule_id}",
            rule=CanonicalPolicyRule(
                rule_type=CanonicalRuleType.OBLIGATION,
                subject=subject,
                predicate=predicate,
            ),
        ),
        dmn_decisions=[],
    )
    return rule


class TestRelationshipAnchors:
    def test_section_path_comes_from_evidence_not_targeting_scope(self):
        # The regression that made discovery a no-op. `rule.scope` has no
        # section at all, so reading it produced an empty path on every rule.
        rule = _rule("R1", section="3. Emergency Access")

        anchor = _relationship_anchors([rule])[0]

        assert anchor.section_path == ["3. Emergency Access"]

    def test_anchor_carries_the_features_detectors_compare(self):
        rule = _rule(
            "R1",
            section="2. Severity",
            subject="The security team",
            predicate="classify",
            source_text="The security team classifies incidents by severity.",
        )

        anchor = _relationship_anchors([rule])[0]

        assert anchor.rule_id == "R1"
        assert anchor.element_ids == ["clause-R1-0"]
        assert anchor.text == "The security team classifies incidents by severity."
        assert anchor.actor == "The security team"
        assert anchor.action == "classify"
        assert anchor.rule_kind == RuleType.APPROVAL_REQUIREMENT.value.lower()

    def test_order_follows_document_order(self):
        anchors = _relationship_anchors(
            [_rule("R1", section="1. One"), _rule("R2", section="2. Two")]
        )

        assert [a.rule_id for a in anchors] == ["R1", "R2"]
        assert [a.order for a in anchors] == [0, 1]

    def test_rule_without_formulation_still_yields_an_anchor(self):
        # A rule that failed to compile still belongs to its section. Dropping
        # it here is how a rule loses every relationship precisely when the
        # reviewer most needs them.
        rule = make_rule("R1", AllCondition(all=[]))
        rule.evidence = [
            EvidenceReference(
                document_version_id="doc-1",
                source_hash="h" * 64,
                page=1,
                section="4. Recordkeeping",
                clause_id="clause-R1",
                start_offset=0,
                end_offset=10,
            )
        ]
        rule.formulation = None

        anchor = _relationship_anchors([rule])[0]

        assert anchor.section_path == ["4. Recordkeeping"]
        assert anchor.actor == ""

    def test_anchors_produce_confirmed_edges_end_to_end(self):
        # The property that actually matters: anchors built from real rule
        # shape make the detectors fire. Asserting only on anchor fields would
        # not have caught the original bug's consequence.
        #
        # Uses a nested path, which is what the hierarchy detector keys on: a
        # subsection's rule is linked to the lead rule of its parent section.
        # Merely sharing one flat section is deliberately not enough — a
        # retention rule and an audit rule printed under one heading are not
        # one decision.
        rules = [
            _rule("R1", section="2. Severity"),
            _rule("R2", section="2. Severity", subsection="2.1 Escalation"),
        ]

        edges = discover_structural_relationships(_relationship_anchors(rules))
        confirmed = [edge for edge in edges if edge.state == "confirmed"]

        assert confirmed, (
            "a subsection rule produced no confirmed edge to its parent section — "
            "the anchors are not carrying document structure"
        )
        assert {(edge.source_rule_id, edge.target_rule_id) for edge in confirmed} == {
            ("R1", "R2")
        }

    def test_rules_sharing_only_a_flat_section_are_not_linked(self):
        # Guards the boundary above: two rules under the same heading, neither
        # nested under the other, state no relationship the document made.
        rules = [
            _rule("R1", section="2. Severity"),
            _rule("R2", section="2. Severity"),
        ]

        edges = discover_structural_relationships(_relationship_anchors(rules))

        assert [e for e in edges if e.state == "confirmed"] == []

    def test_rules_in_different_sections_are_not_linked_structurally(self):
        rules = [
            _rule("R1", section="2. Severity", subsection="2.1 Escalation"),
            _rule("R2", section="7. Exception Approval", subsection="7.1 Requests"),
        ]

        edges = discover_structural_relationships(_relationship_anchors(rules))

        assert [e for e in edges if e.state == "confirmed"] == []
