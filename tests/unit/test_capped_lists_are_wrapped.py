"""An endpoint that caps a collection must return something able to say so.

Four separate clients in this codebase have been found treating a capped
collection as the whole of it: two that had no way to know, and two that were
told and ignored it. Each was fixed where it was found. This is the attempt to
stop the fifth being written, by holding the *shape* of the response rather than
any one endpoint's behaviour.

The rule is narrow on purpose and states only what a schema can prove:

    an operation that accepts a cap must not answer with a bare JSON array

A bare array has nowhere to put "there is more than this". Wrapping it does not
by itself make a client honest -- that is a separate claim, asserted where the
client lives -- but it is the precondition, and it is the half that can be
enforced centrally. `audit.py`, `evaluations.py` and `extraction.py` already
satisfy it; this is what keeps a new router from quietly not.

WHAT THIS CANNOT SEE, stated so its reach is not overestimated:

  * a cap applied inside a repository or service with no query parameter to
    declare it. Nothing reaches the schema, so nothing here can react. Two such
    endpoints exist today and are recorded in the report accompanying this file
    rather than silently tolerated here.
  * a capped list nested inside an object response. The envelope is an object,
    so this passes it.
  * whether any client honours the signal once it is sent.

It is a precondition check, not the whole invariant.

The scan's own verdict is an empty list of offenders, which is also what
scanning nothing produces, so it counts what it examined and fails when that
count collapses -- and the detector itself is exercised against synthetic
schemas below, so "it still detects" does not rest on the application happening
to contain an example.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute

from policy_platform.api.app import create_app

#: Query parameters that mean "return at most this many". General pagination
#: vocabulary rather than anything this repository invented, so an endpoint
#: adopting a different-but-standard spelling is still caught.
CAP_PARAMETERS = frozenset({"limit", "top", "page_size", "max_results", "per_page"})

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    query_parameters: frozenset[str]
    response_type: str | None

    @property
    def caps(self) -> frozenset[str]:
        return self.query_parameters & CAP_PARAMETERS

    @property
    def returns_bare_list(self) -> bool:
        return self.response_type == "array"

    def __str__(self) -> str:
        return f"{self.method.upper()} {self.path}"


def _resolve(schema: dict, spec: dict) -> dict:
    """Follow a single `$ref` so a referenced array is not mistaken for an object."""
    ref = schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return schema
    node: object = spec
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return schema
        node = node[part]
    return node if isinstance(node, dict) else schema


def operations(spec: dict) -> list[Operation]:
    """Every HTTP operation in an OpenAPI document, with what it takes and returns."""
    found: list[Operation] = []
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            query = frozenset(
                parameter.get("name")
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query"
            )
            body = (
                operation.get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            resolved = _resolve(body, spec) if isinstance(body, dict) else {}
            found.append(
                Operation(
                    method=method,
                    path=path,
                    query_parameters=query,
                    response_type=resolved.get("type"),
                )
            )
    return found


def offenders(spec: dict) -> list[Operation]:
    """Operations that accept a cap and answer with a bare array."""
    return [op for op in operations(spec) if op.caps and op.returns_bare_list]


# --------------------------------------------------------------------------
# The detector, exercised against schemas written here.
#
# The application-wide check below reports an empty list on a healthy codebase.
# So does a detector that has stopped detecting. These three fix the detector's
# behaviour against inputs whose answer is known, so that "no offenders" in the
# real API means the API is clean rather than that the scan went quiet.
# --------------------------------------------------------------------------


def _spec(*, response: dict, query: list[dict] | None = None) -> dict:
    return {
        "paths": {
            "/things": {
                "get": {
                    "parameters": query or [],
                    "responses": {
                        "200": {"content": {"application/json": {"schema": response}}}
                    },
                }
            }
        }
    }


_ARRAY = {"type": "array", "items": {"type": "object"}}
_ENVELOPE = {"type": "object"}
_CAP = [{"in": "query", "name": "limit"}]


def test_the_detector_flags_a_bare_array_behind_a_cap():
    """The case every fix so far has been an instance of."""
    assert [str(op) for op in offenders(_spec(response=_ARRAY, query=_CAP))] == [
        "GET /things"
    ]


@pytest.mark.parametrize("cap", sorted(CAP_PARAMETERS))
def test_the_detector_flags_every_spelling_of_a_cap(cap):
    """A cap named something other than `limit` is still a cap."""
    spec = _spec(response=_ARRAY, query=[{"in": "query", "name": cap}])
    assert offenders(spec), f"a cap spelled `{cap}` was not recognised as one"


def test_the_detector_passes_a_wrapped_list_behind_a_cap():
    """The shape the fix produces has to be accepted, or the rule is unusable."""
    assert offenders(_spec(response=_ENVELOPE, query=_CAP)) == []


def test_the_detector_ignores_an_uncapped_list():
    """A list returned whole is complete, and a bare array is honest for it."""
    assert offenders(_spec(response=_ARRAY)) == []


def test_the_detector_sees_through_a_reference():
    """`response_model=list[X]` and a `$ref` to an array must read the same."""
    spec = _spec(response={"$ref": "#/components/schemas/Things"}, query=_CAP)
    spec["components"] = {"schemas": {"Things": _ARRAY}}
    assert offenders(spec), "an array reached through a $ref was read as an object"


# --------------------------------------------------------------------------
# The application.
# --------------------------------------------------------------------------


def test_the_scan_reaches_every_route_the_application_serves():
    """The scan has to still see.

    Asserted by comparing the paths the scan walked against the routes the
    application actually registers, rather than against a number. A count floor
    can stay healthy while the scan quietly narrows -- that is how an earlier
    guard of mine passed after losing an endpoint, and it is why this is a
    coverage comparison.
    """
    app = create_app()
    served = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert served, "the application registered no routes -- nothing was examined"

    scanned = set(app.openapi().get("paths", {}))
    unscanned = served - scanned
    assert not unscanned, (
        f"{len(unscanned)} route(s) the application serves never reached the scan, "
        f"so the check below has not looked at them: {sorted(unscanned)}"
    )


def test_every_endpoint_that_accepts_a_cap_can_declare_it():
    """A capped collection must arrive in something able to say it was capped.

    The two floors run before the verdict and cover the two ways this goes
    blind: an empty schema, and a cap vocabulary that stops matching anything.
    Neither can mask a real offender, because an offender is itself a capped
    endpoint and so keeps the second floor satisfied.
    """
    spec = create_app().openapi()

    found = operations(spec)
    assert found, "the schema yielded no operations -- the scan read nothing"

    capped = [op for op in found if op.caps]
    assert capped, (
        "no endpoint in this API accepts a cap, which is not credible for a "
        f"{len(found)}-operation surface -- the cap vocabulary "
        f"{sorted(CAP_PARAMETERS)} has stopped matching how this codebase spells it"
    )

    bare = [op for op in capped if op.returns_bare_list]
    assert not bare, (
        "these endpoints cap what they return and answer with a bare array, so "
        "no caller can tell a complete collection from a cut-short one:\n  "
        + "\n  ".join(sorted(str(op) for op in bare))
        + "\n\nReturn an object carrying the collection alongside `count` and "
        "`truncated`, as audit-events, evaluations and extraction already do."
    )
