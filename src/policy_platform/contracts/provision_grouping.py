"""Group a document's elements into the provisions its own structure states.

A *provision* is one passage of a document together with everything the passage
introduces: a heading and the material beneath it, down to the next heading at
the same or a shallower level. It is what the interface calls a **policy**, and
what a reviewer means by "this paragraph". The word `policy` is deliberately not
used for the stored entity: `policy_sets` already means *a project*, and a second
meaning for the same word in a sibling table is precisely the confusion this
repository has already paid for once.

This module exists because the grouping was already being computed and thrown
away. `ai_extraction._provisions` built the structural graph, asked it for each
element's chain of governing headings, used the chain to decide where a *batch*
should break, and discarded it. Batching is a resource decision; which rules a
reviewer sees as one policy is a product decision; they were the same
computation serving only the first.

Two groupings, deliberately kept apart
--------------------------------------

`raw_groups` is what batching uses and is unchanged from what it always used:
contiguous runs keyed by the chain of governing heading **element ids**. Nothing
about batching moves in this module, because changing where a batch breaks would
change what the model reads together and therefore what it extracts.

`group_into_provisions` is what persistence and review use. It takes the raw
groups and merges repeats of the same heading **text chain** when they are
adjacent. A table continuing across seven pages repeats its heading seven times
with nothing but its own rows in between; two unrelated sections that happen to
share a title have other sections' content between them. Adjacency is the signal
that separates them, and it is a fact about the document rather than a guess.

Measured on the two stored documents: one repeats
``Table of Violations and Penalties`` on seven consecutive heading elements
(each preceded by the same heading in Arabic), and merging them takes that
document from 44 policies to 38 without merging anything else. The other
document has no repeated heading text at all and is unaffected.

What this module may never do
-----------------------------

It may not compose text. A provision carries the heading texts its document
wrote, verbatim, and nothing else — no summary, no title of its own, no
statement synthesised from its members. That is why `Provision` has no prose
field beyond the copied heading path: a field that does not exist cannot later
be filled with a sentence the document never wrote.

It may not key on any particular document, heading, numbering style or language.
Everything here is derived from the structural graph, which is itself a pure
restatement of layout.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from policy_platform.contracts.canonical_document import CanonicalDocument
from policy_platform.contracts.structural_graph import StructuralGraph

#: Separates heading components inside the key's pre-image. A unit separator
#: rather than a printable character, so a heading containing the delimiter
#: cannot forge a different chain.
_COMPONENT_SEPARATOR = "\x1f"

#: Element types that introduce material rather than being material. A group
#: containing only these carries no content of its own, which is what lets a
#: repeated heading sit between two halves of the same table without counting
#: as an intervening section.
_INTRODUCING_TYPES = frozenset({"title", "heading"})

#: Length of the hexadecimal key. Half a SHA-256, matching the truncation the
#: element identity scheme already uses: long enough that collision is not a
#: practical concern for a single document, short enough to read in a log line.
_KEY_LENGTH = 32


def normalise_heading(text: str) -> str:
    """Fold a heading to the form two repeats of it must share.

    Deliberately minimal: Unicode compatibility normalisation, case folding and
    whitespace collapse. Nothing else.

    The temptation is to strip numbering so that "7.2. WORK PERMIT" and
    "WORK PERMIT" recognise each other. That would be a guess, and a wrong one —
    "7.1" and "7.2" are different sections whose remaining words are routinely
    identical ("Purpose", "Scope"), and folding the number away would merge
    them. This function's only job is to survive the incidental differences a
    repeat picks up (a non-breaking space, a case change from a style sheet),
    not to decide that two differently-written headings mean the same thing.
    """

    folded = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(folded.split())


def provision_key_for(
    source_release: str, heading_texts: Sequence[str], occurrence: int = 0
) -> str:
    """The stable identity of one provision.

    Derived from the source release, the normalised heading chain and, when a
    document states the same chain twice without merging them, which of those
    statements this is.

    Scoped by `source_release` because element ids are **not** unique across
    documents — both documents stored here begin at ``E000001``. The read-time
    grouping this replaces got away with an unscoped key because it never
    outlived a single request; a persisted one would collide the moment a second
    document was stored.

    `occurrence` is an ordinal, which the element identity scheme abandoned for
    good reasons. It is safe here only because it is scoped to one immutable
    source release: within a release nothing can be inserted, so nothing can
    shift. It is also almost always zero — it is non-zero only for a chain the
    document states twice in non-adjacent places, which occurs zero times across
    both stored documents.
    """

    pre_image = _COMPONENT_SEPARATOR.join(
        [
            source_release,
            *(normalise_heading(text) for text in heading_texts),
            f"#{occurrence}",
        ]
    )
    return hashlib.sha256(pre_image.encode("utf-8")).hexdigest()[:_KEY_LENGTH]


@dataclass(frozen=True)
class RawGroup:
    """One contiguous run of elements sharing a chain of governing headings.

    The unit batching has always used. Keyed by heading *element ids*, so two
    identically-titled sections are never confused, which is the property a
    batch boundary needs.
    """

    heading_element_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    #: Whether the run contains anything other than the headings introducing it.
    #: A heading immediately followed by another heading produces a run that
    #: states nothing on its own.
    carries_content: bool


@dataclass
class Provision:
    """One passage of a document, with every element stated under it.

    Holds no prose of its own. `heading_path` is copied verbatim from the
    document; everything else a reader sees comes from the rules extracted from
    `element_ids`.
    """

    provision_key: str
    #: The governing headings, outermost first, exactly as the document wrote
    #: them. Never normalised for display — normalisation exists for the key.
    heading_path: tuple[str, ...]
    #: The same chain as element ids, kept so a reviewer can be shown which
    #: heading occurrence a policy was built from, and so the adjacency merge is
    #: auditable after the fact rather than only reproducible.
    heading_element_ids: tuple[str, ...]
    element_ids: tuple[str, ...] = field(default_factory=tuple)
    #: Position of the earliest element, used to order policies the way the
    #: document reads. Not part of identity.
    first_logical_order: int = 0
    first_page: int | None = None
    last_page: int | None = None
    #: How many raw runs were merged into this one. 1 is the ordinary case; a
    #: continued table reports the number of pages its heading repeats on.
    merged_run_count: int = 1


def raw_groups(document: CanonicalDocument, graph: StructuralGraph) -> list[RawGroup]:
    """Contiguous runs keyed by the chain of governing heading element ids.

    A heading is keyed to *itself* rather than to its parent, so it groups with
    the material it introduces instead of with the section above it. Without
    that, every heading would be the last element of the preceding run — which
    is exactly the cut this grouping exists to prevent, applied to the one
    element whose whole purpose is to say what comes next.

    Runs are contiguous by construction here, and measured to be exhaustive: a
    key never reappears after a different one has intervened on either stored
    document, so grouping never reorders an element.
    """

    ordered = sorted(document.elements, key=lambda element: element.logical_order)
    groups: list[list[str]] = []
    keys: list[tuple[str, ...]] = []
    content: list[bool] = []
    previous: tuple[str, ...] | None = None

    for element in ordered:
        path = tuple(graph.heading_path(element.element_id))
        key = (
            (*path, element.element_id)
            if element.element_type in _INTRODUCING_TYPES
            else path
        )
        if not groups or key != previous:
            groups.append([])
            keys.append(key)
            content.append(False)
        groups[-1].append(element.element_id)
        if element.element_type not in _INTRODUCING_TYPES:
            content[-1] = True
        previous = key

    return [
        RawGroup(
            heading_element_ids=key,
            element_ids=tuple(members),
            carries_content=carries,
        )
        for key, members, carries in zip(keys, groups, content)
    ]


def group_into_provisions(
    document: CanonicalDocument,
    graph: StructuralGraph,
    *,
    source_release: str,
) -> list[Provision]:
    """Every element of `document`, partitioned into the provisions it states.

    A total partition: every element lands in exactly one provision, in document
    order. Provisions that carry no content of their own (a heading immediately
    followed by another heading, which is what a bilingual document produces)
    are still returned, because dropping them would leave elements belonging to
    nothing and make the partition unassertable. They simply never acquire rules
    and so never become a policy a reviewer sees.

    Repeats of the same heading text chain are merged when adjacent — when no
    *content-carrying* group with a different chain lies between them.

    Adjacency is computed from the document and never from what extraction
    produced. If it were computed from the rules, a re-run that formulated one
    fewer rule could change the grouping, and running twice would stop giving
    the same policies.
    """

    runs = raw_groups(document, graph)
    text_of = {node_id: node.text for node_id, node in graph.nodes.items()}
    page_of = {node_id: node.page for node_id, node in graph.nodes.items()}
    order_of = {
        element.element_id: element.logical_order for element in document.elements
    }

    merged: list[Provision] = []
    #: The normalised chain of the most recent content-carrying group, and where
    #: its provision sits in `merged`. A group merges only with this one.
    open_chain: tuple[str, ...] | None = None
    open_index: int | None = None
    seen_chains: dict[tuple[str, ...], int] = {}

    for run in runs:
        heading_texts = tuple(text_of.get(eid, "") for eid in run.heading_element_ids)
        chain = tuple(normalise_heading(text) for text in heading_texts)

        if run.carries_content and open_chain == chain and open_index is not None:
            target = merged[open_index]
            target.element_ids = (*target.element_ids, *run.element_ids)
            target.merged_run_count += 1
            _extend_pages(target, run.element_ids, page_of)
            continue

        occurrence = seen_chains.get(chain, 0)
        seen_chains[chain] = occurrence + 1
        provision = Provision(
            provision_key=provision_key_for(source_release, heading_texts, occurrence),
            heading_path=heading_texts,
            heading_element_ids=run.heading_element_ids,
            element_ids=run.element_ids,
            first_logical_order=min(
                (order_of[eid] for eid in run.element_ids if eid in order_of),
                default=0,
            ),
        )
        _extend_pages(provision, run.element_ids, page_of)
        merged.append(provision)

        if run.carries_content:
            open_chain = chain
            open_index = len(merged) - 1

    _assert_partition(document, merged)
    return merged


def _extend_pages(
    provision: Provision, element_ids: Sequence[str], page_of: dict[str, int | None]
) -> None:
    pages = [page_of[eid] for eid in element_ids if page_of.get(eid) is not None]
    if not pages:
        return
    low, high = min(pages), max(pages)  # type: ignore[type-var]
    provision.first_page = low if provision.first_page is None else min(provision.first_page, low)
    provision.last_page = high if provision.last_page is None else max(provision.last_page, high)


def _assert_partition(document: CanonicalDocument, provisions: Sequence[Provision]) -> None:
    """Every element in exactly one provision, or the grouping is not one.

    Asserted rather than trusted because both failure modes are silent: a
    dropped element removes a rule's passage from the review queue, and a
    duplicated one shows a reviewer the same obligation under two headings.
    """

    placed = [eid for provision in provisions for eid in provision.element_ids]
    expected = {element.element_id for element in document.elements}
    assert len(placed) == len(expected), "provision grouping lost or duplicated an element"
    assert set(placed) == expected, "provision grouping placed an element not in the document"
