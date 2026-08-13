"""An endpoint that cuts a list short has to say that it did.

Both of these endpoints used to return a bare JSON array while applying a
server-side limit. A caller receiving twenty rows had no way to tell twenty
runs from the newest twenty of two hundred, and neither client attempted to:
one rendered the array as the complete history, the other fed it straight into
a run picker. The clients were not careless -- the response carried nothing for
them to be careful with. The defect was in the contract.

The invariant is the same one `audit.py` and `evaluations.py` already satisfy,
and the same one the extraction viewer was fixed to honour: *a collection
presented as complete must be complete, or must be visibly marked partial*. A
response cannot be marked partial if its shape has nowhere to put the mark.

What is asserted here is the contract, not either implementation:

  * the response is an object carrying the collection alongside `count` and
    `truncated`, so a bare array fails regardless of what it contains;
  * `truncated` tracks reality in both directions -- a list that fits is not
    reported as cut short, which is what stops a constant `True` from passing;
  * `count` equals the rows actually delivered, so a client printing the count
    beside the list is not printing a number the list disagrees with;
  * `limit` has a floor, because `truncated` is derived from `count == limit`
    and that comparison stops being a truth claim at zero -- a request for no
    rows would otherwise come back "truncated" holding nothing.

Row counts are named constants and every expectation is computed from them, so
the test states a property rather than a remembered observation.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

# `api.app` builds an application at import time and `Settings` requires a
# database URL. Set before the import so collection does not depend on a
# developer's local .env -- the URL is never connected to, because the session
# dependency is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    CorrelationRun,
    PolicySet,
    QualityRun,
)
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


POLICY_SET_KEY = "capped-list-contract"

#: How many rows exist. Any number greater than ``WINDOW`` by more than one
#: works; the gap is what makes "some were withheld" distinguishable from "the
#: list happened to end".
SEEDED_ROWS = 5

#: The cap a caller asks for. Smaller than ``SEEDED_ROWS``, so a correct server
#: must withhold ``SEEDED_ROWS - WINDOW`` rows and admit it.
WINDOW = 2

#: A cap no server could reach with only ``SEEDED_ROWS`` rows stored. Used to
#: prove the truncation signal can be *off*, which a hardcoded `True` would
#: fail. Without this case the suite would accept a server that cries wolf on
#: every response -- an alarm that is always on carries no information.
ROOMY_WINDOW = SEEDED_ROWS + 1

assert WINDOW < SEEDED_ROWS < ROOMY_WINDOW, "the fixture must exercise both directions"


async def _seed_quality_runs(maker, policy_set_id: uuid.UUID, count: int) -> None:
    async with maker() as session:
        for index in range(count):
            session.add(
                QualityRun(
                    id=uuid.uuid4(),
                    policy_set_id=policy_set_id,
                    scope="published",
                    rule_count=index,
                    run_at=datetime(2024, 1, 1, tzinfo=timezone.utc).replace(
                        minute=index
                    ),
                )
            )
        await session.commit()


async def _seed_correlation_runs(maker, policy_set_id: uuid.UUID, count: int) -> None:
    async with maker() as session:
        for index in range(count):
            session.add(
                CorrelationRun(
                    id=uuid.uuid4(),
                    policy_set_id=policy_set_id,
                    status="completed",
                    rules_analyzed=index,
                    created_at=datetime(2024, 1, 1, tzinfo=timezone.utc).replace(
                        minute=index
                    ),
                )
            )
        await session.commit()


#: (url path under the policy set, key holding the collection, seeder).
#:
#: Parameterised rather than duplicated so the property is stated once. A third
#: capped list added to this router should be appended here, and any that cannot
#: be is a list that does not satisfy the contract.
CAPPED_LISTS = [
    pytest.param(
        "quality/history", "runs", _seed_quality_runs, id="quality-history"
    ),
    pytest.param(
        "correlate/runs", "runs", _seed_correlation_runs, id="correlation-runs"
    ),
]


@pytest.fixture
async def client():
    """A real app over in-memory SQLite with one empty policy set."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            PolicySet.__table__,
            QualityRun.__table__,
            CorrelationRun.__table__,
        ):
            await connection.run_sync(lambda c, t=table: t.create(c, checkfirst=True))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    policy_set_id = uuid.uuid4()
    async with maker() as session:
        session.add(
            PolicySet(
                id=policy_set_id,
                key=POLICY_SET_KEY,
                name="Capped list contract",
                owner="qa",
            )
        )
        await session.commit()

    app = create_app()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client, maker, policy_set_id

    await engine.dispose()


def _url(path: str) -> str:
    return f"/api/ai/policy-sets/{POLICY_SET_KEY}/{path}"


def _envelope(response, collection_key: str) -> tuple[list, int, bool]:
    """Unpack a capped-list response, failing legibly when there is no envelope.

    Every test below would otherwise reach for `body["runs"]` on whatever came
    back, and a bare array answers that with `TypeError: list indices must be
    integers`. That is a true consequence of the defect but a poor witness to
    it: the same crash appears if this file simply misspells the key, so the
    message cannot tell a real regression from a typo in its own scaffolding.
    Stating the shape requirement here means a failure says which it was.
    """
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict), (
        "a limited endpoint returned a bare array, so no caller can tell a "
        "complete list from a cut-short one"
    )
    for field in (collection_key, "count", "truncated"):
        assert field in body, f"envelope is missing '{field}': got {sorted(body)}"
    return body[collection_key], body["count"], body["truncated"]


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_a_capped_list_arrives_as_an_object_that_can_carry_the_cap(
    client, path, collection_key, seed
):
    """A bare array fails here whatever it holds -- it has nowhere to say so."""
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    response = await http_client.get(_url(path), params={"limit": WINDOW})
    rows, _count, _truncated = _envelope(response, collection_key)

    assert isinstance(rows, list)


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_withheld_rows_are_admitted(client, path, collection_key, seed):
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    response = await http_client.get(_url(path), params={"limit": WINDOW})
    rows, _count, truncated = _envelope(response, collection_key)

    assert len(rows) == WINDOW
    assert truncated is True, (
        f"{SEEDED_ROWS - WINDOW} rows were withheld and the response did not say so"
    )


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_a_complete_list_is_not_reported_as_cut_short(
    client, path, collection_key, seed
):
    """The detector has to be able to stay quiet, or it detects nothing."""
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    response = await http_client.get(_url(path), params={"limit": ROOMY_WINDOW})
    rows, _count, truncated = _envelope(response, collection_key)

    assert len(rows) == SEEDED_ROWS
    assert truncated is False, (
        "every row was returned, so a partial-list warning here would train the "
        "reader to ignore the one that matters"
    )


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_the_count_matches_the_rows_delivered(
    client, path, collection_key, seed
):
    """A count the list disagrees with is a number that misleads while being cited."""
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    for requested in (WINDOW, ROOMY_WINDOW):
        response = await http_client.get(_url(path), params={"limit": requested})
        rows, count, _truncated = _envelope(response, collection_key)
        assert count == len(rows)


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_an_exactly_full_page_errs_towards_warning(
    client, path, collection_key, seed
):
    """Documents the deliberate direction of the heuristic's error.

    `truncated` is `count == limit`, so a list that ends exactly on the cap
    reports itself cut short although nothing was withheld. That is the same
    trade `audit.py` and `evaluations.py` make -- it avoids a second count over
    an append-only table -- and it fails safe: the reader is told the list may
    continue when it does not, rather than told it is complete when it is not.
    Asserted so the direction is a decision on the record, not an accident.
    """
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    response = await http_client.get(_url(path), params={"limit": SEEDED_ROWS})
    rows, _count, truncated = _envelope(response, collection_key)

    assert len(rows) == SEEDED_ROWS
    assert truncated is True


@pytest.mark.parametrize(("path", "collection_key", "seed"), CAPPED_LISTS)
async def test_a_limit_below_one_is_refused(client, path, collection_key, seed):
    """Without a floor the truncation signal stops being a truth claim.

    At `limit=0` the server returns nothing and `count == limit` holds, so an
    empty response would announce itself as a truncated one. Rejecting the
    request keeps the signal meaningful instead of asking every client to
    special-case it.
    """
    http_client, maker, policy_set_id = client
    await seed(maker, policy_set_id, SEEDED_ROWS)

    response = await http_client.get(_url(path), params={"limit": 0})

    assert response.status_code == 422
