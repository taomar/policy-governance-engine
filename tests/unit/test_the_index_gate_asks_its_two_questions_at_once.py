"""The index gate asks its two questions at once, and still answers in order.

"Does this index exist" and "does it carry a usable projection" are two live
round trips to the search service, on their own connections. They were serial,
and each measured around a second: together they were **more than half of all
the time a decision spent on search**, before either had asked the index
anything about the actual question.

They are independent questions, so they are now asked concurrently. The order of
the *answers* is what carries the meaning, and that is what these tests pin. The
three states an operator acts on differently must stay distinguishable:

    the index is not built yet          -> republish or rebuild
    it exists but carries no projection -> rebuild the projection
    the search service itself failed    -> retry, or look at the service

The hazard concurrency introduces is specific and worth naming: a readiness
probe against an index that does not exist **fails by definition**. If that
incidental failure were allowed to win the race, "not built yet" — which an
operator can act on — would be reported as "something went wrong", which they
cannot. The existence answer is therefore always read first.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from policy_platform.infrastructure.assistants import ai_case_project
from tests.unit.test_p0_rest_telemetry_closes_measurement_blind_spots import (
    _PolicySet,
    _run_scope_until_index_probe,
)

pytestmark = pytest.mark.anyio

#: Long enough that a serial pair could not be mistaken for a concurrent one at
#: the resolution the timings are recorded in.
_PROBE_DELAY = 0.08
_PROBE_MS = int(_PROBE_DELAY * 1000)

#: Deliberately *longer* than a probe, and that is load-bearing rather than
#: incidental. With three equal durations, a wall of `max(a, b, c)` and a wall of
#: `max(a, b)` are the same number, so a ratio test against their sum passes
#: whether the embedding is inside the concurrent group or behind it. Making the
#: embedding the slowest member means the wall can only reach it by containing
#: it.
_EMBED_DELAY = _PROBE_DELAY * 2
_EMBED_MS = int(_EMBED_DELAY * 1000)


class _Client:
    """A search service that answers both probes, each taking real time."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    #: What `index_exists` returns, or raises when it is an exception.
    exists: Any = True
    #: What the readiness probe's underlying filter returns, or raises.
    ready_ids: Any = ["manifest-1"]

    async def index_exists(self, name: str) -> bool:
        await asyncio.sleep(_PROBE_DELAY)
        if isinstance(type(self).exists, BaseException):
            raise type(self).exists
        return type(self).exists

    async def find_ids_by_filter(self, index: str, **kwargs: Any) -> list[str]:
        await asyncio.sleep(_PROBE_DELAY)
        if isinstance(type(self).ready_ids, BaseException):
            raise type(self).ready_ids
        return list(type(self).ready_ids)

    async def vector_search(self, index: str, **kwargs: Any) -> list[dict]:
        """Matches nothing, so a run that gets this far ends in `no_match`.

        These tests are about what happens *before* the query. Returning no hits
        gives the successful path a clean, named terminal state instead of an
        exception standing in for one.
        """

        return []


class _Embedder:
    """The embedding client, taking the same known time as the probes."""

    calls: list[list[str]] = []
    error: BaseException | None = None

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        type(self).calls.append(list(inputs))
        await asyncio.sleep(_EMBED_DELAY)
        if type(self).error is not None:
            raise type(self).error
        return [[0.1, 0.2, 0.3] for _ in inputs]


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch) -> None:
    _Client.exists = True
    _Client.ready_ids = ["manifest-1"]
    _Embedder.calls = []
    _Embedder.error = None
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _Embedder)


async def test_the_two_probes_run_at_the_same_time() -> None:
    """The measurement that makes the change worth making.

    Driven through the retrieval-only route on purpose: that route runs no
    embedding, so the preflight wall contains exactly these two probes and
    nothing else. Serial, the pair costs two of them; concurrent, it costs one.
    The wall is asserted against the *sum* rather than a hoped-for number, so
    this cannot pass by the probes simply being fast.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe(
        {"timings_ms": timings}, _Client, policies_only=True
    )

    assert timings["index_probe"] >= _PROBE_MS * 0.8
    assert timings["projection_readiness"] >= _PROBE_MS * 0.8
    assert "retrieval_preflight_wall" in timings
    assert "embedding" not in timings, "this route should have run no embedding"

    serial = timings["index_probe"] + timings["projection_readiness"]
    assert timings["retrieval_preflight_wall"] < serial * 0.75, (
        f"the gate took {timings['retrieval_preflight_wall']}ms against a serial cost of "
        f"{serial}ms — the probes are not overlapping"
    )


async def test_an_index_that_is_not_built_says_so_even_though_readiness_also_failed() -> None:
    """The control that concurrency exists to not break.

    A readiness probe against an absent index fails because the index is absent.
    That failure is a consequence of the state the other probe already named, so
    it must be discarded rather than reported. Letting it win would turn a state
    an operator can repair into one they can only puzzle over.
    """

    _Client.exists = False
    _Client.ready_ids = RuntimeError("no such index")

    timings: dict[str, int] = {}
    response = await _run_scope_until_index_probe({"timings_ms": timings}, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_NOT_BUILT
    assert "has not been built yet" in response["retrieval"]["reason"]
    # Both probes still report what they cost, including the one whose answer
    # was thrown away.
    assert timings["index_probe"] >= _PROBE_MS * 0.8
    assert timings["projection_readiness"] >= _PROBE_MS * 0.8


async def test_a_readiness_failure_against_a_live_index_is_still_a_search_fault() -> None:
    """The other side of the same control, asserted on what the operator is told.

    When the index really is there, a readiness probe that failed failed on its
    own account. Discarding *that* would hide a genuine search fault behind a
    successful existence check.

    The assertion is on the reported reason, not merely on the status, because
    the status alone cannot tell the two mechanisms apart: without the explicit
    re-raise the code would go on to read `.ready` off an exception object and
    fail anyway — with an `AttributeError` naming a Python type instead of the
    search error the operator actually needs to see.
    """

    _Client.exists = True
    _Client.ready_ids = RuntimeError("the search service refused the probe")

    response = await _run_scope_until_index_probe({"timings_ms": {}}, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    reason = response["retrieval"]["reason"]
    assert "the search service refused the probe" in reason, reason
    assert "has no attribute" not in reason, reason


async def test_an_index_without_a_projection_is_refused_as_before() -> None:
    """The third state, unchanged.

    An index that exists but carries no usable projection must still raise
    rather than fall through to a query — matching a rendered question against
    an unrendered corpus produces a confident "nothing bears on this", which is
    indistinguishable from a real answer afterwards.
    """

    _Client.exists = True
    _Client.ready_ids = []  # neither ready, nor built under this profile

    with pytest.raises(ai_case_project.IndexProjectionUnavailable):
        await _run_scope_until_index_probe({"timings_ms": {}}, _Client)


async def test_a_failing_existence_probe_is_reported_rather_than_swallowed() -> None:
    """`return_exceptions` collects faults; it must not absorb them.

    This is the sharpest edge of the change. Gathering with
    `return_exceptions=True` turns a raised error into a *returned value*, and an
    exception object is truthy — so without the explicit re-raise, `if not
    index_present:` would read a failed probe as "the index is there" and the
    request would carry on querying an index whose existence was never
    established.

    Asserting only the status cannot catch that, because the request would fail
    later for an unrelated reason and still report a failed search. So the
    assertion is that the reason names *this* fault.
    """

    _Client.exists = RuntimeError("the existence probe failed")
    _Client.ready_ids = ["manifest-1"]

    response = await _run_scope_until_index_probe({"timings_ms": {}}, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    reason = response["retrieval"]["reason"]
    assert "the existence probe failed" in reason, reason


async def test_the_gate_reports_nothing_when_no_one_asked_for_timings() -> None:
    """The `None`-guard, on the wall key as well as the leaves beside it.

    This is the case where the whole preflight *passes*, so all four writes are
    attempted with no map to write into. The run then continues to a normal
    `no_match`, which is what proves the preflight ran through every recording
    without a `NoneType` that could not be subscripted.
    """

    response = await _run_scope_until_index_probe(None, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_NO_MATCH


async def test_the_gate_wall_is_not_a_container_over_unrelated_stages() -> None:
    """A wall key measures the phase it names, and nothing after it.

    `retrieval_preflight_wall` sits beside `retrieval_discovery_wall` in the map and must
    read the same way: the wall of one concurrent group, not a container that has
    quietly grown to include the query that follows it. If it ever exceeded the
    group by a meaningful margin it would be double-counting.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe({"timings_ms": timings}, _Client)

    # Every member of the group, not just the two probes: if the embedding is
    # the slowest — as it is here by design — a `slowest` that ignored it would
    # fail this test against correct code.
    slowest = max(
        timings["index_probe"],
        timings["projection_readiness"],
        timings.get("embedding", 0),
    )
    assert timings["retrieval_preflight_wall"] >= slowest
    assert timings["retrieval_preflight_wall"] <= slowest + 40, timings


# ── the embedding joins the group ────────────────────────────────────


async def test_the_embedding_runs_beside_the_probes_rather_than_behind_them() -> None:
    """The embedding needed nothing the gate produces, and was waiting anyway.

    It takes only the scenario, which has been in hand since the request
    arrived. It was serial behind the gate because it was written after it, not
    because it depended on it.

    The assertion that matters is the second one, and the reason is subtle: a
    ratio against the serial sum is satisfied by *either* arrangement when all
    three calls take the same time, because `max(a, b, c)` and `max(a, b)` are
    then the same number. The embedding is therefore made the slowest of the
    three, so a wall that reaches its duration can only have contained it.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe({"timings_ms": timings}, _Client)

    assert _Embedder.calls, "the embedding never ran"
    assert timings["embedding"] >= _EMBED_MS * 0.8

    # The wall reaches the slowest member, which is the embedding. Behind the
    # gate it would stop at the probes and fall short of this.
    assert timings["retrieval_preflight_wall"] >= _EMBED_MS * 0.8, (
        f"preflight wall {timings['retrieval_preflight_wall']}ms does not reach the "
        f"{timings['embedding']}ms embedding — it ran outside the group, not inside it"
    )
    serial = (
        timings["index_probe"] + timings["projection_readiness"] + timings["embedding"]
    )
    assert timings["retrieval_preflight_wall"] < serial * 0.75, (
        f"preflight took {timings['retrieval_preflight_wall']}ms against a serial cost "
        f"of {serial}ms"
    )


async def test_a_refused_index_discloses_the_embedding_it_paid_for() -> None:
    """The cost of this concurrency, made visible rather than hidden.

    Starting the embedding before the gate has answered means a project whose
    index is missing now pays for a call it never used to make. That is the
    trade, and it is a real one — so it is disclosed in the same telemetry as
    everything else, rather than being a cost nobody can see.
    """

    _Client.exists = False

    timings: dict[str, int] = {}
    response = await _run_scope_until_index_probe(
        {"timings_ms": timings}, _Client
    )

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_NOT_BUILT
    assert _Embedder.calls, "the embedding should have been started before the answer"
    assert "embedding" in timings, "a call was paid for and not reported"


async def test_a_failed_embedding_does_not_disguise_a_missing_index() -> None:
    """Answer order again, with a third answer in the race.

    An embedding fault says nothing about the index. If it were read first, a
    project whose index simply has not been built would be told its search
    failed — sending an operator to look at the wrong system entirely.
    """

    _Client.exists = False
    _Embedder.error = RuntimeError("the embedding deployment refused the call")

    response = await _run_scope_until_index_probe({"timings_ms": {}}, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_NOT_BUILT


async def test_a_failed_embedding_on_a_live_index_is_still_reported() -> None:
    """And it must not be swallowed either.

    When the gate passes, the embedding's fault is the only thing that went
    wrong, and there is no vector to search with. It is re-raised for the same
    reason the other two are: `return_exceptions` returns it as a value, and a
    value is not an error until something checks.
    """

    _Embedder.error = RuntimeError("the embedding deployment refused the call")

    response = await _run_scope_until_index_probe({"timings_ms": {}}, _Client)

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    reason = response["retrieval"]["reason"]
    assert "the embedding deployment refused the call" in reason, reason


async def test_an_embedding_client_that_cannot_be_built_reports_no_duration() -> None:
    """Absent, not zero — the same rule the search client beside it follows.

    The embedding client is constructed before its clock starts. If it were
    constructed inside the timed region, a constructor that failed would emit
    `embedding: 0` — a present duration for a call that was never made, on a
    map whose readers are told that a `0` means "under a millisecond" and never
    "did not happen".
    """

    class _BrokenEmbedder:
        def __init__(self, settings: Any) -> None:
            raise RuntimeError("the embedding client could not be constructed")

    import policy_platform.infrastructure.assistants.ai_case_project as module

    original = module.AzureOpenAIClient
    module.AzureOpenAIClient = _BrokenEmbedder
    try:
        timings: dict[str, int] = {}
        response = await _run_scope_until_index_probe({"timings_ms": timings}, _Client)
    finally:
        module.AzureOpenAIClient = original

    assert response["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert "embedding" not in timings, (
        f"a call that was never made reported a duration: {timings.get('embedding')!r}"
    )



async def test_the_retrieval_only_route_starts_no_embedding_at_all() -> None:
    """`/policies` runs no embedding, and absent is not zero.

    The concurrency must not have quietly given the retrieval-only route a model
    call it does not need — that would be the route doing *more* work than it
    did before, to save time it was not spending.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe(
        {"timings_ms": timings}, _Client, policies_only=True
    )

    assert _Embedder.calls == [], "the retrieval-only route made an embedding call"
    assert "embedding" not in timings
    assert "retrieval_preflight_wall" in timings

