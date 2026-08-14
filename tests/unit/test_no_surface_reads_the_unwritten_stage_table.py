"""A reviewer-facing surface must not be fed by a table nothing writes.

WHAT WENT WRONG
---------------
`extraction_stages` had a migration, an ORM model, a repository, an API
endpoint and a "Run stages" tab in the extraction drawer. Every layer existed.
Nothing in `src/` ever called `ExtractionStageRepository.record`, so the table
held no rows: measured live, 11 extraction runs and 0 stages. The tab could
only ever render its empty state, and it showed a nine-stage model of a
pipeline that actually runs 24 steps.

That is worse than no surface. A reader who opens "Run stages" and sees
nothing concludes something about the run. What they are actually seeing is a
fact about the writer that was never built.

WHAT THIS GUARD ASSERTS
-----------------------
Not "stages may never be shown" -- that would be over-reach, and would block a
legitimate re-introduction. It asserts the *pairing*: while nothing writes the
table, nothing in the web app may read it. Wire up a writer and this guard
stands down on its own and says so.

WHERE THE FLOOR GOES, AND WHY IT IS LAST HERE
---------------------------------------------
The verdict is an offender list: collect web references to the dead surface,
assert the list is empty. A scan that goes blind -- wrong root, wrong glob,
renamed directory -- collects nothing, and an empty offender list *passes*.
Vacuously. So the floors go LAST, after the verdict, where they can catch a
pass that was earned by seeing nothing.

(The opposite rule applies to a set-difference verdict, where a blind scan does
not go quiet: it accuses every item and produces a precise, confident, entirely
wrong bug report against the interface when the fault is in the test. Those
need the floor FIRST. This one is not that shape.)

This scan has two independent ways to go blind, so there is a floor for each:
  1. it reads no files at all              -> the file-count floor
  2. it reads files but matches nothing    -> the positive-control floor,
     which looks for a live sibling accessor that is definitely present
A count floor alone would not catch (2): a scan pointed at the right directory
with a broken matcher reads hundreds of files and still sees nothing.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"
BACKEND_SRC = REPO_ROOT / "src"

#: Identifiers that exist only to carry the persisted-stage surface.
#:
#: Deliberately NOT the bare word "stage". `ExtractionProgressPanel.tsx` shows
#: live progress through named phases from a different endpoint and a different
#: table; it is a working surface and must not be caught here.
_DEAD_SURFACE_TOKENS = (
    "getStages",
    "ExtractionStagesResponse",
    "ExtractionStageRecord",
    "/stages",
)

#: Present in the same client object as the removed accessor. If the scan
#: cannot find this, the scan is broken -- not the code under test.
_POSITIVE_CONTROL = "getCoverage"


def _web_files() -> list[Path]:
    return sorted(p for p in WEB_SRC.rglob("*.ts*") if p.is_file())


def _writes_stages() -> list[str]:
    """Files under `src/` that record a stage row.

    A writer both names the repository and calls `.record(`. The repository's
    own definition is `async def record(` and so does not match, and the API
    router only calls `.list_for_run(`.
    """
    writers = []
    for path in BACKEND_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "ExtractionStageRepository" in text and ".record(" in text:
            writers.append(str(path.relative_to(REPO_ROOT)))
    return sorted(writers)


def test_no_web_file_reads_the_stage_surface_while_nothing_writes_it() -> None:
    files = _web_files()
    writers = _writes_stages()

    offenders: list[str] = []
    control_seen = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _POSITIVE_CONTROL in text:
            control_seen += 1
        for token in _DEAD_SURFACE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")

    if writers:
        # Someone built the writer. Reading the table is now honest, and this
        # guard has done its job and should be deleted along with this branch.
        assert offenders, (
            "Stages are now written by "
            + ", ".join(writers)
            + " but no web file reads them. If that is deliberate, delete this test."
        )
    else:
        assert not offenders, (
            "The web app reads the persisted-stage surface, but nothing in src/ "
            "writes a stage row, so the table is empty and the surface can only "
            "mislead:\n  " + "\n  ".join(sorted(offenders))
        )

    # --- Floors LAST. See the module docstring for why. ---
    assert len(files) > 50, (
        f"Only {len(files)} web source files scanned. The scan is blind and the "
        "verdict above was reached by reading almost nothing."
    )
    assert control_seen > 0, (
        f"The control token {_POSITIVE_CONTROL!r} was not found in any of "
        f"{len(files)} files. The scan read files but matched nothing, so an "
        "empty offender list above proves nothing about the code."
    )
