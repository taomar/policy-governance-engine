"""A run that did not read everything must not report itself as one that did.

INVARIANT 9 of the ingestion spec: *failures cannot silently reduce document
coverage.* The failure this guards is not missing information — the skips are
recorded — but a status field that cannot express the difference. "Completed
with 4 skips" and "completed" were the same value, so a person, a query, or a
downstream check reading `status` was told the same thing either way.

That mattered concretely, though not in the way first supposed. The baseline
query used `status == "completed"` as its test for "trustworthy enough to diff
against", excluding a partial run because comparing against it "would report
every rule it never reached as brand new". That reasoning was right about the
risk and wrong about the remedy: skipping the most recent run reached back to an
older one built by different code, and the delta then reported our own changes
as the document's. A gapped run is now chosen and its gap declared — see
`test_a_gapped_baseline_is_declared_rather_than_avoided`. The status must still
express the difference, which is what this file guards.

Nothing here is about the policy or about the reading route. A skip is material
this system did not read; it is never a shortfall in the document, and never a
comment on records that are AI Ready.

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
from policy_platform.infrastructure.extraction.ai_extraction import (
    _UNUSABLE_BASELINE_STATUSES,
    _comparison_caveats,
)
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
    """Every write to a list-valued name in the module, counted by name.

    Counts two shapes, because a ledger is written to in two ways:

      `name.append(...)`   — a bare list
      `record_skip(name,)` — the skip ledger, which records one entry per
                             declined passage rather than per rejection event
                             and so cannot be a plain append

    Counting only `.append` would read the second shape as zero writes and
    report a derived `coverage_complete` as constant, which is what this guard
    exists to catch — so it would fail on a correct implementation and, worse,
    could be silenced by weakening the assertion rather than by teaching it the
    call. The intent is unchanged: coverage must be derived from the list the
    skip sites actually write to.
    """
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target: str | None = None
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
        ):
            target = node.func.value.id
        elif (
            isinstance(node.func, ast.Name)
            and node.func.id == "record_skip"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            target = node.args[0].id
        if target is not None:
            counts[target] = counts.get(target, 0) + 1
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


def _assignments(tree: ast.Module) -> dict[str, set[str]]:
    """For each assigned name, the names its value was built from."""
    sources: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        for target in node.targets:
            if isinstance(target, ast.Name):
                sources.setdefault(target.id, set()).update(names)
    return sources


def _coverage_ledgers(tree: ast.Module) -> set[str]:
    """Every name the coverage signal is built from, following derivations.

    Resolved transitively rather than one hop, because the signal is legitimately
    derived: coverage is not "were there skips" but "were any of them the kind
    that means we never read the material", so the expression names a filtered
    list and that list names the ledger. A one-hop reading calls that
    indirection a broken derivation.

    Following assignments makes this guard strictly harder to defeat, not
    easier. A coverage signal laundered through any number of intermediate
    variables still has to bottom out in the list the skip points append to, and
    a signal that does not — a flag set by hand, a counter kept separately —
    still fails, because nothing in its chain is ever appended to.
    """
    names = {n.id for n in ast.walk(_coverage_expression(tree)) if isinstance(n, ast.Name)}
    sources = _assignments(tree)
    seen: set[str] = set()
    while names - seen:
        seen |= names
        names = names | {source for name in seen for source in sources.get(name, set())}
    return seen


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
    referenced = _coverage_ledgers(extraction_module)
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
    referenced = _coverage_ledgers(extraction_module)
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
    ledgers = _coverage_ledgers(extraction_module)

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


def test_a_gapped_baseline_is_declared_rather_than_avoided() -> None:
    """Diffing against a partial reading is allowed; doing it quietly is not.

    This assertion used to be the opposite: the baseline query required
    `status == "completed"`, so a run with one unread batch was passed over
    entirely. The reasoning was sound — rules the baseline never reached surface
    as new — but the cure was worse than the disease. Skipping the immediately
    preceding run reached back to whatever came before it, which on the run that
    prompted this change was two model generations and five commits earlier, and
    the delta then reported the difference between two versions of *this system*
    as though the handbook had been rewritten. Measured, the wrong baseline
    reported far fewer rules as unchanged than the gapped-but-recent one.

    So recency wins and the gap is declared instead. The original concern is
    still honoured — a reader is told the comparison cannot distinguish "new"
    from "in the part the baseline never read" — but it is honoured by saying
    so rather than by silently comparing against something older and less
    comparable.
    """

    baseline = ExtractionRun(
        status=RUN_COMPLETED_WITH_GAPS,
        deployment_name="d",
        prompt_version="p",
        parser_version="v",
        skipped_json=[{"kind": "batch_unread", "identity": "batch:x", "reason": "boom"}],
    )
    current = ExtractionRun(
        status=RUN_COMPLETED, deployment_name="d", prompt_version="p", parser_version="v"
    )

    caveats = _comparison_caveats(current, baseline)

    assert caveats, (
        "a baseline that never read part of the document produced no caveat. The delta "
        "would then report rules from unread material as new, which is a claim about the "
        "document made on the strength of how much of it the previous run reached."
    )
    assert any("did not read" in caveat for caveat in caveats), (
        f"the caveats {caveats} do not say that material went unread, so a reader cannot "
        "tell why the comparison is limited."
    )


def test_a_whole_coverage_baseline_on_the_same_code_needs_no_caveat() -> None:
    """The positive control: the warning must stay rare enough to be worth reading.

    A caveat on every run is a caveat on none. If this ever fails, the check
    above has started firing on healthy comparisons and will be ignored exactly
    when it matters.
    """

    fields = {"deployment_name": "d", "prompt_version": "p", "parser_version": "v"}
    baseline = ExtractionRun(status=RUN_COMPLETED, skipped_json=[], **fields)
    current = ExtractionRun(status=RUN_COMPLETED, **fields)

    assert _comparison_caveats(current, baseline) == (), (
        "a like-for-like comparison against a whole reading was flagged as untrustworthy."
    )


def test_a_baseline_built_by_different_code_is_flagged() -> None:
    """Comparing across versions measures us, not the document.

    Every run records the deployment, prompt and parser that made it, and until
    this existed nothing read them back. A deliberate change to how rules are
    merged, shipped between two extractions, was read as the model being
    unstable — the delta had no way to say "some of this difference is ours".
    """

    for field in ("deployment_name", "prompt_version", "parser_version"):
        same = {"deployment_name": "d", "prompt_version": "p", "parser_version": "v"}
        baseline = ExtractionRun(status=RUN_COMPLETED, skipped_json=[], **same)
        current = ExtractionRun(status=RUN_COMPLETED, **{**same, field: "different"})

        caveats = _comparison_caveats(current, baseline)

        assert caveats, (
            f"a baseline whose {field} differs from this run's produced no caveat, so a "
            "change in this system is reported as a change in the policy."
        )


def test_an_abandoned_run_is_still_refused_as_a_baseline() -> None:
    """Relaxing the status filter must not have relaxed it all the way.

    A gapped run finished and knows what it missed. A failed or still-running
    one stopped somewhere unrecorded and holds whatever it had committed at that
    moment, so everything it never reached would be reported as new with nothing
    to warn the reader. That distinction is the whole reason this is a denylist
    of abandoned states rather than an allowlist of good ones.
    """

    assert RUN_COMPLETED_WITH_GAPS not in _UNUSABLE_BASELINE_STATUSES, (
        "a finished-but-partial run is refused as a baseline again, which sends the "
        "comparison back to an older and less comparable run."
    )
    assert RUN_COMPLETED not in _UNUSABLE_BASELINE_STATUSES
    assert "failed" in _UNUSABLE_BASELINE_STATUSES, (
        "a failed run can be chosen as a baseline. It stopped at an unrecorded point, so "
        "every rule it never reached would be reported as new."
    )
    assert "running" in _UNUSABLE_BASELINE_STATUSES, (
        "a run still in flight can be chosen as a baseline; it is comparing against a "
        "moving target."
    )
