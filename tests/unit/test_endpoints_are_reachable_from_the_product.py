"""An endpoint the product never calls is unreachable, however live it is.

`tests/unit/test_capabilities_are_reachable.py` closes the shape where a
capability under `src/` has no production caller. It cannot see this one. An
HTTP endpoint *is* reachable by its own measure -- it is registered, it is
routable, `curl` will answer it -- and the analyser stops at the router because
the router is where Python's call graph ends.

The sub-shape this closes:

    reachable from the API, unreachable from the product.

The witness. `GET /api/policy-sets/{key}/policies` arranges rules under the
passage that stated them. It was written, measured, and reported as working --
411 rules into 183 policies, every rule in exactly one policy. Nothing in
`apps/web/src` called it. The review queue read the flat list instead, so one
sentence imposing three obligations reached the reviewer as three unrelated
cards. The capability existed and the product did not have it, and the number
that said otherwise was obtained by calling the function directly rather than
through the surface a user sees.

WHY THE FLOORS COME FIRST

The verdict is a set difference: backend routes minus the routes the product
calls. That arithmetic is silent in the direction that matters. An extractor
that finds no backend routes yields an empty difference and a green test, which
is a guard reporting "nothing unreachable" because it looked at nothing. Five
checks in this repository have passed that way. So the floors are asserted
before the difference is taken, and one of them is on the *intersection*: if
either side's path normalisation drifts, the two vocabularies stop meeting and
the intersection collapses even while both counts stay healthy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "apps" / "web" / "src"

#: Served by FastAPI itself, not written here and not product surfaces. A web
#: client is not expected to call its own schema document or the health probe
#: that a load balancer uses.
FRAMEWORK_PATHS = {
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
    "/health",
}

#: Endpoints known to have no caller in the product, each with the reason it is
#: tolerated rather than fixed.
#:
#: This is a register of reported findings, not an allowlist to grow. Adding a
#: line here is a decision to ship an endpoint the product cannot reach, and
#: `test_known_unreachable_register_has_not_rotted` deletes the excuse the
#: moment one of these acquires a caller -- so the list cannot quietly outlive
#: what it describes.
KNOWN_UNREACHABLE = {
    "GET /api/policy-exceptions/*": (
        "Single-exception fetch. The product lists exceptions and edits them "
        "from the list, so it never needs one by id. Reported, not fixed."
    ),
    "POST /api/policy-sets/*/policy-index/rebuild": (
        "Rebuilds a project's policy index. The build normally happens on publish "
        "and is best effort, so this is the repair path for the case where that "
        "build failed and the index is stale or absent. `policy_index_states` "
        "records enough to detect that, so the product could show it and offer "
        "this -- until it does, a failed build is only repairable by an operator. "
        "Recorded as a gap, not as a design."
    ),
    "GET /api/policy-sets/*/policy-index": (
        "Reads the app's recorded state for a project's policy index so the "
        "product can show whether the index is current, stale, unbuilt, or not "
        "applicable before offering the rebuild action. This is the backend half "
        "of that repair surface; until the web half lands, the state is still "
        "only visible to direct API callers. Recorded as a gap, not as a design."
    ),
}


def _normalise_backend(path: str) -> str:
    """`/api/policy-sets/{key}/policies` -> `/api/policy-sets/*/policies`."""
    return re.sub(r"\{[^}]*\}", "*", path).rstrip("/") or "/"


def _normalise_frontend(literal: str) -> str:
    """`/api/policy-sets/${encodeURIComponent(key)}/policies` -> the same shape.

    Interpolations are matched by brace depth rather than by `[^}]*`, because
    the expression inside one is arbitrary TypeScript and a nested brace would
    otherwise end the match early and corrupt every path after it.
    """
    out: list[str] = []
    i = 0
    while i < len(literal):
        if literal.startswith("${", i):
            depth = 1
            j = i + 2
            while j < len(literal) and depth:
                if literal[j] == "{":
                    depth += 1
                elif literal[j] == "}":
                    depth -= 1
                j += 1
            out.append("*")
            i = j
        else:
            out.append(literal[i])
            i += 1

    joined = "".join(out).split("?")[0].split("#")[0]
    joined = re.sub(r"\*+", "*", joined)
    # A `*` glued to the end of a segment came from an interpolation inside that
    # segment, which is how query strings are appended here -- `/api/audit-events
    # ${qs}`. A path parameter always occupies a whole segment and so is preceded
    # by a slash. Trimming only the glued form keeps `/api/documents/*` distinct
    # from `/api/documents` with a query.
    joined = re.sub(r"(?<!/)\*+$", "", joined)
    return joined.rstrip("/") or "/"


def _backend_endpoints() -> dict[str, str]:
    """Every route the application exposes, as `METHOD /shape` -> path."""
    from policy_platform.api.app import app

    found: dict[str, str] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        shape = _normalise_backend(route.path)
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found[f"{method} {shape}"] = shape
    return found


def _product_call_shapes() -> set[str]:
    """Every API path the shipped web client asks for.

    Test files are excluded deliberately. A capability exercised only from a
    test is the precise thing this guard exists to catch, and counting a test
    as a caller would make it blind to its own subject.
    """
    shapes: set[str] = set()
    for path in sorted([*WEB_SRC.rglob("*.ts"), *WEB_SRC.rglob("*.tsx")]):
        if ".test." in path.name or ".spec." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        # A path starts at the opening quote (`/api/...`) or straight after an
        # interpolation (`${API_BASE_URL}/api/...`). Anchoring to a delimiter
        # matters: a bare search for "/api/" would also match prose in comments,
        # and a mention is not a call. Counting mentions as callers would let an
        # unreachable endpoint hide behind a comment describing it.
        for raw in re.findall(r"""(?:["'`]|\})(/api/[^"'`]*)""", text):
            shapes.add(_normalise_frontend(raw))
    return shapes


# --------------------------------------------------------------------------
# Floors. These run before the verdict, because the verdict is a set difference
# and a set difference cannot distinguish "nothing is wrong" from "nothing was
# examined".
# --------------------------------------------------------------------------


def test_the_backend_extractor_still_sees_routes():
    endpoints = _backend_endpoints()
    assert len(endpoints) > 20, (
        f"Only {len(endpoints)} routes found on the application. The verdict "
        "below subtracts from this set, so an empty or truncated one would "
        "report universal reachability while examining nothing."
    )


def test_the_product_extractor_still_sees_calls():
    shapes = _product_call_shapes()
    assert WEB_SRC.is_dir(), (
        f"{WEB_SRC} does not exist. A guard scanning a missing directory finds "
        "no callers, flags every endpoint, and its failure would be read as a "
        "reachability problem rather than a broken path."
    )
    assert len(shapes) > 20, (
        f"Only {len(shapes)} API call shapes found in {WEB_SRC}. The client is "
        "known to call dozens; a collapse here means the literal extractor "
        "stopped matching, not that the product stopped calling."
    )


def test_the_two_extractors_still_speak_the_same_shapes():
    """The floor the counts cannot provide.

    Both sides can be healthy and still fail to meet: if either normalisation
    drifts -- a parameter left as `{key}`, a query string not trimmed -- every
    endpoint reads as uncalled while both counts stay large. The intersection is
    the only measure that fails when the two vocabularies diverge.
    """
    backend_shapes = set(_backend_endpoints().values())
    called = _product_call_shapes()
    agreed = backend_shapes & called

    assert len(agreed) > 20, (
        f"Only {len(agreed)} paths matched between {len(backend_shapes)} routes "
        f"and {len(called)} product calls. The two extractors have stopped "
        "agreeing on path shape; the verdict below would be noise."
    )


def test_no_product_call_points_at_a_route_that_does_not_exist():
    """The converse reading, and a check on the extractor at the same time.

    A call shape matching no route is either a client asking for something the
    API does not serve, or evidence that this file's normalisation is wrong. It
    is worth knowing which, and both are worth failing on.
    """
    backend_shapes = set(_backend_endpoints().values())
    called = _product_call_shapes()
    orphaned = sorted(called - backend_shapes)

    assert not orphaned, (
        "The product calls paths the application does not serve:\n  "
        + "\n  ".join(orphaned)
    )


# --------------------------------------------------------------------------
# Verdict.
# --------------------------------------------------------------------------


def test_every_endpoint_the_api_exposes_is_reached_from_the_product():
    endpoints = _backend_endpoints()
    called = _product_call_shapes()

    unreachable = sorted(
        name
        for name, shape in endpoints.items()
        if shape not in called
        and shape not in FRAMEWORK_PATHS
        and name not in KNOWN_UNREACHABLE
    )

    assert not unreachable, (
        "These endpoints are reachable over HTTP and unreachable from the "
        "product -- no code under apps/web/src calls them:\n  "
        + "\n  ".join(unreachable)
        + "\n\nAn endpoint no client calls is a capability the product does not "
        "have, whatever its tests say. Either give it a caller, or record it in "
        "KNOWN_UNREACHABLE with the reason it is tolerated."
    )


def test_known_unreachable_register_has_not_rotted():
    """A recorded exception that has since acquired a caller is a stale excuse.

    Without this, the register only ever grows: entries survive the condition
    that justified them and the guard's real coverage shrinks silently behind a
    list nobody rereads.
    """
    endpoints = _backend_endpoints()
    called = _product_call_shapes()

    now_reachable = sorted(
        name
        for name in KNOWN_UNREACHABLE
        if name in endpoints and endpoints[name] in called
    )
    assert not now_reachable, (
        "These are recorded as unreachable from the product but the product now "
        "calls them. Remove them from KNOWN_UNREACHABLE:\n  "
        + "\n  ".join(now_reachable)
    )

    retired = sorted(name for name in KNOWN_UNREACHABLE if name not in endpoints)
    assert not retired, (
        "These are recorded as unreachable but no longer exist on the "
        "application. Remove them from KNOWN_UNREACHABLE:\n  "
        + "\n  ".join(retired)
    )


# --------------------------------------------------------------------------
# Controls. A guard holding only offenders cannot tell when it has begun
# over-reaching.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shape",
    [
        "/api/policy-sets/*/policies",
        "/api/policy-sets/*/candidate-rules",
        "/api/policy-sets",
    ],
)
def test_endpoints_the_product_demonstrably_calls_are_seen_as_called(shape: str):
    """Positive control.

    A detector that finds nothing reachable would still pass the verdict above
    by flagging everything and being suppressed -- these assert it can see a
    call it should see. The first is the witness: the assembling view, whose
    absence from this set is what the wiring fixed.
    """
    assert shape in _product_call_shapes(), (
        f"{shape} is called by the product but the extractor did not see it. "
        "The verdict cannot be trusted while this is true."
    )


def test_a_path_parameter_is_not_confused_with_a_query_string():
    """Control on normalisation itself.

    These two collapse to the same string under a careless trim, and if they do
    then `/api/documents/{id}` reads as called whenever anything fetches
    `/api/documents?...`, hiding a genuinely unreachable endpoint.
    """
    assert _normalise_frontend("/api/documents/${id}") == "/api/documents/*"
    assert _normalise_frontend("/api/documents${qs}") == "/api/documents"
    assert _normalise_frontend("/api/documents/${id}") != _normalise_frontend(
        "/api/documents${qs}"
    )


def test_normalisation_survives_a_nested_brace_in_an_interpolation():
    """Control on the brace-depth scan.

    A `[^}]*` match would end at the inner brace and leave the tail of the
    expression in the path, corrupting every segment after it.
    """
    assert (
        _normalise_frontend("/api/policy-sets/${fn({a: b})}/policies")
        == "/api/policy-sets/*/policies"
    )


def test_a_mention_in_a_comment_is_not_counted_as_a_caller():
    """Control against the loosest possible extractor.

    If prose counted, an endpoint could be documented into apparent
    reachability -- which is the failure mode of every guard that greps.
    """
    assert not re.findall(
        r"""(?:["'`]|\})(/api/[^"'`]*)""",
        "// TODO: nothing calls /api/policy-sets/x/policies yet",
    )
