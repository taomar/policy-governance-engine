"""Relationship discovery: typed links between rules, independent of executability.

The defect this closes is the fourth confirmed root cause. Relationships used to
be derived from ``_group_labels``, which linked two rules only when one DMN
decision table already named both. When the projection was ``ambiguous`` or
``enrichment_required`` — precisely when a reviewer most needs to see what a rule
depends on — no shared decision existed, so the rule was reported as unrelated to
everything. The document said otherwise: it was a row of a table, an exception to
a general condition, or the sentence a cross-reference pointed at.

Discovery here runs on *source structure and text*, before and regardless of any
executable projection, and produces typed edges from
``contracts.relationships``.

Signals
-------
Every detector here reports what the document itself establishes:

1. **Structural** — same table, section hierarchy, list membership, adjacency in
   an ordered procedure. The document's own layout.
2. **Enumeration** — a governing stem and the clauses that complete it.
3. **Semantic role** — the neutral normative role the formulator already
   assigned (``exception``, ``approval``, ``definition``).

Nothing here filters the element set; it only adds edges. A detector that could
*remove* material would be able to lose policy silently, which is the failure
this module exists to prevent.

Similarity-based discovery was removed once it was found to be unreachable:
nothing ever constructed an embedding provider, so the branch had never run in
production. Restoring it is a deliberate decision, not a wiring fix — it changes
the edges attached to already-reviewed rules.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from policy_platform.contracts.relationships import (
    PolicyRelationship,
    PolicyRelationshipGraph,
    PolicyRelationshipType,
    RelationshipEvidence,
)
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
)
from policy_platform.infrastructure.ingestion import source_structure

logger = logging.getLogger(__name__)

#: Bumped when discovery changes in a way that alters the edges produced for an
#: unchanged document. Persisted with the run as `clustering_version`.
DISCOVERY_VERSION = "relationship-discovery-v1"


@dataclass
class RuleAnchor:
    """One rule, described by the source features discovery can compare.

    Assembled by the caller from a drafted rule plus the elements it was
    formulated from. Deliberately a plain dataclass rather than a contract: it
    is an internal working shape, and pinning it as a wire contract would invite
    callers to persist it instead of the relationship graph.
    """

    rule_id: str
    element_ids: list[str] = field(default_factory=list)
    unit_id: str = ""
    cluster_id: str = ""
    text: str = ""
    section_path: list[str] = field(default_factory=list)
    table_id: str | None = None
    table_row_index: int | None = None
    references: list[str] = field(default_factory=list)
    #: Fact paths the rule's DMN projection named, when it had one. A shared
    #: fact path is strong evidence two rules answer one question.
    fact_paths: list[str] = field(default_factory=list)
    #: Canonical subject/actor and predicate, when the formulation supplied
    #: them. Neutral slots: the module never inspects their values for meaning.
    actor: str = ""
    action: str = ""
    #: Canonical rule type as the formulator classified it, lower-cased.
    rule_kind: str = ""
    #: Document order of the rule's first element, for ordered-procedure links.
    order: int = 0
    #: Outline number as a comparable path — ``3.2.1`` becomes ``(3, 2, 1)`` —
    #: so parent/child is a prefix test. Empty when the clause carries no
    #: number, which is most unstructured prose.
    outline_path: tuple[int, ...] = ()
    #: The clause promises material it does not itself contain ("…in one of the
    #: following cases only:"). Independent of numbering, so it still fires on
    #: documents that number nothing.
    promises_enumeration: bool = False
    #: The canonical decomposition as a neutral name→value mapping. Carried
    #: whole rather than as named slots because the family test below compares
    #: the *set* of fields two records disagree on, and naming them here would
    #: mean adding a slot every time the formulator gains a qualifier.
    canonical_fields: dict[str, str] = field(default_factory=dict)
    #: Operative wording this record points at but does not itself contain,
    #: already quoted from the record. Empty for a record that stands alone.
    unresolved_phrases: list[str] = field(default_factory=list)


def discover_enumeration_relationships(anchors: list[RuleAnchor]) -> list[PolicyRelationship]:
    """Link governing stems to the clauses that complete them.

    A stem and its cases are one policy split across clauses. Left unlinked, the
    stem becomes a rule asserting an exhaustive limit with nothing to limit it
    to — "salary shall be increased in one of the following cases only:" with no
    cases — and each case becomes a rule that cannot say what it is a case of.
    Both read as complete, which is what makes the omission dangerous rather
    than merely untidy.

    Two independent signals, because documents supply one or the other and
    rarely both:

    * **Outline numbering.** ``3.2.1`` is a child of ``3.2``. Exact, and needs
      no interpretation.
    * **An unsatisfied promise.** A clause ending "…the following:" is
      incomplete by its own words, so the clauses that follow it at the same
      level complete it. This holds where no numbering exists at all.

    Both produce ``confirmed`` edges: each is a relation a reader of the source
    can point at, which is the standard the ontology sets. Neither infers from
    topic or wording similarity.
    """

    edges: list[PolicyRelationship] = []
    ordered = sorted(anchors, key=lambda item: item.order)

    # Outline numbering, but only where the parent is a *governing stem*.
    #
    # Numbering alone proves containment, not shared decision. "3.2 Leave" with
    # "3.2.1 Annual leave" and "3.2.2 Sick leave" beneath it is a heading over
    # two separate policies: linking them as `same_decision` would assert they
    # must be evaluated together to answer one question, which is false and
    # would drag an unrelated rule into every review of its neighbour.
    #
    # A parent that *promises* an enumeration is different in kind. "…in one of
    # the following cases only:" is incomplete by its own words, so its children
    # are not neighbours under a label — they are the rest of its sentence.
    #
    # Where the parent is substantive but makes no promise, the answer is not
    # deterministic and this module says nothing. Those go to the model tier,
    # which can weigh whether a sub-clause continues its parent or merely sits
    # beneath it, and must quote the source either way. Containment itself is
    # already recorded as `parent_heading` in the structural graph, so nothing
    # is lost by declining here.
    by_path: dict[tuple[int, ...], RuleAnchor] = {}
    for anchor in ordered:
        if anchor.outline_path and anchor.outline_path not in by_path:
            by_path[anchor.outline_path] = anchor
    for anchor in ordered:
        path = anchor.outline_path
        if len(path) < 2:
            continue
        parent = by_path.get(path[:-1])
        if parent is None or parent.rule_id == anchor.rule_id:
            continue
        if not parent.promises_enumeration:
            continue
        edges.append(
            _edge(
                PolicyRelationshipType.SAME_DECISION,
                parent,
                anchor,
                signals=["outline_hierarchy", "unsatisfied_promise"],
                score=0.95,
                origin="structural",
                state="confirmed",
                detail=(
                    f"{'.'.join(str(p) for p in path)} completes "
                    f"{'.'.join(str(p) for p in path[:-1])}, which promises cases it does not contain"
                ),
            )
        )

    # An unsatisfied promise, bounded by numbering. The clauses following a stem
    # complete it — but only where the outline says where that run ends.
    #
    # Deliberately NOT applied to unnumbered stems. A promise with no numbering
    # has no deterministic extent: the next clause might be its final case or an
    # unrelated rule, and the text alone does not say. Running to the end of the
    # section attaches whatever came next, which on a real document linked a
    # travel-expenses rule to a salary clause. Those stems are reported by
    # `stems_needing_adjudication` and handed to the model tier, which can weigh
    # subject matter and must quote the source for what it proposes.
    linked = {(e.source_rule_id, e.target_rule_id) for e in edges}
    for index, anchor in enumerate(ordered):
        if not anchor.promises_enumeration or not anchor.outline_path:
            continue
        for candidate in ordered[index + 1 :]:
            if candidate.promises_enumeration:
                break
            if not candidate.outline_path:
                break
            if len(candidate.outline_path) <= len(anchor.outline_path):
                break
            if (anchor.rule_id, candidate.rule_id) in linked:
                continue
            if anchor.rule_id == candidate.rule_id:
                continue
            edges.append(
                _edge(
                    PolicyRelationshipType.SAME_DECISION,
                    anchor,
                    candidate,
                    signals=["unsatisfied_promise"],
                    score=0.8,
                    origin="structural",
                    state="confirmed",
                    detail="the clause promises material it does not itself contain",
                )
            )
            linked.add((anchor.rule_id, candidate.rule_id))

    return edges


def stems_needing_adjudication(
    anchors: list[RuleAnchor], edges: list[PolicyRelationship]
) -> list[RuleAnchor]:
    """Governing stems this module could not resolve, for the model tier.

    A stem with outline numbering bounds its own run and is handled above. A
    stem without it promises material whose extent the text does not state, and
    guessing that extent is how unrelated rules get merged. Those are handed on
    rather than approximated.
    """

    satisfied = {edge.source_rule_id for edge in edges}
    return [
        a
        for a in anchors
        if a.promises_enumeration and not a.outline_path and a.rule_id not in satisfied
    ]


def unsatisfied_promises(
    anchors: list[RuleAnchor], edges: list[PolicyRelationship]
) -> list[RuleAnchor]:
    """Stems that promised material and were linked to none.

    The format-independent completeness check. Whatever numbering a document
    uses — or none — a clause stating "in one of the following cases only:" with
    nothing attached is *provably* an incomplete extraction, not a judgement
    call. Reported so the run can say a rule is unfinished rather than shipping
    a permission whose limits went missing.
    """

    satisfied = {edge.source_rule_id for edge in edges}
    return [a for a in anchors if a.promises_enumeration and a.rule_id not in satisfied]


def _edge(
    relationship_type: PolicyRelationshipType,
    source: RuleAnchor,
    target: RuleAnchor,
    *,
    signals: list[str],
    score: float,
    origin: str,
    state: str = "candidate",
    detail: str = "",
    quote: str = "",
) -> PolicyRelationship:
    return PolicyRelationship(
        relationship_type=relationship_type,
        source_rule_id=source.rule_id,
        target_rule_id=target.rule_id,
        source_element_id=source.element_ids[0] if source.element_ids else "",
        target_element_id=target.element_ids[0] if target.element_ids else "",
        cluster_id=source.cluster_id if source.cluster_id == target.cluster_id else "",
        evidence=RelationshipEvidence(
            signals=signals, score=round(score, 4), detail=detail, source_quote=quote
        ),
        origin=origin,
        state=state,
    )


def discover_split_decision_relationships(
    anchors: list[RuleAnchor],
) -> list[PolicyRelationship]:
    """Link records that were cut out of one statement of one obligation.

    `same_decision` is exactly what these are: several records that have to be
    read together before anyone can say what the obligation requires. Left
    unlinked, each one reads as the whole rule, and a consumer answering "may
    this employee do X" gets whichever fragment it happened to retrieve.

    `confirmed`, not proposed. The claim is that two records quote the same
    sentence verbatim and decompose it to the same subject, predicate, modality
    and rule type — every part of which a reader can check against the source
    without interpreting anything. What the records *disagree* on is never
    inspected for meaning, so no judgment about the document enters here.

    Nothing is merged and nothing is superseded. The edge says these belong
    together; what belongs in one record is a decision for a reviewer holding
    the sentence.
    """

    members = [
        FamilyMember(rule_id=anchor.rule_id, sentence=anchor.text, core=anchor.canonical_fields)
        for anchor in anchors
        if anchor.canonical_fields
    ]
    by_id = {anchor.rule_id: anchor for anchor in anchors}

    edges: list[PolicyRelationship] = []
    for family in decision_families(members):
        ordered = sorted(
            (by_id[rule_id] for rule_id in family.rule_ids if rule_id in by_id),
            key=lambda item: item.order,
        )
        if len(ordered) < 2:
            continue
        # The earliest fragment stands in for the decision, the same way a
        # table's first row stands in for the table: linking every pair would
        # grow with the square of the family and say nothing extra.
        head = ordered[0]
        for member in ordered[1:]:
            edges.append(
                _edge(
                    PolicyRelationshipType.SAME_DECISION,
                    member,
                    head,
                    signals=["same_sentence", "same_obligation"],
                    score=1.0,
                    origin="structural",
                    state="confirmed",
                    detail=(
                        "cut from one statement of one obligation, differing in "
                        + ", ".join(family.varying)
                    ),
                    quote=family.sentence[:300],
                )
            )
    return edges


def discover_referent_relationships(anchors: list[RuleAnchor]) -> list[PolicyRelationship]:
    """Propose the neighbour that supplies wording a record points at.

    A record saying "on that day" without saying which day was cut away from
    the sentence that named it. The remedy is never to write the missing words
    into the record — the record's text is the document's text — so the link is
    the repair: a reviewer opening both can decide the rule honestly.

    `candidate`, deliberately. Which neighbour supplies the referent is not
    something the document states; the nearest preceding record is where an
    antecedent normally lives, and normally is not always. Recording that as
    established would put a positional guess into the field consumers read as
    fact, so it is offered for adjudication instead.
    """

    ordered = sorted(anchors, key=lambda item: item.order)
    edges: list[PolicyRelationship] = []
    for position, anchor in enumerate(ordered):
        if not anchor.unresolved_phrases or position == 0:
            continue
        supplier = ordered[position - 1]
        if supplier.rule_id == anchor.rule_id:
            continue
        edges.append(
            _edge(
                PolicyRelationshipType.SAME_DECISION,
                anchor,
                supplier,
                signals=["unresolved_referent"],
                score=0.5,
                origin="candidate",
                state="candidate",
                detail=(
                    "points at wording it does not contain ("
                    + "; ".join(anchor.unresolved_phrases)
                    + "); this is the record immediately before it"
                ),
                quote=anchor.text[:300],
            )
        )
    return edges


#: Ordinal/step markers that make an ordered procedure explicit. `precedes` is
#: only asserted between elements that carry them: two consecutive paragraphs in
#: a section are adjacent on the page, which says nothing about execution order,
#: and recording that as an ordering claim would put layout into the policy
#: record.
_ORDINAL_RE = re.compile(
    r"^\s*(?:"
    r"step\s+\d+"
    r"|\(?\d+[.)]"
    r"|\(?[ivx]+[.)]"
    r"|(?:first|second|third|fourth|fifth|then|next|finally)\b"
    r")",
    re.IGNORECASE,
)


def _is_ordered_step(anchor: RuleAnchor) -> bool:
    return bool(_ORDINAL_RE.match(anchor.text or ""))


def discover_structural_relationships(anchors: list[RuleAnchor]) -> list[PolicyRelationship]:
    """Edges provable from document structure alone.

    Runs first and unconditionally. These edges never depend on a model call, a
    successful DMN projection, or an embedding deployment being configured,
    which is what guarantees a non-executable rule still carries its table, its
    section hierarchy and its ordering.
    """

    edges: list[PolicyRelationship] = []
    by_table: dict[str, list[RuleAnchor]] = {}
    for anchor in anchors:
        if anchor.table_id:
            by_table.setdefault(anchor.table_id, []).append(anchor)

    # Rows of one table belong to that table. The anchor is the lowest-ordered
    # row, which stands in for the table itself: a table that produced rules has
    # no rule of its own, so without a designated anchor every row would be
    # related to every other row and the graph would say nothing.
    for table_id, rows in by_table.items():
        ordered = sorted(rows, key=lambda item: (item.table_row_index or 0, item.order))
        anchor_row = ordered[0]
        for row in ordered[1:]:
            edges.append(
                _edge(
                    PolicyRelationshipType.TABLE_ROW_OF,
                    row,
                    anchor_row,
                    signals=["same_table"],
                    score=1.0,
                    origin="structural",
                    state="confirmed",
                    detail=f"rows of table {table_id}",
                )
            )

    # Rules formulated in the same window. This is *layout* proximity: the
    # window is a size-bounded region of the document, so two rules sharing one
    # says only that they were printed near each other. A retention rule and an
    # audit rule in the same window are not one decision, so this is proposed
    # for review rather than recorded as a finding.
    by_cluster: dict[str, list[RuleAnchor]] = {}
    for anchor in anchors:
        key = anchor.cluster_id or anchor.unit_id
        if key:
            by_cluster.setdefault(key, []).append(anchor)
    for key, members in by_cluster.items():
        ordered = sorted(members, key=lambda item: item.order)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                edges.append(
                    _edge(
                        PolicyRelationshipType.SAME_DECISION,
                        left,
                        right,
                        signals=["same_window"],
                        score=0.35,
                        origin="candidate",
                        state="candidate",
                        detail=f"co-located in window {key}",
                    )
                )

    # Ordered procedure steps. `precedes` requires *procedural* evidence on both
    # ends — an ordinal or step marker the document itself wrote — plus the same
    # section. Adjacency alone is a fact about the page: two consecutive
    # paragraphs of prose are not a sequence, and asserting that they are puts
    # layout into the policy record.
    by_section: dict[str, list[RuleAnchor]] = {}
    for anchor in anchors:
        by_section.setdefault(source_structure.section_key(anchor.section_path), []).append(anchor)
    for section, members in by_section.items():
        if not section:
            continue
        ordered = sorted(members, key=lambda item: item.order)
        for left, right in zip(ordered, ordered[1:]):
            if left.table_id or right.table_id:
                continue
            if not (_is_ordered_step(left) and _is_ordered_step(right)):
                continue
            edges.append(
                _edge(
                    PolicyRelationshipType.PRECEDES,
                    left,
                    right,
                    signals=["ordinal_marker", "sequence_adjacent", "shared_section"],
                    score=0.85,
                    origin="structural",
                    state="confirmed",
                    detail=f"consecutive numbered steps within {section}",
                )
            )

    # Section hierarchy. A rule in a subsection is qualified by the governing
    # rule that opens its parent section — "a device may be replaced when it can
    # no longer support the work" in §4 governs the diagnosis and warranty
    # clauses in §4.1. This is the relationship half of the same defect
    # overlapping windows fix on the extraction side: without it, a subsection's
    # rules are reported as unrelated to the general rule they qualify, purely
    # because a window boundary fell between them.
    #
    # Only the *lead* rule of each immediate ancestor section is linked, and only
    # from rules that are not themselves in that ancestor section. Linking every
    # descendant to every ancestor rule would relate a whole chapter to itself
    # and say nothing.
    lead_by_section = {
        section: min(members, key=lambda item: item.order)
        for section, members in by_section.items()
        if section
    }
    for anchor in anchors:
        if len(anchor.section_path) < 2:
            continue
        parent_key = source_structure.section_key(anchor.section_path[:-1])
        lead = lead_by_section.get(parent_key)
        if lead is None or lead.rule_id == anchor.rule_id:
            continue
        edges.append(
            _edge(
                PolicyRelationshipType.SAME_DECISION,
                lead,
                anchor,
                signals=["section_hierarchy"],
                score=0.75,
                origin="structural",
                state="confirmed",
                detail=f"{parent_key} governs {source_structure.section_key(anchor.section_path)}",
            )
        )
    return edges


def discover_semantic_role_relationships(anchors: list[RuleAnchor]) -> list[PolicyRelationship]:
    """Edges implied by neutral normative roles the formulator already assigned.

    Uses only the closed canonical vocabulary (``exception``, ``approval``,
    ``definition``) that ``contracts.formulation.CanonicalRuleType`` and the
    platform's own ``RuleType`` already define. It never inspects *values* — an
    approval rule about expense limits and one about device replacement are
    indistinguishable here, which is exactly the property that keeps this
    domain neutral.

    Two very different confidences are produced, and the distinction is the
    point:

    * **positional** — an exception or approval attached to the nearest
      preceding rule in its section. Position is a fact about the page, not
      about which rule the exception carves out of: with two candidate rules
      above it, "nearest" is a coin flip. These are ``candidate`` edges, and
      when the choice is genuinely ambiguous the evidence says so.
    * **term-based** — a definition linked to the rules that actually contain
      its defined term. The target is established by the text itself, not by
      layout, so these are ``confirmed``.
    """

    edges: list[PolicyRelationship] = []
    ordered = sorted(anchors, key=lambda item: item.order)

    for index, anchor in enumerate(ordered):
        kind = (anchor.rule_kind or "").casefold()
        if kind not in {"exception", "approval_requirement", "definition"}:
            continue
        # Candidate governing rules are the ones preceding it *in its own
        # section* that are not themselves exceptions or approvals.
        preceding = [
            candidate
            for candidate in reversed(ordered[:index])
            if source_structure.section_key(candidate.section_path)
            == source_structure.section_key(anchor.section_path)
            and (candidate.rule_kind or "").casefold()
            not in {"exception", "approval_requirement"}
        ]
        if not preceding:
            continue

        governing = preceding[0]
        relationship = {
            "exception": PolicyRelationshipType.EXCEPTION_TO,
            "approval_requirement": PolicyRelationshipType.APPROVAL_FOR,
            "definition": PolicyRelationshipType.DEFINITION_USED_BY,
        }[kind]
        ambiguous = len(preceding) > 1
        edges.append(
            _edge(
                relationship,
                anchor,
                governing,
                signals=(
                    ["nearest_preceding", "shared_section", "ambiguous_target"]
                    if ambiguous
                    else ["nearest_preceding", "shared_section"]
                ),
                # Lower still when more than one rule could plausibly be the
                # target: a reviewer needs to see that the platform picked, not
                # that it knew.
                score=0.35 if ambiguous else 0.5,
                origin="candidate",
                state="candidate",
                detail=(
                    f"{kind} attached to the nearest preceding rule in its section; "
                    + (
                        f"{len(preceding)} rules in this section could be the target"
                        if ambiguous
                        else "one candidate target in this section"
                    )
                ),
            )
        )

    # A definition's term used elsewhere links to every rule that uses it. The
    # target is established by the defined term occurring in that rule's text —
    # a property of the words, not of where they sit — so this is confirmed.
    for anchor in ordered:
        if (anchor.rule_kind or "").casefold() != "definition":
            continue
        terms = source_structure.salient_terms(anchor.text, limit=4)
        if not terms:
            continue
        for other in ordered:
            if other.rule_id == anchor.rule_id:
                continue
            lowered = other.text.casefold()
            hit = next((term for term in terms if term and term in lowered), "")
            if not hit:
                continue
            edges.append(
                _edge(
                    PolicyRelationshipType.DEFINITION_USED_BY,
                    anchor,
                    other,
                    signals=["shared_term"],
                    score=0.65,
                    origin="structural",
                    state="confirmed",
                    detail=hit,
                    quote=hit,
                )
            )
    return edges
