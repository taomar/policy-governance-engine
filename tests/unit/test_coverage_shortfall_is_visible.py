"""A run that did not read everything must not report itself as one that did.

INVARIANT 9 of the ingestion spec: *failures cannot silently reduce document
coverage.* The failure this guards is not missing information — the skips are
recorded — but a status field that cannot express the difference. "Completed
with 4 skips" and "completed" were the same value, so a person, a query, or a
downstream check reading `status` was told the same thing either way.

That mattered concretely. `ExtractionRun.status == "completed"` is the test for
"trustworthy enough to diff against" when a later run picks its baseline, and
the comment at that query says a partial run must be excluded because comparing
against it "would report every rule it never reached as brand new". A skipped
run is partial in exactly that sense.

Nothing here is about the policy or about the reading route. A skip is material
this system did not read; it is never a shortfall in the document, and never a
comment on records that are decided by reading.

The structural checks below deliberately key off the *skip ledger* — the list
every skip point appends to — rather than a list of known skip sites. A skip
point added later is then covered whether or not its author thought about the
run's status.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from policy_platform.domain.models import ExtractionRun
from policy_platform.infrastructure.persistence.repositories.candidates import (
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_GAPS,
    ExtractionRunRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXTRACTION = _REPO_ROOT / "src" / "policy_platform" / "infrastructure" / "extraction" / "ai_extraction.py"

# The three skip points that exist today (a batch that errored, a fabricated
# passage, a passage that could not be formulated). A floor, not a target: it is
# here so that a scan which silently matches nothing fails loudly instead of
# passing vacuously. Raise it only if skip points are genuinely added.
_MINIMUM_KNOWN_SKIP_SITES = 3


class _FakeSession:
    """Enough of an AsyncSession for the repository's flush."""

    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


def _mark_completed(*, coverage_complete: bool) -> ExtractionRun:
    run = ExtractionRun()
    repo = ExtractionRunRepository(_FakeSession())  # type: ignore[arg-type]
    asyncio.run(repo.mark_completed(run, coverage_complete=coverage_complete))
    return run


@pytest.fixture(scope="module")
def extraction_module() -> ast.Module:
    assert _EXTRACTION.is_file(), (
        f"the extraction module is not at {_EXTRACTION}. Every structural check below "
        "would pass vacuously against a file that does not exist, so this is a hard stop."
    )
    tree = ast.parse(_EXTRACTION.read_text(encoding="utf-8"))
    # Detector-still-sees: a parse that yielded nothing would let every
    # structural assertion below succeed without reading a line of real code.
    assert any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)
    ), "parsed the extraction module but found no function definitions in it"
    return tree


def _append_targets(tree: ast.Module) -> dict[str, int]:
    """Every `name.append(...)` in the module, counted by `name`."""
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
        ):
            counts[node.func.value.id] = counts.get(node.func.value.id, 0) + 1
    return counts


def _completion_call(tree: ast.Module) -> ast.Call:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "mark_completed"
        ):
            return node
    raise AssertionError(
        "no call to mark_completed found in the extraction module. Either the run is no "
        "longer closed here, or it was renamed — in both cases this guard is pointed at "
        "nothing and must not pass."
    )


def _coverage_expression(tree: ast.Module) -> ast.expr:
    """The expression the run's coverage is derived from.

    Raises an assertion naming what was expected and what was found. Reaching
    for it with `next(...)` instead would surface a bare StopIteration, which is
    red without saying why — the failure mode this suite exists to prevent.
    """
    call = _completion_call(tree)
    for keyword in call.keywords:
        if keyword.arg == "coverage_complete":
            return keyword.value
    found = sorted(k.arg for k in call.keywords if k.arg)
    raise AssertionError(
        "the run is closed without saying whether its coverage was whole. Expected a "
        f"`coverage_complete=` argument on mark_completed; got keywords {found}."
    )


# --------------------------------------------------------------------------
# The distinction itself
# --------------------------------------------------------------------------


def test_a_whole_reading_is_recorded_as_completed() -> None:
    assert _mark_completed(coverage_complete=True).status == RUN_COMPLETED


def test_a_run_that_passed_over_material_is_not_recorded_as_completed() -> None:
    status = _mark_completed(coverage_complete=False).status
    assert status != RUN_COMPLETED, (
        "a run that passed over material was recorded with the same status as one that "
        f"read everything ({status!r}). That is the whole defect: 'completed with skips' "
        "and 'completed' become the same value, and every reader of `status` is told the "
        "same thing either way."
    )
    assert status == RUN_COMPLETED_WITH_GAPS


def test_the_two_outcomes_are_distinguishable() -> None:
    """Guards against 'fixing' a failure here by collapsing the vocabulary."""
    assert RUN_COMPLETED != RUN_COMPLETED_WITH_GAPS


def test_both_outcomes_still_close_the_run() -> None:
    """A gapped run finished. It is not a failure, and it is not left open."""
    for coverage_complete in (True, False):
        run = _mark_completed(coverage_complete=coverage_complete)
        assert run.completed_at is not None


def test_coverage_is_assumed_whole_only_when_stated() -> None:
    """The default must not quietly re-open the hole for callers not yet updated."""
    run = ExtractionRun()
    repo = ExtractionRunRepository(_FakeSession())  # type: ignore[arg-type]
    asyncio.run(repo.mark_completed(run))
    assert run.status == RUN_COMPLETED


# --------------------------------------------------------------------------
# The distinction is actually fed by the skips
# --------------------------------------------------------------------------


def test_completion_derives_coverage_from_the_skip_ledger(extraction_module: ast.Module) -> None:
    expression = _coverage_expression(extraction_module)
    referenced = {n.id for n in ast.walk(expression) if isinstance(n, ast.Name)}
    assert referenced, (
        "coverage_complete is a constant expression. It has to be derived from the "
        "skips actually recorded, or it states the same thing on every run."
    )

    appended = _append_targets(extraction_module)
    ledgers = {name: appended.get(name, 0) for name in referenced}
    assert any(count >= _MINIMUM_KNOWN_SKIP_SITES for count in ledgers.values()), (
        "coverage_complete is not derived from the list the skip points append to. "
        f"Expected one of {sorted(referenced)} to be appended to at least "
        f"{_MINIMUM_KNOWN_SKIP_SITES} times; actual append counts {ledgers}. "
        "Deriving it from anything else means a skip point added later will not be counted."
    )


def test_the_skip_ledger_is_also_reported_to_the_caller(extraction_module: ast.Module) -> None:
    """The ledger driving the status must be the one the caller is shown.

    Otherwise the status could be computed from a private counter while the
    reported `skipped` list says something else.
    """
    call = _completion_call(extraction_module)
    expression = _coverage_expression(extraction_module)
    referenced = {n.id for n in ast.walk(expression) if isinstance(n, ast.Name)}
    assert call is not None

    returned: set[str] = set()
    for node in ast.walk(extraction_module):
        if isinstance(node, ast.Dict):
            for value in node.values:
                if isinstance(value, ast.Name):
                    returned.add(value.id)
    assert referenced & returned, (
        f"the coverage signal is derived from {sorted(referenced)}, none of which is "
        f"returned to the caller (returned names: {sorted(returned)}). The status and the "
        "reported skips must come from the same ledger."
    )


def test_every_skip_point_feeds_one_ledger(extraction_module: ast.Module) -> None:
    """Detector-still-sees, plus the generality claim.

    If the scan finds fewer append sites than the skip points known to exist,
    it is matching on something that has moved and is no longer watching them.
    """
    appended = _append_targets(extraction_module)
    assert appended, "found no `.append(...)` calls at all in the extraction module"
    best = max(appended.values())
    assert best >= _MINIMUM_KNOWN_SKIP_SITES, (
        f"expected at least {_MINIMUM_KNOWN_SKIP_SITES} appends to a single ledger; the "
        f"busiest list has {best} ({appended}). Either the skip points moved, or this "
        "guard has stopped seeing them."
    )


def test_the_reader_is_told_when_a_reading_was_partial(extraction_module: ast.Module) -> None:
    """The sentence shown to the reader must be conditioned on the skip ledger.

    The durable status carries the distinction for queries; this is the same
    distinction for the person watching the run.
    """
    expression = _coverage_expression(extraction_module)
    ledgers = {n.id for n in ast.walk(expression) if isinstance(n, ast.Name)}

    finishes = [
        node
        for node in ast.walk(extraction_module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "finish"
    ]
    assert finishes, "no extraction_progress.finish(...) call found to check"

    stage_names = {
        kw.value.id
        for node in finishes
        for kw in node.keywords
        if kw.arg == "stage" and isinstance(kw.value, ast.Name)
    }
    assert stage_names, (
        "no finish(...) call passes a named `stage` variable, so the sentence shown to "
        "the reader cannot be traced to the skip ledger."
    )

    conditioned = False
    for node in ast.walk(extraction_module):
        if not isinstance(node, ast.If):
            continue
        tested = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        if not tested & ledgers:
            continue
        assigned = {
            target.id
            for stmt in ast.walk(node)
            if isinstance(stmt, ast.Assign)
            for target in stmt.targets
            if isinstance(target, ast.Name)
        }
        if assigned & stage_names:
            conditioned = True
            break
    assert conditioned, (
        f"the summary shown to the reader ({sorted(stage_names)}) is never rewritten under "
        f"a branch on the skip ledger ({sorted(ledgers)}). A partial reading would be "
        "announced in the same words as a whole one."
    )


# --------------------------------------------------------------------------
# The consumer this protects
# --------------------------------------------------------------------------


def test_the_baseline_is_chosen_on_whole_coverage(extraction_module: ast.Module) -> None:
    """A gapped run must not be picked as the trustworthy reference to diff against."""
    literals: list[str] = []
    for node in ast.walk(extraction_module):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (
            isinstance(left, ast.Attribute)
            and left.attr == "status"
            and isinstance(left.value, ast.Name)
            and left.value.id == "ExtractionRun"
        ):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                literals.append(comparator.value)

    assert literals, (
        "no `ExtractionRun.status == <literal>` comparison found. This guard exists to "
        "hold the baseline query to whole-coverage runs; if that query moved, the guard "
        "is watching nothing."
    )
    assert RUN_COMPLETED_WITH_GAPS not in literals, (
        f"the baseline query accepts {RUN_COMPLETED_WITH_GAPS!r} ({literals}). Diffing "
        "against a run that did not read the whole document reports the rules it never "
        "reached as new, and the rules a later run misses as 'no longer found' — a claim "
        "about the document made on the strength of extraction coverage."
    )
    assert all(literal == RUN_COMPLETED for literal in literals), (
        f"the baseline query compares status against {literals}, which is not the "
        f"whole-coverage status {RUN_COMPLETED!r}."
    )
