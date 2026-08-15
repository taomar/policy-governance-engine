"""The readiness guard still reads the surface that wording moved onto.

Item 2 of this work moved user-facing sentences out of Python and into
TypeScript. That is exactly the move that blinds a scanner: the Python guard
keeps passing, and it keeps passing because there is less for it to find, which
reads identically to there being nothing wrong.

`test_no_readiness_framing.py` already scans `apps/web/src`, so the moved
wording is in principle covered. "In principle" is what failed here five times.
This asserts it in fact:

  * the web scan reaches the file the wording moved to, by name;
  * the scanner would catch a violation if that file contained one, proven by
    feeding it one rather than by reading the regex;
  * the Python scan has not quietly shrunk to nothing.

The floors in the guard itself are counts over the whole tree. A single file
can leave a tree-wide count untouched, so a count is not evidence about this
file.
"""
from __future__ import annotations

from pathlib import Path

from tests.unit.test_no_readiness_framing import (
    SRC,
    WEB,
    _BARE_EXECUTABILITY,
    _FRAMING_RE,
    _interface_captions,
    _string_literals,
)

#: The file Item 2's wording moved to.
MOVED_TO = WEB / "actorRole.ts"


def test_the_wording_moved_somewhere_the_web_scan_reaches():
    """The guard globs `*.ts*` under `apps/web/src`. Assert this file is in it."""

    assert MOVED_TO.exists(), f"{MOVED_TO} does not exist"

    scanned = [p for p in WEB.rglob("*.ts*") if p.is_file()]
    assert MOVED_TO in scanned, (
        f"{MOVED_TO.name} is not in the web scan's file set, so wording moved "
        "into it is unguarded"
    )
    # And the set is a real set, not one file.
    assert len(scanned) > 50, f"the web scan sees only {len(scanned)} files"


def test_the_caption_reader_finds_the_moved_sentences():
    """Presence in the file list is not coverage; the line reader must see it.

    The scanner extracts captions per line. A file it opens but reads no
    captions out of is scanned and unchecked.
    """

    captions = []
    for line in MOVED_TO.read_text(encoding="utf-8").splitlines():
        captions.extend(_interface_captions(line))

    assert captions, f"the caption reader found nothing in {MOVED_TO.name}"
    joined = " ".join(captions)
    assert "Switch your acting role in the header." in joined, (
        "the sentence that moved out of Python is not among the captions the "
        f"scanner reads from {MOVED_TO.name}; it found {captions!r}"
    )


def test_the_scanner_would_catch_a_violation_in_the_file_it_moved_to():
    """Feed it one. A regex read by eye is not a check that it fires.

    The phrasings below are the ones the product rule forbids. Neither is in
    the file; this proves that if one arrived, the guard scanning this file
    would see it rather than pass over it.
    """

    would_be_caught = 'const x = "This rule is machine-executable once mapped.";'
    captions = _interface_captions(would_be_caught)
    assert captions, "the caption reader read nothing from a line carrying a caption"
    assert any(_FRAMING_RE.search(c) for c in captions), (
        "the framing pattern did not fire on a planted violation, so its "
        "silence on the real file proves nothing"
    )

    bare = 'const y = "Executability is still pending.";'
    assert any(_BARE_EXECUTABILITY.search(c) for c in _interface_captions(bare)), (
        "the bare-noun pattern did not fire on a planted violation"
    )


def test_the_real_file_is_clean_by_both_patterns():
    """Having proven the scanner fires, its silence here means something."""

    for number, line in enumerate(MOVED_TO.read_text(encoding="utf-8").splitlines(), 1):
        for caption in _interface_captions(line):
            assert not _FRAMING_RE.search(caption), f"{MOVED_TO.name}:{number}: {caption!r}"
            assert not _BARE_EXECUTABILITY.search(caption), (
                f"{MOVED_TO.name}:{number}: {caption!r}"
            )


def test_the_python_scan_did_not_shrink_to_nothing():
    """Wording left Python; the Python scan must still have Python to read.

    Not a claim that the count is unchanged -- removing sentences is the point.
    A claim that the scan still reads a tree, so that its continued silence is
    a finding rather than an absence of input.
    """

    files = 0
    literals = 0
    for path in sorted(SRC.rglob("*.py")):
        files += 1
        literals += len(_string_literals(path))

    assert files > 100, f"the Python scan reads only {files} files"
    assert literals > 2000, f"the Python scan reads only {literals} string literals"


def test_the_router_that_lost_its_sentence_is_still_scanned():
    """The specific file wording was removed from is still in the scan's set."""

    router = SRC / "api" / "routers" / "policy_attestations.py"
    assert router in set(SRC.rglob("*.py")), f"{router} is not scanned"
    assert Path(router).exists()
