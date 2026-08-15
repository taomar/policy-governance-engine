"""Rebuild a canonical document from the clauses already persisted for it.

This existed before this module did — it lived as a private helper on the
extraction router, and it is the seam that lets any later stage recover the
document's *structure* without re-parsing the source. It has been moved here,
rather than copied, so there is exactly one rebuild in the system.

Moved because of direction, not taste. Infrastructure may read ``domain`` and
``contracts``; it may not reach up into ``api``. A stage that needed this had
only two honest choices — move the one implementation down to a layer both
callers may see, or write a second one. A second one would drift from the first
the moment either changed, and the two would disagree about what the document
is while both claiming to describe it.
"""

from __future__ import annotations

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.domain.models import Clause

#: The fragment fields a persisted clause is allowed to contribute.
#:
#: Named rather than passed through: ``source_fragments`` is stored as free JSON,
#: so a writer that added a key would otherwise hand it straight to a constructor
#: that has never heard of it.
_FRAGMENT_FIELDS = {"page", "start_offset", "end_offset", "text"}


def canonical_from_clauses(document_id: str, clauses: list[Clause]) -> CanonicalDocument:
    """Rebuild a canonical document from the persisted clauses.

    Rebuilt rather than re-converted. Re-running Docling would take minutes and,
    worse, could produce a *different* artifact from the one whose offsets are
    already stored — so every span a reviewer is looking at would silently stop
    referring to what produced it.
    """

    elements: list[CanonicalElement] = []
    pages: dict[int, list[str]] = {}

    for index, clause in enumerate(clauses):
        fragments = [
            SourceFragment(
                **{k: v for k, v in fragment.items() if k in _FRAGMENT_FIELDS}
            )
            for fragment in (clause.source_fragments or [])
        ]
        elements.append(
            CanonicalElement(
                element_id=clause.element_id or f"E{index:06d}",
                element_type=clause.element_type or "paragraph",  # type: ignore[arg-type]
                logical_order=clause.sequence,
                text=clause.text,
                section=clause.section,
                source_fragments=fragments,
                # Restored, so a rebuilt document still knows which grid a row
                # belongs to and what that grid's columns are called. Passed
                # through untouched, and deliberately not guarded: `None` means
                # the converter found no row stating column labels, and mapping
                # anything else onto `None` here would make a corrupt value
                # indistinguishable from that fact. A value this projection did
                # not write fails validation loudly instead.
                #
                # Row identity only. `table_cell` is deliberately not set,
                # because no cell coordinate is stored to set it from — see
                # `structural_graph._add_table_edges`, which needs one.
                table_id=clause.table_id,
                table_headers=clause.table_headers,
            )
        )
        for fragment in fragments:
            pages.setdefault(fragment.page, [])

    return CanonicalDocument(
        document_id=document_id,
        page_count=len(pages) or 1,
        pages=[CanonicalPage(page=page, raw_text="") for page in sorted(pages)]
        or [CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="persisted",
    )
