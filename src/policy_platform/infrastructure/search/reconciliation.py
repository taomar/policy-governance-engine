"""Reconcile what the search index holds against what the store actually has.

The index is written from `indexing.py` and keyed by
`{document_version_id}_{clause_id}`. Re-extracting a document version replaces
its clause rows with new ones carrying new identifiers, so every key written by
the previous run stops pointing at anything. Nothing in the write path removed
them, so they stayed searchable and a query could return text that no longer
exists in the store.

Reconciling rather than deleting-on-delete is deliberate:

* Entries orphaned by earlier runs already exist. A hook on the delete of the
  owning row would only ever tidy up future deletions and could not repair
  them; a sweep repairs an orphan whatever produced it, including a crash
  between committing the store and updating the index.
* The index write is best-effort by design and lives outside the database
  transaction. Deleting index entries from inside a repository would put a
  network call in a unit of work that can still roll back, which can remove
  entries for rows that continue to exist.

The invariant is per document version, matching how the index is written and
how `scripts/reextract_document.py` has always scoped its own clean-up: for one
document version, the entries under it are exactly the clauses the store holds
for that version.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from policy_platform.infrastructure.search.indexing import clause_search_document_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexReconciliation:
    """What the sweep looked at and what it removed.

    `examined` is reported so a run that read nothing cannot be mistaken for a
    run that found nothing to do.
    """

    examined: int
    live: int
    removed: tuple[str, ...]

    @property
    def removed_count(self) -> int:
        return len(self.removed)


def orphaned_keys(examined: Iterable[str], live: Iterable[str]) -> tuple[str, ...]:
    """Keys present in the index that the store no longer accounts for.

    Pure so the rule can be exercised without a search service.
    """

    live_keys = set(live)
    return tuple(sorted(key for key in examined if key not in live_keys))


def live_keys_for_version(document_version_id: str, clause_ids: Iterable[str]) -> tuple[str, ...]:
    """The keys the store's clauses entitle this version to have in the index."""

    return tuple(
        clause_search_document_id(document_version_id, str(clause_id))
        for clause_id in clause_ids
    )


async def reconcile_version_index(
    search_client,
    index: str,
    *,
    document_version_id: str,
    clause_ids: Iterable[str],
) -> IndexReconciliation:
    """Remove index entries under `document_version_id` with no clause behind them.

    Returns what was examined and removed. Raises nothing of its own: callers in
    the upload path treat search as best-effort, and this is theirs to swallow.
    """

    live = live_keys_for_version(document_version_id, clause_ids)
    examined = await search_client.find_ids_by_filter(
        index, filter_expr=f"document_version eq '{document_version_id}'"
    )
    orphans = orphaned_keys(examined, live)
    if orphans:
        await search_client.delete_documents(index, list(orphans))
    return IndexReconciliation(examined=len(examined), live=len(live), removed=orphans)
