"""Typed relationships between policy rules, independent of executability.

The defect this closes: relationships used to be a *side effect* of a successful
DMN projection. ``formulation_mapping._group_labels`` linked two canonical rules
only when one decision table already named both of them, and the cross-batch
linker then joined rules that already shared that derived label. So the moment a
rule was ``ambiguous`` or ``enrichment_required`` — exactly when a reviewer most
needs to see what else the rule depends on — it had no relationships at all.

Relationships are a property of the *source document*, not of whether the
platform managed to compile the rule. A table row belongs to its table whether
or not the row is executable. An exception qualifies its rule whether or not
either has an approved fact mapping. This module models that directly.

The vocabulary is domain neutral and closed. It names structural and normative
relations that exist in statutes, HR handbooks, IT standards, procurement
manuals, control frameworks and operating procedures alike. It contains no
HR-specific, device-specific or finance-specific link types; a project that
wants "supersedes for the purposes of the collective agreement" maps its own
label onto :class:`PolicyRelationshipType.SUPERSEDES` in project configuration.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PolicyRelationshipType(str, Enum):
    """The closed relationship ontology.

    Each member names a relation a reader of the source could point at, not an
    inference about topic similarity:

    * ``SAME_DECISION`` — these rules must be evaluated together to answer one
      question. The general condition and its qualifying sub-clauses.
    * ``TABLE_ROW_OF`` — this rule was formulated from a row of that table. The
      target is the table's header/anchor rule.
    * ``DEFINITION_USED_BY`` — a defined term's rule, pointing at the rules that
      use the term.
    * ``EXCEPTION_TO`` — this rule carves out a case from that rule.
    * ``APPROVAL_FOR`` — this rule states who must approve the outcome of that
      rule.
    * ``OVERRIDES`` — this rule takes precedence over that rule where both
      apply, without replacing it.
    * ``SUPERSEDES`` — this rule replaces that rule outright.
    * ``PRECEDES`` — ordered process steps: this step comes before that step.
    * ``CROSS_REFERENCES`` — the source text explicitly points at the other
      provision without either of the stronger semantics above.
    """

    SAME_DECISION = "same_decision"
    TABLE_ROW_OF = "table_row_of"
    DEFINITION_USED_BY = "definition_used_by"
    EXCEPTION_TO = "exception_to"
    APPROVAL_FOR = "approval_for"
    OVERRIDES = "overrides"
    SUPERSEDES = "supersedes"
    PRECEDES = "precedes"
    CROSS_REFERENCES = "cross_references"


#: Relationship types whose meaning does not depend on direction. Persisted
#: edges are still directed (source -> target); this set tells consumers that
#: reversing the edge would not change the claim, which is what lets the
#: reconciliation pass deduplicate ``A same_decision B`` against
#: ``B same_decision A`` without losing information.
SYMMETRIC_RELATIONSHIPS = frozenset(
    {PolicyRelationshipType.SAME_DECISION, PolicyRelationshipType.CROSS_REFERENCES}
)


class RelationshipEvidence(BaseModel):
    """Why the platform believes a relationship exists.

    ``signals`` names the mechanical detectors that fired (``"same_table"``,
    ``"explicit_reference"``, ``"shared_section"``, ``"embedding_similarity"``,
    ``"shared_term"``, ``"shared_fact"``, ``"shared_actor"``,
    ``"sequence_adjacent"``, ``"model_adjudicated"``). Recorded rather than
    collapsed into a score because a relationship supported only by embedding
    similarity is a materially weaker claim than one supported by an explicit
    cross-reference in the text, and a reviewer must be able to tell them apart.
    """

    model_config = ConfigDict(extra="ignore")

    signals: list[str] = Field(default_factory=list)
    #: 0..1. Deliberately not a probability — it is a monotone ranking aid used
    #: to order candidates for review, nothing more.
    score: float = 0.0
    #: The exact source text fragment that justifies the link, when one exists
    #: (an explicit cross-reference). Never model-authored prose.
    source_quote: str = ""
    detail: str = ""


class PolicyRelationship(BaseModel):
    """One directed, typed edge between two rules.

    ``source_rule_id``/``target_rule_id`` are platform rule ids. Element ids are
    carried alongside so an edge stays meaningful even when one endpoint failed
    to become a rule — a table row that yielded no canonical rule still belongs
    to its table, and losing that fact is how orphaned rows appear.
    """

    model_config = ConfigDict(extra="ignore")

    relationship_type: PolicyRelationshipType
    source_rule_id: str = ""
    target_rule_id: str = ""
    source_element_id: str = ""
    target_element_id: str = ""
    #: The decision cluster both endpoints were formulated in, when they shared
    #: one. Empty for edges discovered by the document-wide reconciliation pass.
    cluster_id: str = ""
    evidence: RelationshipEvidence = Field(default_factory=RelationshipEvidence)
    #: ``"structural"`` (derived deterministically from document structure),
    #: ``"reference"`` (the text says so), ``"candidate"`` (proposed by
    #: similarity and not yet adjudicated), ``"reconciliation"`` (found by the
    #: document-wide pass), ``"model"`` (asserted by the formulator).
    origin: str = "structural"
    #: Whether this edge is a *finding* or a *proposal*, and the distinction is
    #: the whole point of having it.
    #:
    #: ``confirmed`` means the document itself establishes the relation: rows of
    #: one table, an explicit cross-reference, a heading hierarchy, a normative
    #: role attached within one section. A consumer may act on it.
    #:
    #: ``candidate`` means something *suggested* it — layout adjacency, shared
    #: vocabulary, embedding similarity. Two paragraphs sitting next to each
    #: other is a fact about page layout, not about policy: a retention rule and
    #: an audit rule printed consecutively are not one decision, and recording
    #: that as ``same_decision`` would put a machine's guess into the record a
    #: reviewer trusts. Candidates are surfaced for review and excluded from the
    #: flat ``related_rule_ids`` view the rest of the platform reads.
    state: Literal["confirmed", "candidate"] = "candidate"

    def key(self) -> tuple[str, str, str]:
        """Identity used for deduplication.

        Symmetric types sort their endpoints so an edge and its mirror collapse
        to one entry; asymmetric types keep direction, because ``A overrides B``
        and ``B overrides A`` are contradictory claims that must both survive to
        be reported as a conflict.
        """

        left = self.source_rule_id or self.source_element_id
        right = self.target_rule_id or self.target_element_id
        if self.relationship_type in SYMMETRIC_RELATIONSHIPS and right < left:
            left, right = right, left
        return (self.relationship_type.value, left, right)


class PolicyRelationshipGraph(BaseModel):
    """Every relationship discovered for one extraction run.

    Persisted with the run rather than derived from the rules, for the same
    reason the context manifest is: it records what this run concluded, and a
    later run that reads the document differently must not silently rewrite
    history.
    """

    model_config = ConfigDict(extra="ignore")

    relationships: list[PolicyRelationship] = Field(default_factory=list)

    def add(self, relationship: PolicyRelationship) -> bool:
        """Add an edge unless an equivalent one is already present.

        Returns whether it was added, so callers can count discoveries. Keeps
        the *first* edge on a duplicate: earlier edges come from stronger,
        earlier-running detectors (structure and explicit references) than the
        later similarity passes.
        """

        existing = {edge.key() for edge in self.relationships}
        if relationship.key() in existing:
            return False
        self.relationships.append(relationship)
        return True

    def extend(self, relationships: list[PolicyRelationship]) -> int:
        return sum(1 for relationship in relationships if self.add(relationship))

    def for_rule(self, rule_id: str) -> list[PolicyRelationship]:
        return [
            edge
            for edge in self.relationships
            if edge.source_rule_id == rule_id or edge.target_rule_id == rule_id
        ]

    def related_rule_ids(self, rule_id: str, *, confirmed_only: bool = True) -> list[str]:
        """Rule ids connected to ``rule_id``, in insertion order.

        Confirmed edges only by default. This is the flat, untyped view the rest
        of the platform reads, and it must not carry proposals: a reviewer
        seeing "Related to: R-7" reasonably reads it as a statement about the
        policy, not as "these two paragraphs were adjacent". Candidates remain
        visible in the typed ``relationships`` list, where their ``state`` and
        ``evidence.signals`` are visible alongside them.
        """

        related: list[str] = []
        for edge in self.relationships:
            if confirmed_only and edge.state != "confirmed":
                continue
            other = ""
            if edge.source_rule_id == rule_id:
                other = edge.target_rule_id
            elif edge.target_rule_id == rule_id:
                other = edge.source_rule_id
            if other and other != rule_id and other not in related:
                related.append(other)
        return related

    def confirmed(self) -> list[PolicyRelationship]:
        return [edge for edge in self.relationships if edge.state == "confirmed"]

    def candidates(self) -> list[PolicyRelationship]:
        return [edge for edge in self.relationships if edge.state == "candidate"]

    def by_type(self, relationship_type: PolicyRelationshipType) -> list[PolicyRelationship]:
        return [edge for edge in self.relationships if edge.relationship_type is relationship_type]
