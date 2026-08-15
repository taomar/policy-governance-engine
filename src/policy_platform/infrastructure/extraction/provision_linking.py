"""Attach extracted rules to the provision of the document that states them.

Sits between `contracts.provision_grouping`, which decides what the provisions
of a document *are*, and the two callers that need rules filed under them:

* `ai_extraction.extract_candidate_rules`, which links each rule as it is
  written (step 13a of the running path);
* `scripts/backfill_provisions.py`, which links rules extracted before this
  existed.

One module rather than two implementations on purpose. If the backfill computed
the grouping its own way, a document extracted before the change and one
extracted after could disagree about which policy a rule belongs to, and the
disagreement would be invisible — both would look internally consistent. The
backfill is therefore a caller of the production path, not a parallel one.

Nothing here composes text, and nothing here deletes. Linking is idempotent by
construction: the provision key is a function of the document, so a second pass
over an unchanged document finds every row already present and writes none.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.provision_grouping import (
    Provision,
    group_into_provisions,
)
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.domain.models import Clause, DocumentProvision
from policy_platform.infrastructure.ingestion.canonical_rebuild import (
    canonical_from_clauses,
)

logger = logging.getLogger(__name__)


def provision_index(
    clauses: list[Clause], document_id: str, source_release: str
) -> dict[str, Provision] | None:
    """Which provision each clause belongs to, keyed by `clause_ref`.

    The grouping the *review queue* uses, as distinct from the one batching
    uses: repeats of a heading are merged here and never there. Computed once
    per run, before any model call, from the document alone — so it says the
    same thing whether the run that follows succeeds, fails or extracts nothing.

    Returns None on the same terms as `ai_extraction._provisions`: a document
    whose structure defeats grouping is still worth extracting, and its rules
    simply carry no provision and render exactly as they did before this
    existed. A grouping failure must not cost a reviewer their extraction.
    """

    try:
        document = canonical_from_clauses(document_id, clauses)
        graph = build_structural_graph(document)
        provisions = group_into_provisions(
            document, graph, source_release=source_release
        )
    except Exception:  # noqa: BLE001 - see docstring; degrade, never fail the run
        logger.warning(
            "provision index unavailable; rules will carry no policy", exc_info=True
        )
        return None

    order_of = {
        element.element_id: element.logical_order for element in document.elements
    }
    by_order = {clause.sequence: clause for clause in clauses}
    index: dict[str, Provision] = {}
    for provision in provisions:
        for element_id in provision.element_ids:
            clause = by_order.get(order_of.get(element_id, -1))
            if clause is not None:
                index[clause.clause_ref] = provision
    return index


def provision_for(
    source_elements: str,
    fallback_refs: list[str],
    index: dict[str, Provision] | None,
) -> Provision | None:
    """The provision a rule belongs to, via the passage it cites.

    Resolved from `lineage.source_elements` first, because that is the same
    attribution the element-anchored fallback reads. Deriving the persisted
    grouping from a different field than the fallback would let the two
    disagree about where a rule lives, and a reviewer would see a rule move
    when its provision link happened to be absent.

    Read through the rule's *own* attribution rather than its batch's, for the
    reason `source_elements` exists at all: a batch holds as many provisions as
    fit its character budget, so a rule taking the batch's first clause would be
    filed under a neighbouring rule's heading.

    When a rule cites clauses in more than one provision the earliest is taken.
    Measured across both stored documents this affects 5 rules of 692. The
    alternative — leaving such a rule unplaced — would mean the policy view
    silently omits a rule the document does state, and "nothing is lost" is the
    stronger obligation. Earliest is also what `policy_assembly.policy_key`
    already does, so the two groupings continue to agree.

    Returns None when the rule cites nothing this index knows, which is not an
    error: the rule keeps its row, carries no provision, and renders through the
    element-anchored fallback exactly as it did before this existed.
    """

    if index is None:
        return None

    refs = [part.strip() for part in (source_elements or "").split(";") if part.strip()]
    if not refs:
        refs = fallback_refs

    candidates = [index[ref] for ref in refs if ref in index]
    if not candidates:
        return None
    return min(candidates, key=lambda provision: provision.first_logical_order)


async def provision_row(
    session: AsyncSession,
    cache: dict[str, DocumentProvision],
    provision: Provision,
    *,
    policy_set_id,
    document_version_id,
) -> DocumentProvision:
    """Get or create the row for one provision. Never updates, never deletes.

    Get-or-create rather than insert-or-update because a provision is derived
    from the document and the document does not change within a version: if a
    row already exists for this key, it already says the right thing. Updating
    it would be a write with no possible effect, and a write with no possible
    effect is exactly what makes an idempotence assertion over the whole table
    fail on a timestamp.

    The unique constraint on `(document_version_id, provision_key)` is the real
    guard; the cache only avoids a round trip per rule within one pass.
    """

    cached = cache.get(provision.provision_key)
    if cached is not None:
        return cached

    existing = (
        await session.execute(
            select(DocumentProvision).where(
                DocumentProvision.document_version_id == document_version_id,
                DocumentProvision.provision_key == provision.provision_key,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = DocumentProvision(
            policy_set_id=policy_set_id,
            document_version_id=document_version_id,
            provision_key=provision.provision_key,
            heading_path_json=list(provision.heading_path),
            heading_element_ids_json=list(provision.heading_element_ids),
            first_page=provision.first_page,
            last_page=provision.last_page,
            first_sequence=provision.first_logical_order,
            merged_run_count=provision.merged_run_count,
        )
        session.add(existing)
        await session.flush()
    cache[provision.provision_key] = existing
    return existing
