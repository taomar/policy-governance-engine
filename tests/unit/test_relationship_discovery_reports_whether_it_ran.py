"""Relationship discovery records whether it ran, so `linked: 0` is not ambiguous.

Twice in one day a caught-and-logged exception left the discovery pass producing
zero links while the strip reported a plain ``0 Linked`` -- a true number for a
false reason. The reader could not tell "the document established no cross-rule
relationships" from "discovery crashed before it could find any". Those are
different facts (constraint 5), and a surface that renders both as the same 0 is
the §4.1 shape this whole session has been unpicking.

The fix gives the run a per-tier record, ``relationship_discovery``, on the same
ephemeral strip surface that already carries ``linked``. A tier appears there
only once *attempted*, with value ``"ok"`` (finished, nothing swallowed) or
``"failed"`` (its guard caught something). An absent key is the third state,
"not reached". So a ``linked`` of 0 under an all-``"ok"`` record is trustworthy,
while the same 0 under a ``"failed"`` record is a floor.

Every expectation here is a relationship over what the test itself set up -- a
record it started, a window it built whose client it made fail -- never a count
copied from a real run (constraint 1). The model-tier check drives the *real*
``discover_continuations`` with a client that raises, so the window's failure
travels the actual per-window guard rather than being asserted into place; and
because ``extract_candidate_rules`` needs a database and live agents it cannot be
unit-run, the wiring that reports each tier is pinned on the parsed source, so a
regression that drops a ``note_discovery`` -- returning the surface to a silent 0
on failure, the exact bug this feature ends -- fails here, not only in a live run.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from policy_platform.infrastructure.extraction import ai_extraction, extraction_progress
from policy_platform.infrastructure.extraction.continuation_adjudicator import (
    ClauseWindow,
    discover_continuations,
)

_AI_EXTRACTION_SOURCE = Path(ai_extraction.__file__).read_text(encoding="utf-8")

_SETTINGS = SimpleNamespace(azure_openai_deployment="test-deployment")

# A governing stem (non-terminal ":") over one enumerated case. `should_adjudicate`
# returns True for this window, so `discover_continuations` actually calls the
# model over it rather than skipping it -- that is what puts the failure path
# below under test instead of a path that is never entered (this repo's §4.1).
_PARENT = ClauseWindow(
    element_id="e1",
    rule_id="r1",
    text="Salary shall be increased in one of the following cases only:",
)
_CHILD = ClauseWindow(
    element_id="e2",
    rule_id="r2",
    text="Completion of one full year of continuous service.",
)


def teardown_function() -> None:
    extraction_progress.clear()


def _started(key: str) -> None:
    extraction_progress.start(key, total_clauses=1, total_batches=1, total_pages=1)


# ---- note_discovery: the record it writes ----------------------------------


def test_note_discovery_records_each_attempted_tier_as_ok_or_failed() -> None:
    _started("doc-both")
    extraction_progress.note_discovery("doc-both", tier="deterministic", ok=True)
    extraction_progress.note_discovery("doc-both", tier="model", ok=False)
    record = extraction_progress.get("doc-both")
    assert record["relationship_discovery"] == {
        "deterministic": "ok",
        "model": "failed",
    }


def test_the_discovery_record_is_empty_until_the_pass_runs() -> None:
    _started("doc-fresh")
    record = extraction_progress.get("doc-fresh")
    # Empty, not {"deterministic": "ok"}: before the pass runs there is no
    # outcome, and an empty record must not read as "ran and found none".
    assert record["relationship_discovery"] == {}


def test_an_unattempted_tier_stays_absent_rather_than_failed() -> None:
    _started("doc-no-model")
    # The deterministic tier ran; the model tier was never attempted (no model
    # configured). It must stay absent -- "not reached" -- not be recorded as a
    # failure it did not have.
    extraction_progress.note_discovery("doc-no-model", tier="deterministic", ok=True)
    record = extraction_progress.get("doc-no-model")
    assert record["relationship_discovery"] == {"deterministic": "ok"}
    assert "model" not in record["relationship_discovery"]


def test_note_discovery_is_total_on_an_unknown_run() -> None:
    # The module's invariant: a reporting call never raises and never invents a
    # record. Its caller wraps nothing, so it must be safe on a run it does not
    # know.
    extraction_progress.note_discovery("never-started", tier="model", ok=False)
    assert extraction_progress.get("never-started") is None


# ---- constraint 5: a crash and a genuine zero read differently --------------


def test_a_crashed_pass_and_a_genuine_zero_read_differently_at_equal_linked() -> None:
    _started("doc-genuine-zero")
    # Both tiers ran and found nothing: linked stays 0 honestly.
    extraction_progress.note_discovery("doc-genuine-zero", tier="deterministic", ok=True)
    extraction_progress.note_discovery("doc-genuine-zero", tier="model", ok=True)
    genuine = extraction_progress.get("doc-genuine-zero")

    _started("doc-crashed")
    # The deterministic guard caught an exception: linked is 0 only because the
    # pass never got far enough to find anything.
    extraction_progress.note_discovery("doc-crashed", tier="deterministic", ok=False)
    crashed = extraction_progress.get("doc-crashed")

    # The linked count alone cannot separate these two runs ...
    assert genuine["linked"] == crashed["linked"] == 0
    # ... but the discovery record must: one is all-"ok" (the 0 is trustworthy),
    # the other names a failed tier (the 0 is a floor). This is the constraint-5
    # distinction the strip needs to stop drawing a crash as a confirmed zero.
    assert all(v == "ok" for v in genuine["relationship_discovery"].values())
    assert "failed" in crashed["relationship_discovery"].values()
    assert genuine["relationship_discovery"] != crashed["relationship_discovery"]


# ---- the model tier degrading is a value the tier returns, not just a log ----


class _ClientThatFailsEveryWindow:
    """A client whose ``chat`` raises, as a DNS blip or a dead deployment would.

    The signature mirrors the real ``AzureOpenAIClient.chat`` exactly -- keyword
    only, no ``**kwargs`` -- so an argument the adjudicator gets wrong would be a
    ``TypeError`` here just as it would in production, rather than being absorbed
    by a permissive fake. That is what makes ``windows_failed`` below evidence
    about the real call, not about the stub.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages: list[dict],
        *,
        deployment: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 1500,
        temperature: float | None = None,
        seed: int | None = None,
        timeout: float = 120.0,
        reasoning_effort: str | None = None,
    ) -> str:
        self.calls += 1
        raise RuntimeError("passage extractor was unreachable")


async def test_discover_continuations_returns_the_count_of_windows_it_lost() -> None:
    client = _ClientThatFailsEveryWindow()
    edges, windows_failed = await discover_continuations(
        client, _SETTINGS, [_PARENT, _CHILD], resolved_element_ids=set()
    )
    # The window was actually adjudicated -- the client was called -- so the
    # per-window failure path under test was entered, not skipped.
    assert client.calls == 1
    # The per-window guard caught the failure and yielded no edges ...
    assert edges == []
    # ... but did not swallow it into silence: the tier returns that one window
    # was lost, which is the only signal that lets the caller mark the model
    # tier degraded (ok=False) rather than clean. Drop the counter and this is 0.
    assert windows_failed == 1


# ---- the wiring `extract_candidate_rules` cannot be unit-run to prove --------


def _module() -> ast.Module:
    tree = ast.parse(_AI_EXTRACTION_SOURCE)
    # Detector-still-sees: an empty parse would pass every structural check below.
    assert any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    ), "parsed the extraction module but found no functions in it"
    return tree


def _extract_fn(tree: ast.Module) -> ast.AST:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "extract_candidate_rules"
        ):
            return node
    raise AssertionError("extract_candidate_rules is not defined in the extraction module")


def _handler_logs(handler: ast.ExceptHandler, needle: str) -> bool:
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exception"
        ):
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and needle in arg.value
                ):
                    return True
    return False


def _try_for(fn: ast.AST, needle: str) -> ast.Try:
    for node in ast.walk(fn):
        if isinstance(node, ast.Try) and any(
            _handler_logs(h, needle) for h in node.handlers
        ):
            return node
    raise AssertionError(
        f"no try/except in extract_candidate_rules logs {needle!r}, so the block "
        "that owns that failure cannot be found to check it records its outcome."
    )


def _note_calls(nodes: list[ast.AST]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in nodes:
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "note_discovery"
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id == "extraction_progress"
            ):
                calls.append(inner)
    return calls


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _tier_of(call: ast.Call) -> str | None:
    value = _kw(call, "tier")
    return value.value if isinstance(value, ast.Constant) else None


def _ok_is(call: ast.Call, expected: bool) -> bool:
    value = _kw(call, "ok")
    return isinstance(value, ast.Constant) and value.value is expected


def _mentions_windows_failed(node: ast.AST) -> bool:
    return any(
        isinstance(inner, ast.Name) and inner.id == "windows_failed"
        for inner in ast.walk(node)
    )


class TestTheDiscoveryBlocksRecordTheirOutcome:
    """``extract_candidate_rules`` needs a database and live agents, so it cannot
    run here; the wiring that makes each tier report itself is pinned on the
    parsed source. A regression that drops a ``note_discovery`` -- returning a
    crashed tier to a silent 0 -- fails here rather than only on a real run.
    """

    def test_the_deterministic_failure_is_recorded_in_its_own_handler(self) -> None:
        block = _try_for(_extract_fn(_module()), "relationship discovery failed")
        handler_calls = _note_calls(list(block.handlers))
        assert any(
            _tier_of(c) == "deterministic" and _ok_is(c, False) for c in handler_calls
        ), (
            'the deterministic except does not record note_discovery(tier="deterministic", '
            "ok=False); a crash there would leave linked=0 reading as a confirmed zero."
        )

    def test_the_deterministic_success_is_recorded_in_the_try_body(self) -> None:
        block = _try_for(_extract_fn(_module()), "relationship discovery failed")
        body_calls = _note_calls(list(block.body))
        assert any(
            _tier_of(c) == "deterministic" and _ok_is(c, True) for c in body_calls
        ), (
            'the deterministic try body does not record note_discovery(tier="deterministic", '
            'ok=True); without it a tier that ran clean stays absent, reading as "not reached".'
        )

    def test_the_model_failure_is_recorded_in_its_own_handler(self) -> None:
        block = _try_for(_extract_fn(_module()), "continuation adjudication failed")
        handler_calls = _note_calls(list(block.handlers))
        assert any(
            _tier_of(c) == "model" and _ok_is(c, False) for c in handler_calls
        ), 'the model except does not record note_discovery(tier="model", ok=False).'

    def test_the_model_success_is_computed_from_windows_failed(self) -> None:
        block = _try_for(_extract_fn(_module()), "continuation adjudication failed")
        model_success = [c for c in _note_calls(list(block.body)) if _tier_of(c) == "model"]
        assert model_success, "the model try body does not record its outcome at all."
        # ok= must be derived from windows_failed, not a bare True: a tier that
        # lost windows inside its own per-window guard would otherwise report
        # clean -- the §4.5 trap of watching the block-level except while the
        # real failure is swallowed one level down.
        assert any(
            isinstance(ok, ast.Compare)
            and any(isinstance(op, ast.Eq) for op in ok.ops)
            and _mentions_windows_failed(ok)
            for ok in (_kw(c, "ok") for c in model_success)
        ), (
            "the model tier's ok= is not derived from windows_failed; a per-window "
            "failure the adjudicator swallows would then be reported as a clean tier."
        )

    def test_the_run_unpacks_windows_failed_from_discover_continuations(self) -> None:
        fn = _extract_fn(_module())
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            value = node.value.value if isinstance(node.value, ast.Await) else node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "discover_continuations"
            ):
                target = node.targets[0]
                assert isinstance(target, ast.Tuple) and len(target.elts) == 2, (
                    "discover_continuations' result is not unpacked into two names; the "
                    "windows-lost count it returns is being dropped at the call site."
                )
                names = [e.id for e in target.elts if isinstance(e, ast.Name)]
                assert "windows_failed" in names, (
                    "the second value of discover_continuations is not bound to "
                    "windows_failed, so the count the tier returns is not the one read."
                )
                return
        raise AssertionError(
            "nothing in extract_candidate_rules calls discover_continuations."
        )
