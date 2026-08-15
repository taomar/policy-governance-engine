"""Prove idempotence against the real database, by digesting the whole table.

Reports a hash over every column of every row of `document_provisions`, plus
the per-rule linkage. Run it, run `backfill_provisions.py --commit` again, run
it again: the two digests must be identical.

"Nothing was added" is not the assertion. A pass that removed one row and
created another would also report nothing added. The digest changes if any
value of any row changes, including a timestamp -- so a no-op UPDATE that
touched `updated_at` and nothing else would still be caught.

`tests/unit/test_provisions_are_idempotent.py` makes the same assertion over
constructed documents. This script makes it over the rows that actually exist,
which is the only place a migration or a backfill can go wrong.

Read-only. It issues no INSERT, UPDATE or DELETE.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text  # noqa: E402

from policy_platform.infrastructure.persistence.db import get_engine  # noqa: E402

# `select *`, not a column list. A column list is a claim about the table made
# somewhere other than the table, and it goes stale silently: a column added
# later would sit outside the digest, and could then change without changing
# the hash. The point of this script is that nothing escapes it.
PROVISIONS = "select * from document_provisions order by id"

LINKS = "select id, provision_id from candidate_rules order by id"


def digest(rows) -> str:
    payload = json.dumps(
        [[str(value) for value in row] for row in rows], sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


async def main() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        provisions = (await connection.execute(text(PROVISIONS))).fetchall()
        links = (await connection.execute(text(LINKS))).fetchall()
    await engine.dispose()

    linked = sum(1 for _, provision_id in links if provision_id is not None)
    print(f"document_provisions rows : {len(provisions)}")
    print(f"columns digested         : {len(provisions[0]) if provisions else 0}")
    print(f"candidate_rules rows     : {len(links)}")
    print(f"  of which linked        : {linked}")
    print(f"WHOLE-TABLE DIGEST       : {digest(provisions)}")
    print(f"LINKAGE DIGEST           : {digest(links)}")


asyncio.run(main())
