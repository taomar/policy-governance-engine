"""A runtime asset has exactly one copy, and it lives where the code loads it from.

The prompts under `PROMPTS_DIR` are machine input. `passage_extractor.py` loads
one from disk deliberately, "so a prompt revision is a visible file change
rather than a diff buried in Python" — which is right, and which only holds
while there is one file to revise.

WHAT WENT WRONG, AND WHY A HASH PIN WOULD NOT HAVE CAUGHT IT
------------------------------------------------------------
A copy of the passage-extractor prompt sat in `docs/specs/` under a different
name. It was 32 lines shorter than the running one: it had missed both
revisions the runtime asset received, so a reader following it would have built
a system that extracts the document-control metadata the running system
deliberately rejects.

That copy is why this guard compares *content overlap* and not names or
hashes. It matched the running prompt on neither:

  * the name differed  — `verbatim-passage-extractor-v1.md` against
    `passage_extractor_v1.md`, so a filename check saw two unrelated files;
  * the bytes differed — by 1,760 of them, so an equality or digest check saw
    two unrelated files too.

An exact duplicate is untidy. A *drifted* duplicate is the hazard, and it is
precisely the case a name or digest comparison cannot see. Overlap is the
measure that notices a copy is a copy while it is drifting, which is the whole
window in which noticing helps.

A hash pinned to the version constant was the other candidate and was rejected
on purpose: it fails the build on every legitimate prompt edit until someone
updates the hash, which teaches people to update hashes without reading them.
This guard costs nothing when nobody copies a prompt, and names both files when
somebody does.

WHY THE DOCS COPY NEVER FAILED ANYTHING
---------------------------------------
`test_no_domain_specific_wording` scans `SRC` and `PROMPTS_DIR`. It does not
scan `docs/`, so the stale copy kept currency-specific wording that the runtime
prompt had already had removed, and no test could see it. Nothing imports a
document, so nothing that is wrong with one fails loudly. That is the general
shape of the fault this guard exists to close.
"""
from __future__ import annotations

import os
from pathlib import Path

from policy_platform.infrastructure.prompt_assets import PROMPTS_DIR

ROOT = Path(__file__).resolve().parents[2]

#: Directories that are not source: virtualenvs, caches, build output, and the
#: untracked scratch a run leaves behind. Copying a prompt into any of these is
#: not the mistake being guarded against.
_SKIP_DIRS = frozenset(
    {
        ".git", ".venv", ".venv-graph", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "__pycache__", "node_modules", "build", "dist", "data", ".azure", ".idea",
        ".vscode", "htmlcov", ".tox",
    }
)

#: Extensions a prompt would plausibly be pasted into. A prompt embedded in a
#: Python string literal is a different fault with a different remedy, and
#: guessing at it here would cost more in false positives than it returns.
_TEXT_SUFFIXES = frozenset({".md", ".txt", ".prompt", ".rst", ".mdx"})

#: Below this, two files are unrelated. Above it, one is a copy of the other:
#: the stale docs copy shared roughly 95% of the running prompt's lines after
#: missing two revisions, and unrelated documents in this repository share
#: almost nothing, so the threshold is not finely balanced.
_OVERLAP_THRESHOLD = 0.5

#: Short files share boilerplate — a title, a licence line — at ratios that mean
#: nothing. Compare only files long enough for overlap to be evidence.
_MIN_LINES = 20


def _significant_lines(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


def _candidate_files() -> list[Path]:
    """Every text file in the tree that is not itself a runtime asset.

    Directories are pruned during the walk rather than filtered afterwards. The
    difference is not cosmetic: descending into a virtualenv to discard what it
    contains took this check from under a second to the better part of a
    minute, and a slow guard is one somebody eventually runs with `-k`.
    """

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        here = Path(dirpath)
        if here == PROMPTS_DIR:
            continue
        for name in filenames:
            if Path(name).suffix.lower() in _TEXT_SUFFIXES:
                found.append(here / name)
    return sorted(found)


def test_a_runtime_prompt_has_no_copy_elsewhere_in_the_tree() -> None:
    # Asserted before the scan, not assumed by it. A guard that globs a
    # directory which has moved reports success having compared nothing, and
    # this repository has produced that result more than once.
    assert PROMPTS_DIR.is_dir(), f"prompt directory is missing: {PROMPTS_DIR}"
    assets = sorted(PROMPTS_DIR.glob("*.md"))
    assert assets, f"no prompt assets found in {PROMPTS_DIR}"

    candidates = _candidate_files()
    assert candidates, (
        f"no files to compare against under {ROOT}; the scan would pass without "
        f"having looked at anything"
    )

    # Read each candidate once, not once per asset.
    candidate_lines = {
        path: lines
        for path in candidates
        if len(lines := _significant_lines(path)) >= _MIN_LINES
    }

    duplicates: list[str] = []
    for asset in assets:
        asset_lines = _significant_lines(asset)
        if len(asset_lines) < _MIN_LINES:
            continue
        for candidate, lines in candidate_lines.items():
            shared = len(asset_lines & lines) / len(asset_lines)
            if shared >= _OVERLAP_THRESHOLD:
                duplicates.append(
                    f"{candidate.relative_to(ROOT).as_posix()} carries "
                    f"{shared:.0%} of the lines in the runtime asset "
                    f"{asset.relative_to(ROOT).as_posix()}"
                )

    assert not duplicates, (
        "a runtime asset has a second copy in the tree:\n  "
        + "\n  ".join(duplicates)
        + "\n\nThe copy the code loads is the only one that runs. A second copy "
        "is not documentation of the first: nothing imports it, so nothing "
        "makes it fail when it falls behind, and a reader cannot tell which of "
        "the two is current. Delete the copy and cite the runtime path instead."
    )
