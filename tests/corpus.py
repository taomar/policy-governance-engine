"""Locating the documents a test examines, and refusing to be quiet about it.

Two different faults have hidden here, and they need separating.

The first is where a test looks. `data/documents/` is the upload directory: it
is gitignored, and every file in it carries the upload's UUID as a prefix. A
test that pins the whole filename therefore stops resolving the moment the
document is re-uploaded -- the document is still present, under a new prefix,
and the test never notices. `samples/source-documents/` is tracked, and a
document there resolves in every checkout for as long as the repository lives.
Prefer it. Reach for the upload directory only for a document that cannot be
committed.

The second is what a test does when the document is absent. `pytest.skip`
renders as a pass in the only line most people read, so a fixture that has
gone missing announces nothing while the behaviour it guarded goes unchecked.
That is the same shape as `empty_parameter_set_mark = fail_at_collect` in
`pyproject.toml`, which this repository already set for exactly this reason on
`parametrize`; it simply was never applied to fixture-gated tests.

So absence fails here. A skip that means "this environment cannot run this"
is legitimate -- an optional dependency, a platform difference -- and belongs
in a `skipif` on the thing that is genuinely optional. A skip that means "the
thing I was going to examine is not here" is a silence, and this module will
not produce one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

#: Committed documents. Stable names, resolvable in any checkout.
TRACKED = _ROOT / "samples" / "source-documents"

#: Uploaded documents. Gitignored, and prefixed with the upload's UUID, so a
#: name here is only stable from the human-readable tail onwards.
UPLOADS = _ROOT / "data" / "documents"


def tracked_document(name: str) -> Path:
    """A document committed to the repository, by its exact name."""

    path = TRACKED / name
    if not path.is_file():
        pytest.fail(
            f"the tracked fixture {name!r} is missing from {TRACKED}. This is a "
            "committed file, so its absence means the checkout is damaged rather "
            "than merely unprovisioned -- which is not something to skip past."
        )
    return path


def uploaded_document(stable_suffix: str) -> Path:
    """An uploaded document, found by the part of its name that does not drift.

    Files in the upload directory are named `<uuid>_v<n>_<original name>`, and
    re-uploading the same document changes the prefix. Matching on the tail
    survives that; matching on the whole name is what stopped these tests from
    running in the first place.

    Where several uploads of the same document are present the earliest by name
    is chosen, so the choice is at least deterministic between runs.
    """

    if not UPLOADS.is_dir():
        pytest.fail(
            f"the upload directory {UPLOADS} does not exist, so a scan of it "
            "would examine nothing and report nothing wrong. Those are not the "
            "same result and must not render identically."
        )
    matches = sorted(p for p in UPLOADS.glob(f"*{stable_suffix}") if p.is_file())
    if not matches:
        available = sorted(p.name for p in UPLOADS.iterdir() if p.is_file())
        pytest.fail(
            f"no uploaded document ends with {stable_suffix!r} in {UPLOADS}. "
            "This test cannot be skipped quietly: with no document there is "
            "nothing to examine, and a silent skip reads exactly like a pass. "
            f"Present instead: {available or 'nothing at all'}."
        )
    return matches[0]
