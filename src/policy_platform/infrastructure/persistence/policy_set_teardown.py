"""Deleting a policy set, and everything that would otherwise outlive it.

The owner is told projects are disposable and to create and drop them freely,
but the product had no way to drop one: the only `DELETE` under `/policy-sets`
was for an aggregate limit, so teardown meant hand-written SQL against the
database. This closes that.

Why the work is here and not in the router
------------------------------------------
Same reason as `review_facets.py`: a router turns HTTP into a call and a result
into a response. Deciding what belongs to a policy set, and in what order it can
be removed, is neither -- and it could not be exercised without going through
FastAPI.

Three kinds of thing hang off a policy set, and they fail differently
--------------------------------------------------------------------
1. **Twenty-one tables reachable by foreign key.** Every one of them is
   `ON DELETE NO ACTION` -- there is not a single `CASCADE` in the schema. That
   is the *safe* failure: Postgres refuses the delete rather than orphaning the
   children. It is also why this module exists, because the caller has to do the
   ordering itself.

2. **`notes`, which reference their subject polymorphically** (`entity_type` +
   `entity_id`, no foreign key). Nothing blocks, nothing cascades. A note on a
   deleted rule simply becomes unreachable commentary keyed to an id that no
   longer resolves. These are removed with the project.

3. **The Azure AI Search index, which is not in the database at all.** This is
   the one that orphans permanently, and it is worth being explicit about why.
   `indexing.py` reconciles the index *when it writes* -- its own docstring says
   the sweep lives there "and not on the delete of the owning row". That is a
   sound choice for a re-extracted document, which gets rewritten and therefore
   swept. A deleted project is never rewritten, so no future write will ever
   sweep it: its clause entries would stay searchable forever, pointing at a
   document that no longer exists. So the keys are collected *before* the rows
   go, while the clauses can still be read.

What is deliberately kept
-------------------------
`audit_events` are not deleted. This codebase already holds the line that a
rejection is "evidence, not a deletion", and the same applies with more force to
a whole project: erasing the record that it ever existed is the opposite of what
a governance trail is kept for. `record_audit_event` folds `policy_set_key` into
the stored details precisely so an event stays readable when the entity it hangs
off is gone, so the surviving trail says which project was deleted by name and
not merely as a dangling id. A deletion event is appended rather than the
history being removed.

Order
-----
`_DELETION_ORDER` is written out rather than derived, because the *predicate*
for each table -- how it reaches a policy set -- is semantic and cannot be
inferred from the schema. The *order*, however, can be, so it is checked against
SQLAlchemy's own topological sort by a test rather than trusted. Adding a table
or a foreign key without updating this list fails that test instead of failing
in production against a half-deleted project.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import PolicySet
from policy_platform.infrastructure.search.indexing import clause_search_document_id

logger = logging.getLogger(__name__)

POLICY_SET_DELETED = "policy_set.deleted"

#: (table, DELETE statement) in an order where every child precedes its parent.
#:
#: Depth from `policy_sets` is NOT a valid order and using it would break:
#: `candidate_rules` is one hop from a policy set but also references
#: `extraction_runs`, which is three hops away, so deleting by descending depth
#: removes the runs first and violates the constraint.
_DELETION_ORDER: tuple[tuple[str, str], ...] = (
    # Notes first: they point at candidate rules by id with no foreign key, so
    # once the rules are gone there is nothing left to identify them by.
    #
    # CAST(:sid AS text) rather than `:sid::text`: SQLAlchemy's text() binder
    # does not bind a parameter immediately followed by a `::` cast, and leaves
    # the literal `:sid` in the statement for Postgres to choke on. The other
    # two binds in this same statement substitute correctly, so the failure is
    # per-occurrence and would not show up in review.
    (
        "notes",
        """DELETE FROM notes WHERE entity_id IN (
               SELECT id::text FROM candidate_rules WHERE policy_set_id = :sid
               UNION ALL SELECT id::text FROM source_documents WHERE policy_set_id = :sid
               UNION ALL SELECT CAST(:sid AS text)
           )""",
    ),
    (
        "rule_exceptions",
        """DELETE FROM rule_exceptions WHERE rule_id IN (
               SELECT ar.id FROM approved_rules ar
               JOIN approved_policy_versions v ON ar.policy_version_id = v.id
               WHERE v.policy_set_id = :sid)""",
    ),
    # Three ways in, not one: an evidence reference points at an approved rule,
    # and independently at the document version and clause it was drawn from.
    # Scoping on the rule alone would leave rows whose rule is null but whose
    # clause belongs to this project -- and those would then block the clause
    # delete further down rather than orphaning, so the symptom would be a
    # half-finished teardown.
    (
        "evidence_references",
        """DELETE FROM evidence_references
           WHERE rule_id IN (
               SELECT ar.id FROM approved_rules ar
               JOIN approved_policy_versions v ON ar.policy_version_id = v.id
               WHERE v.policy_set_id = :sid)
              OR document_version_id IN (
               SELECT dv.id FROM document_versions dv
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)
              OR clause_id IN (
               SELECT c.id FROM clauses c
               JOIN document_versions dv ON dv.id = c.document_version_id
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)""",
    ),
    (
        "policy_test_runs",
        """DELETE FROM policy_test_runs WHERE policy_test_id IN (
               SELECT id FROM policy_tests WHERE policy_set_id = :sid)
           OR policy_version_id IN (
               SELECT id FROM approved_policy_versions WHERE policy_set_id = :sid)""",
    ),
    (
        "approved_aggregate_limits",
        """DELETE FROM approved_aggregate_limits WHERE policy_version_id IN (
               SELECT id FROM approved_policy_versions WHERE policy_set_id = :sid)""",
    ),
    (
        "approved_rules",
        """DELETE FROM approved_rules WHERE policy_version_id IN (
               SELECT id FROM approved_policy_versions WHERE policy_set_id = :sid)""",
    ),
    ("policy_tests", "DELETE FROM policy_tests WHERE policy_set_id = :sid"),
    ("policy_test_batches", "DELETE FROM policy_test_batches WHERE policy_set_id = :sid"),
    # Before extraction_runs: candidate_rules.extraction_run_id is NOT NULL.
    ("candidate_rules", "DELETE FROM candidate_rules WHERE policy_set_id = :sid"),
    # After candidate_rules and before document_versions. The foreign key from
    # candidate_rules is ON DELETE SET NULL, so a provision deleted first would
    # not block -- it would quietly unlink rules that are about to be deleted
    # anyway, and the ordering error would leave no trace. Placed by the
    # constraint that actually binds instead: document_versions is its parent.
    (
        "document_provisions",
        """DELETE FROM document_provisions WHERE policy_set_id = :sid
           OR document_version_id IN (
               SELECT dv.id FROM document_versions dv
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)""",
    ),
    (
        "extraction_stages",
        """DELETE FROM extraction_stages WHERE document_version_id IN (
               SELECT dv.id FROM document_versions dv
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)
           OR extraction_run_id IN (
               SELECT er.id FROM extraction_runs er
               JOIN document_versions dv ON dv.id = er.document_version_id
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)""",
    ),
    (
        "extraction_runs",
        """DELETE FROM extraction_runs WHERE document_version_id IN (
               SELECT dv.id FROM document_versions dv
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)""",
    ),
    (
        "clauses",
        """DELETE FROM clauses WHERE document_version_id IN (
               SELECT dv.id FROM document_versions dv
               JOIN source_documents d ON d.id = dv.document_id
               WHERE d.policy_set_id = :sid)""",
    ),
    (
        "document_versions",
        """DELETE FROM document_versions WHERE document_id IN (
               SELECT id FROM source_documents WHERE policy_set_id = :sid)""",
    ),
    ("source_documents", "DELETE FROM source_documents WHERE policy_set_id = :sid"),
    ("correlation_findings", "DELETE FROM correlation_findings WHERE policy_set_id = :sid"),
    ("correlation_runs", "DELETE FROM correlation_runs WHERE policy_set_id = :sid"),
    ("evaluations", "DELETE FROM evaluations WHERE policy_set_id = :sid"),
    ("quality_runs", "DELETE FROM quality_runs WHERE policy_set_id = :sid"),
    ("policy_exceptions", "DELETE FROM policy_exceptions WHERE policy_set_id = :sid"),
    ("policy_attestations", "DELETE FROM policy_attestations WHERE policy_set_id = :sid"),
    ("policy_aggregate_limits", "DELETE FROM policy_aggregate_limits WHERE policy_set_id = :sid"),
    ("approved_policy_versions", "DELETE FROM approved_policy_versions WHERE policy_set_id = :sid"),
)

#: Tables reachable from `policy_sets` that this module intentionally leaves
#: alone, with the reason. Asserted by test, so a new exemption has to be argued
#: for here rather than achieved by forgetting.
RETAINED_TABLES: dict[str, str] = {
    "audit_events": "governance evidence; a deletion is appended, not erased",
}


@dataclass
class DeletionOutcome:
    """What was removed, per table, plus what could not be reached."""

    policy_set_key: str
    policy_set_name: str
    rows_deleted: dict[str, int] = field(default_factory=dict)
    search_documents_identified: int = 0
    search_documents_deleted: int | None = None
    search_index_error: str | None = None

    @property
    def total_rows(self) -> int:
        return sum(self.rows_deleted.values())

    @property
    def search_index_state(self) -> str:
        """`clean`, `skipped`, or `orphaned` -- never a bare number.

        A caller has to be able to tell "there was nothing to remove" from "we
        could not remove it", because the second leaves entries pointing at a
        project that no longer exists and someone has to know that happened.
        """

        if self.search_index_error is not None:
            return "orphaned"
        if self.search_documents_deleted is None:
            return "skipped"
        return "clean"


async def collect_search_document_ids(session: AsyncSession, policy_set_id: uuid.UUID) -> list[str]:
    """Search keys for every clause under this policy set.

    Must run before the rows are deleted. Uses `clause_search_document_id` --
    the same function the writer uses -- rather than re-forming the key here,
    so a delete cannot miss entries because two places disagree about the
    format.
    """

    rows = (
        await session.execute(
            text(
                """SELECT c.id AS clause_id, c.document_version_id AS version_id
                   FROM clauses c
                   JOIN document_versions dv ON dv.id = c.document_version_id
                   JOIN source_documents d ON d.id = dv.document_id
                   WHERE d.policy_set_id = :sid"""
            ),
            {"sid": policy_set_id},
        )
    ).mappings().all()
    return [clause_search_document_id(str(r["version_id"]), str(r["clause_id"])) for r in rows]


async def delete_policy_set(
    session: AsyncSession, policy_set: PolicySet, *, actor: str
) -> tuple[DeletionOutcome, list[str]]:
    """Remove a policy set and everything scoped to it, in one transaction.

    Returns the outcome and the search keys the caller still has to remove.
    Search cleanup is deliberately *not* done here: it is a network call to
    another service, and holding a transaction open across it would mean a slow
    or unavailable Search resource could block the database. The caller runs it
    after the commit and records the result on the outcome.
    """

    outcome = DeletionOutcome(policy_set_key=policy_set.key, policy_set_name=policy_set.name)
    search_ids = await collect_search_document_ids(session, policy_set.id)
    outcome.search_documents_identified = len(search_ids)

    for table, statement in _DELETION_ORDER:
        result = await session.execute(text(statement), {"sid": policy_set.id})
        if result.rowcount:
            outcome.rows_deleted[table] = result.rowcount

    # Appended before the set row goes, inside the same transaction: if the
    # delete fails, the claim that it happened must fail with it.
    from policy_platform.infrastructure.persistence.audit import record_audit_event

    record_audit_event(
        session,
        event_type=POLICY_SET_DELETED,
        entity_type="policy_set",
        entity_id=policy_set.id,
        actor=actor,
        policy_set_key=policy_set.key,
        details={
            "policy_set_name": policy_set.name,
            "rows_deleted": dict(outcome.rows_deleted),
            "total_rows_deleted": outcome.total_rows,
            "search_documents_identified": outcome.search_documents_identified,
        },
    )

    await session.execute(text("DELETE FROM policy_sets WHERE id = :sid"), {"sid": policy_set.id})
    return outcome, search_ids
