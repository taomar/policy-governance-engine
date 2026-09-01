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
    "POST /api/policy-decisions/*/case": (
        "The audited external decision contract. Its callers are by design not "
        "in apps/web: an external system, and the separate consume demo app, "
        "which this scan does not read. The in-product Consume drawer will call "
        "it, and when it does `test_known_unreachable_register_has_not_rotted` "
        "requires this line to be deleted."
    ),
    "POST /api/policy-decisions/*/case/light": (
        "The compact audited decision contract. Its shipped caller is the separate "
        "consume demo app, while apps/web only displays integration snippets."
    ),
    "POST /api/policy-decisions/*/policies": (
        "The external retrieval-only contract. Its shipped caller is the separate "
        "consume demo app, which this scan deliberately does not read; apps/web "
        "only displays integration snippets and never sends this request."
    ),
    "GET /api/policy-decisions/*": (
        "Receipt read-back for the audited external decision contract. Same "
        "reason as the POST above: the caller is an external consumer today, "
        "and the register entry expires the moment apps/web calls it."
    ),
}


#: Modules whose `/api/...` literals are *shown*, not *sent*.
#:
#: `consumeSnippets.ts` builds the cURL, Python, JavaScript and raw-HTTP
#: examples the Consume drawer puts on a reader's clipboard. Its path literals
#: are documentation text destined for somebody else's service; this app never
#: requests them. Counting them as callers is not a harmless over-count — it is
#: the exact failure this guard exists to find, running in reverse: an endpoint
#: no client calls would read as reached because a code sample mentions it, and
#: the register below would go stale on the strength of a string in a text box.
#:
#: The exclusion is not taken on trust. `test_a_display_only_module_really_is_
#: display_only` asserts each module here performs no request at all, so the
#: moment one acquires a `fetch` the declaration stops being true and the guard
#: fails rather than quietly ignoring a real caller.
DISPLAY_ONLY_MODULES = {
    "consumeSnippets.ts",
}

#: How a module reaches the network. Any of these appearing in a declared
#: display-only module retires the declaration.
_REQUEST_CONSTRUCTS = (
    r"\bfetch\s*\(",
    r"\brequest\s*[<(]",
    r"\baxios\b",
    r"\bXMLHttpRequest\b",
    r"\bsendBeacon\s*\(",
    r"\bEventSource\s*\(",
)


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


def _product_calls() -> set[str]:
    """Every API call the shipped web client makes, as `METHOD shape`.

    Test files are excluded deliberately. A capability exercised only from a
    test is the precise thing this guard exists to catch, and counting a test
    as a caller would make it blind to its own subject.

    WHY THE METHOD IS PART OF THE ANSWER. This returned bare path shapes until
    a delete went missing. The verdict compared paths alone, so an endpoint
    counted as reached whenever *any* method on its path was called --
    `DELETE /api/policy-sets/{key}` passed on the strength of the `GET` beside
    it, while nothing in the product could delete a project. The guard was
    reporting "every endpoint is reached" and measuring "every endpoint's path
    is mentioned", which is the same shape of defect it exists to find: a check
    that judges something narrower than it claims, and reports success for what
    it could not see.

    The method is read from the request options that follow the path literal,
    defaulting to GET when there are none, which is what `request` itself does.
    A method belongs to the nearest path before it, so the search window stops
    at the next path literal rather than running to the end of the file --
    otherwise one `method: "POST"` would be claimed by every path above it.

    WHY SOME MODULES ARE SKIPPED. A path literal is evidence of a call only when
    the module containing it makes calls. `consumeSnippets.ts` renders worked
    examples for an *external* integrator; its `/api/policy-decisions/...`
    strings are text this app displays and never requests. See
    `DISPLAY_ONLY_MODULES`, and the floor test that keeps that claim honest.
    """
    calls: set[str] = set()
    for path in sorted([*WEB_SRC.rglob("*.ts"), *WEB_SRC.rglob("*.tsx")]):
        if ".test." in path.name or ".spec." in path.name:
            continue
        if path.relative_to(WEB_SRC).as_posix() in DISPLAY_ONLY_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        # A path starts at the opening quote (`/api/...`) or straight after an
        # interpolation (`${API_BASE_URL}/api/...`). Anchoring to a delimiter
        # matters: a bare search for "/api/" would also match prose in comments,
        # and a mention is not a call. Counting mentions as callers would let an
        # unreachable endpoint hide behind a comment describing it.
        hits = list(re.finditer(r"""(?:["'`]|\})(/api/[^"'`]*)""", text))
        for index, hit in enumerate(hits):
            shape = _normalise_frontend(hit.group(1))
            window_end = hits[index + 1].start() if index + 1 < len(hits) else len(text)
            options = text[hit.end() : window_end]
            declared = re.search(r"""method:\s*["'](\w+)["']""", options)
            method = declared.group(1).upper() if declared else "GET"
            calls.add(f"{method} {shape}")
    return calls


def _product_call_shapes() -> set[str]:
    """The same calls as bare paths, with the method dropped.

    Kept because two questions are asked of this data and they are not the same
    question. The verdict asks whether a *specific endpoint* is called, which
    needs the method. The floors ask whether the two extractors still describe
    paths the same way at all -- if the backend says `/api/policy-sets/*` and
    the client says `/api/policy-sets/$%7Bkey%7D`, both counts stay healthy
    while the sets never meet, and the verdict silently accuses everything.
    That is a question about path vocabulary, and the method would only add
    noise to it.
    """

    return {call.split(" ", 1)[1] for call in _product_calls()}


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


@pytest.mark.parametrize("module", sorted(DISPLAY_ONLY_MODULES))
def test_a_display_only_module_really_is_display_only(module: str):
    """The exclusion above is a claim, and this is what makes it checkable.

    Skipping a module is the one move in this file that can *hide* an
    unreachable endpoint, so it may not rest on a comment. A module is
    display-only when it performs no request at all; the day someone adds a
    `fetch` to the snippet builders, this fails and the declaration has to go,
    which puts its literals back in front of the verdict.
    """

    source = WEB_SRC / module
    assert source.is_file(), (
        f"{module} is declared display-only and does not exist. A skip list "
        "naming a missing file silently stops skipping anything, and nobody "
        "learns that from a passing test."
    )

    text = source.read_text(encoding="utf-8")
    performed = sorted(
        construct for construct in _REQUEST_CONSTRUCTS if re.search(construct, text)
    )
    assert not performed, (
        f"{module} is declared display-only but reaches the network: "
        f"{performed}. Its path literals are being skipped by the reachability "
        "verdict, so a real caller here would make an unreachable endpoint look "
        "reached. Remove it from DISPLAY_ONLY_MODULES."
    )


def test_a_display_only_modules_paths_are_not_counted_as_calls():
    """Positive control on the skip itself, in the direction it can fail.

    Without this, deleting the skip would be invisible: the verdict would still
    pass (the endpoint reads as reached) and only the register's expiry check
    would notice, one test further on and with a confusing message.
    """

    called = _product_call_shapes()
    assert not any(shape.startswith("/api/policy-decisions") for shape in called), (
        "A /api/policy-decisions path is being counted as a product call. Only "
        "consumeSnippets.ts mentions those paths in apps/web/src, and it renders "
        "them as examples for an external integrator rather than requesting "
        "them. If the Consume drawer now really calls the endpoint, delete the "
        "matching KNOWN_UNREACHABLE entries instead of widening this."
    )


def test_the_register_expiry_check_is_not_method_blind():
    """Control on the fix, expressed as the confusion it used to make.

    The register is keyed `METHOD /shape`. Comparing it against bare paths let
    any method on a path retire an entry recorded for a different one. Asserted
    by construction rather than against live data, so it keeps meaning when the
    product's real calls change.
    """

    endpoints = {"GET /api/example/*": "/api/example/*", "DELETE /api/example/*": "/api/example/*"}
    register = {"GET /api/example/*"}
    calls = {"DELETE /api/example/*"}

    # The method-blind reading: the GET entry "has a caller" because the DELETE
    # beside it does.
    blind = {name for name in register if endpoints[name] in {c.split(" ", 1)[1] for c in calls}}
    assert blind == {"GET /api/example/*"}

    # The reading this file now uses.
    qualified = {name for name in register if name in calls}
    assert qualified == set()


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
    called = _product_calls()

    unreachable = sorted(
        name
        for name, shape in endpoints.items()
        if name not in called
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

    WHY THE COMPARISON IS METHOD-QUALIFIED. It was not, and that made the
    register's expiry check strictly weaker than the verdict it guards. The
    register is keyed `METHOD /shape`, and the callers were compared as bare
    paths -- so `GET /api/policy-exceptions/*` would be declared "now reachable"
    on the strength of a `DELETE` to the same path, and the entry deleted while
    nothing in the product could fetch one. That is the same defect the method
    was added to `_product_calls` to fix, left behind in the one place that
    reads the register.
    """
    endpoints = _backend_endpoints()
    called = _product_calls()

    now_reachable = sorted(
        name for name in KNOWN_UNREACHABLE if name in endpoints and name in called
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
