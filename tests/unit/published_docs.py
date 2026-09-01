"""Which documents this repository actually publishes.

One definition, because there were three, and they disagreed.

Several documentation guards need to scan *published* pages and only those: a
guard about what a reader is told has no business reading material no reader can
reach. Each guard answered "which pages are published?" for itself, and each
answered it by naming a path -- `docs/internal/`. That was a stand-in for the
real boundary, and an incomplete one. The publication boundary is `.gitignore`,
which also excludes `docs/adr/`, `docs/failures/`, `docs/handoff/` and several
loose files beside them.

The consequence was the exact failure mode `test_no_readiness_framing` already
warns about in its own comments: the guards became **a property of whichever
machine ran them**. On CI, and in any fresh clone, the private tree is absent, so
the guards passed. On a checkout that had preserved that material -- which is the
supported state, and the one a handover explicitly asks for -- the same guards
failed on identical published content, reporting private history as a defect in
the product documentation.

So the boundary is asked of git rather than restated here. `git check-ignore` is
the same mechanism `test_publication_excludes_private_material` uses, for the
same reason: a reimplementation of `.gitignore` semantics is a second source of
truth that drifts.

Only *ignored* documents are excluded. A document that is merely untracked --
a new page someone has written but not yet added -- is still scanned, so adding
a page cannot quietly opt it out of the guards.
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def _candidates() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


@lru_cache(maxsize=1)
def ignored_documents() -> frozenset[Path]:
    """Resolved paths of every document under `docs/` that git does not publish.

    Returns an empty set when git cannot answer -- no repository, no git binary,
    an unexpected exit. Failing open matters: a guard that silently scanned
    nothing because a subprocess broke would report success while checking
    nothing at all, which is worse than scanning a little private material.
    """

    candidates = _candidates()
    if not candidates:
        return frozenset()

    # `-z` is not a detail. Without it git C-quotes any path it considers
    # special -- which includes every path under a directory whose name has a
    # space -- and returns `"C:\\...\\file.md"` rather than the path itself, so
    # nothing matches and every private document is silently treated as
    # published. Byte I/O for the same reason: text mode on Windows rewrites the
    # separator on the way in and git then reads a trailing carriage return as
    # part of the filename.
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            input=b"\0".join(os.fsencode(str(path)) for path in candidates),
            capture_output=True,
            cwd=ROOT,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()

    # 0 = some paths are ignored, 1 = none are. Anything else is an error, and
    # an error must not be read as "nothing is private".
    if completed.returncode not in (0, 1):
        return frozenset()

    resolved: set[Path] = set()
    for chunk in completed.stdout.split(b"\0"):
        if not chunk:
            continue
        path = Path(os.fsdecode(chunk))
        resolved.add((path if path.is_absolute() else ROOT / path).resolve())
    return frozenset(resolved)


def published_documents() -> list[Path]:
    """Every published document under `docs/`, in a stable order."""

    ignored = ignored_documents()
    return [path for path in _candidates() if path.resolve() not in ignored]
