"""Link rules extracted before provisions existed to the provision that states them.

Operator-run and re-runnable. Calls exactly the functions the extraction
pipeline calls (`infrastructure.extraction.provision_linking`), so a document
extracted before this change and one extracted after are grouped by the same
code. A backfill that reimplemented the grouping could drift from it silently —
both halves would look internally consistent while disagreeing about which
policy a rule belongs to.

Writes only:

* rows into `document_provisions` that are not already there;
* `candidate_rules.provision_id` where it is NULL;
* `approved_rules.provision_key` / `provision_heading_json` where they are NULL.

It never deletes, never re-links a rule that already carries a provision, and
never touches rule payloads. Running it twice writes nothing the second time,
which is the same property the pipeline's own linking has and for the same
reason: the key is a function of the document.

Usage::

    python scripts/backfill_provisions.py            # report only, writes nothing
    python scripts/backfill_provisions.py --commit   # apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from policy_platform.domain.models import (  # noqa: E402
    ApprovedRule,
    CandidateRule,
    Clause,
    DocumentProvision,
    DocumentVersion,
)
from policy_platform.infrastructure.extraction.provision_linking import (  # noqa: E402
    provision_for,
    provision_index,
    provision_row,
)
from policy_platform.infrastructure.persistence.db import (  # noqa: E402
    get_engine,
    get_sessionmaker,
)


async def backfill(session: AsyncSession, *, commit: bool) -> dict[str, int]:
    """Link every unlinked rule of every stored document version.

    Scoped per document version because a provision key is scoped to a source
    release: element ids are not unique across documents, so a rule may only
    ever be matched against the index built from its own document.
    """

    counts = {"provisions": 0, "candidates": 0, "approved": 0, "unresolved": 0}
    versions = (await session.execute(select(DocumentVersion))).scalars().all()

    for version in versions:
        clauses = (
            await session.execute(
                select(Clause)
                .where(Clause.document_version_id == version.id)
                .order_by(Clause.sequence)
            )
        ).scalars().all()
        if not clauses:
            continue

        index = provision_index(
            clauses, str(version.id), version.content_hash or str(version.id)
        )
        if index is None:
            print(f"{version.id}: grouping unavailable, skipped")
            continue

        ref_by_clause_id = {str(clause.id): clause.clause_ref for clause in clauses}
        known_refs = set(ref_by_clause_id.values())
        cache: dict[str, DocumentProvision] = {}

        candidates = (
            await session.execute(
                select(CandidateRule).where(CandidateRule.provision_id.is_(None))
            )
        ).scalars().all()

        for candidate in candidates:
            payload = candidate.payload_json or {}
            source_elements = (payload.get("lineage") or {}).get("source_elements") or ""
            fallback = [
                ref
                for ref in (
                    ref_by_clause_id.get(str(entry.get("clause_id")))
                    for entry in (payload.get("evidence") or [])
                )
                if ref is not None
            ]
            # A rule belongs to this version only if the refs it cites are this
            # version's. Checked explicitly because clause_refs are not unique
            # across documents either, and a silent cross-document match would
            # file a rule under a heading from a document it never mentions.
            cited = [
                part.strip() for part in source_elements.split(";") if part.strip()
            ] or fallback
            if not cited or not set(cited) & known_refs:
                continue

            provision = provision_for(source_elements, fallback, index)
            if provision is None:
                counts["unresolved"] += 1
                continue

            before = len(cache)
            row = await provision_row(
                session,
                cache,
                provision,
                policy_set_id=candidate.policy_set_id,
                document_version_id=version.id,
            )
            if len(cache) > before and row.id is not None:
                counts["provisions"] += 1
            candidate.provision_id = row.id
            counts["candidates"] += 1

            approved = (
                await session.execute(
                    select(ApprovedRule).where(
                        ApprovedRule.rule_id == str(payload.get("rule_id") or ""),
                        ApprovedRule.provision_key.is_(None),
                    )
                )
            ).scalars().all()
            for record in approved:
                record.provision_key = provision.provision_key
                record.provision_heading_json = list(provision.heading_path)
                counts["approved"] += 1

    if commit:
        await session.commit()
    else:
        await session.rollback()
    return counts


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="apply the changes; without it the pass runs and rolls back",
    )
    args = parser.parse_args()

    engine = get_engine()
    factory = get_sessionmaker()
    async with factory() as session:
        counts = await backfill(session, commit=args.commit)
    await engine.dispose()

    verb = "linked" if args.commit else "would link"
    print(
        f"{verb}: {counts['candidates']} candidate rule(s), "
        f"{counts['approved']} approved rule(s), "
        f"{counts['provisions']} provision row(s) created, "
        f"{counts['unresolved']} rule(s) cited no passage this grouping knows"
    )
    if not args.commit:
        print("nothing was written; re-run with --commit to apply")


if __name__ == "__main__":
    asyncio.run(main())
