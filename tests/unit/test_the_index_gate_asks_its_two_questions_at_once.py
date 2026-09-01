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


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    _Client.exists = True
    _Client.ready_ids = ["manifest-1"]


async def test_the_two_probes_run_at_the_same_time() -> None:
    """The measurement that makes the change worth making.

    Both probes sleep the same known duration. Serial, the pair costs two of
    them; concurrent, it costs one. The wall key is asserted against the *sum*
    rather than against a hoped-for number, so this cannot pass by the probes
    simply being fast.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe({"timings_ms": timings}, _Client)

    assert timings["index_probe"] >= _PROBE_MS * 0.8
    assert timings["projection_readiness"] >= _PROBE_MS * 0.8
    assert "index_gate_wall" in timings

    serial = timings["index_probe"] + timings["projection_readiness"]
    assert timings["index_gate_wall"] < serial * 0.75, (
        f"the gate took {timings['index_gate_wall']}ms against a serial cost of "
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
    """The `None`-guard, on the new wall key as well as the two it sits beside.

    This is the one case where the gate *passes*, so all three writes are
    attempted with no map to write into. Execution then continues past the gate
    and stops later on this stub's deliberately incomplete settings — which is
    fine and is the point: what matters is that it got that far, rather than
    failing at the gate with a `NoneType` that could not be subscripted.
    """

    response = await _run_scope_until_index_probe(None, _Client)

    reason = response["retrieval"].get("reason") or ""
    assert "NoneType" not in reason, reason
    assert "timings" not in reason, reason
    # It reached the stage after the gate, which is what proves the gate ran
    # through all three recordings without one.
    assert "embedding" in reason, reason


async def test_the_gate_wall_is_not_a_container_over_unrelated_stages() -> None:
    """A wall key measures the phase it names, and nothing after it.

    `index_gate_wall` sits beside `retrieval_discovery_wall` in the map and must
    read the same way: the wall of one concurrent pair, not a container that has
    quietly grown to include the query that follows it. If it ever exceeded the
    two probes by a meaningful margin it would be double-counting.
    """

    timings: dict[str, int] = {}
    await _run_scope_until_index_probe({"timings_ms": timings}, _Client)

    slowest = max(timings["index_probe"], timings["projection_readiness"])
    assert timings["index_gate_wall"] >= slowest
    assert timings["index_gate_wall"] <= slowest + 40, timings
