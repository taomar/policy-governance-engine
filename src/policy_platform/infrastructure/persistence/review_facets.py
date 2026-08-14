"""What the review queue needs to offer filters, built in one round-trip.

Lifted out of `api/routers/candidate_rules.py`, where it was 133 lines of
aggregation and two hand-written joins inside a request handler. A router's job
is to turn HTTP into a call and a result into a response; deciding what a facet
is and how a removed rule is recognised is not that, and it could not be
exercised without going through FastAPI.

The 404 stays in the router. Resolving a policy set that does not exist is an
HTTP concern, and this function takes the resolved set rather than the key so
it never has to raise one.

This is containment, not a fix. Seventeen `session.execute` calls remain across
six files under `api/`, so business logic in routers is a pattern here rather
than an oversight in one place. This was the largest single instance and it now
sits behind a boundary -- it also took this router from three direct queries to
none. The rest are recorded in `docs/known-limitations.md` rather than quietly
left to look intentional.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    CandidateRule,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)


async def build_review_facets(session: AsyncSession, policy_set: PolicySet) -> dict:
    """Documents, runs, delta and status totals, and rules no longer found.

    Returned together because they are always needed together: four separate
    calls would only make the filter bar render in stages.
    """

    rows = (
        await session.execute(
            select(
                CandidateRule.extraction_run_id,
                CandidateRule.delta_status,
                CandidateRule.review_status,
                func.count(),
            )
            .where(
                CandidateRule.policy_set_id == policy_set.id,
                CandidateRule.superseded_at.is_(None),
            )
            .group_by(
                CandidateRule.extraction_run_id,
                CandidateRule.delta_status,
                CandidateRule.review_status,
            )
        )
    ).all()

    run_ids = {r[0] for r in rows}
    runs_meta = (
        (
            await session.execute(
                select(ExtractionRun, DocumentVersion, SourceDocument)
                .join(DocumentVersion, DocumentVersion.id == ExtractionRun.document_version_id)
                .join(SourceDocument, SourceDocument.id == DocumentVersion.document_id)
                .where(ExtractionRun.id.in_(run_ids))
            )
        ).all()
        if run_ids
        else []
    )

    documents: dict[str, dict] = {}
    runs: dict[str, dict] = {}
    for run, version, document in runs_meta:
        documents.setdefault(
            str(document.id),
            {"id": str(document.id), "title": document.title, "rule_count": 0},
        )
        runs[str(run.id)] = {
            "id": str(run.id),
            "reference": run.reference,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "document_id": str(document.id),
            "document_title": document.title,
            "document_version_id": str(version.id),
            "version_label": f"v{version.version_number}",
            "content_hash": version.content_hash[:12] if version.content_hash else None,
            "total": 0,
            "pending": 0,
            "delta": {"new": 0, "changed": 0, "unchanged": 0, "baseline": 0},
        }

    delta_totals = {"new": 0, "changed": 0, "unchanged": 0, "baseline": 0, "unclassified": 0}
    status_totals: dict[str, int] = {}
    for run_id, delta_status, review_status, count in rows:
        bucket = delta_status if delta_status in delta_totals else "unclassified"
        delta_totals[bucket] += count
        status_totals[review_status] = status_totals.get(review_status, 0) + count
        entry = runs.get(str(run_id))
        if entry is None:
            continue
        entry["total"] += count
        if review_status == "candidate":
            entry["pending"] += count
        if delta_status in entry["delta"]:
            entry["delta"][delta_status] += count
        documents[entry["document_id"]]["rule_count"] += count

    # A rule is "no longer found" when a later run retired it and nothing in
    # that later run claimed it as a continuation.
    #
    # "Later run" has to mean the run that produced what the reader is looking
    # at, not merely some run that came after. A set extracted four times holds
    # four generations of retired rules, and the earlier three were retired by
    # runs that have since been retired themselves -- they answer "what did run
    # two drop", which is a question about history, not about the current state.
    # Returning all of them put rules from three generations into one panel and
    # is what a reviewer sees as old runs mixing together.
    #
    # A retiring run is the current one exactly when it still has rules of its
    # own standing in this set. That is derived rather than assumed, so it stays
    # correct for a set holding several documents: each document's latest run
    # has current rules, so each document contributes its own last generation
    # and no document contributes two.
    current_runs = select(CandidateRule.extraction_run_id).where(
        CandidateRule.policy_set_id == policy_set.id,
        CandidateRule.superseded_at.is_(None),
    )
    # Scoped to this set. A continuation is claimed by a rule in the same set;
    # an unscoped subquery let any other set's baseline reference suppress a row
    # here, which hid removals rather than showing stale ones -- the quieter
    # direction of the same mistake, and wrong for the same reason.
    claimed = select(CandidateRule.baseline_candidate_id).where(
        CandidateRule.policy_set_id == policy_set.id,
        CandidateRule.baseline_candidate_id.is_not(None),
    )
    removed_rows = (
        await session.execute(
            select(CandidateRule, ExtractionRun)
            .join(ExtractionRun, ExtractionRun.id == CandidateRule.superseded_by_run_id)
            .where(
                CandidateRule.policy_set_id == policy_set.id,
                CandidateRule.superseded_at.is_not(None),
                CandidateRule.superseded_by_run_id.in_(current_runs),
                CandidateRule.id.not_in(claimed),
            )
            .order_by(CandidateRule.superseded_at.desc())
            .limit(200)
        )
    ).all()

    removed = [
        {
            "id": str(row.id),
            "title": (row.payload_json or {}).get("title") or "(untitled rule)",
            "rule_type": row.rule_type,
            "review_status": row.review_status,
            "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None,
            "superseded_by_run_id": str(row.superseded_by_run_id) if row.superseded_by_run_id else None,
            "superseded_by_reference": superseding_run.reference,
            "source_text": ((row.payload_json or {}).get("formulation") or {}).get("source_text", ""),
        }
        for row, superseding_run in removed_rows
    ]

    return {
        "documents": sorted(documents.values(), key=lambda d: d["title"]),
        "runs": sorted(runs.values(), key=lambda r: r["started_at"] or "", reverse=True),
        "delta_totals": delta_totals,
        "status_totals": status_totals,
        "removed": removed,
    }
