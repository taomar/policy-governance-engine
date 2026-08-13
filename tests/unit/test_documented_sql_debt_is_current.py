"""The documented count of SQL-in-routers must equal the real one.

`docs/known-limitations.md` records how far the repository layer's premise
falls short: a number of `session.execute` calls, in a number of files, broken
down per file. It was accurate the day it was written, and nothing made it stay
that way.

That is the defect this branch spent its time deleting, in miniature. A comment
promised cross-reference edges extraction never discovered; two documents
described a `worker/` package that never existed; the packaging config implied
prompts that never shipped. Each was believed because it was written down, and
each survived a green suite. A hand-counted number in a limitations document is
the same shape: it decays silently, and the reader who most needs it -- someone
deciding whether to add one more query to a router -- is the least able to tell.

So this does not pin the number. It pins the *agreement* between the document
and the code. Adding a query to a router is allowed; letting the document
disagree about it is not. The friction is the point: the file itself observes
that each of these looked small on its own, which is exactly why the pattern
spread. A failing test turns the eighteenth one into a decision somebody makes
rather than a drift nobody notices.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIMITATIONS = REPO_ROOT / "docs" / "known-limitations.md"
API_ROOT = REPO_ROOT / "src" / "policy_platform" / "api"

#: The sentence under test, e.g. "**17** `session.execute` calls remain across
#: **6** files under `api/`".
_HEADLINE_RE = re.compile(
    r"\*\*(?P<calls>\d+)\*\*\s*`session\.execute`\s*calls remain across\s*\*\*(?P<files>\d+)\*\*\s*files",
    re.IGNORECASE,
)

#: The per-file breakdown, e.g. "`ai.py` (6)".
_BREAKDOWN_RE = re.compile(r"`(?P<name>[A-Za-z0-9_]+\.py)`\s*\((?P<count>\d+)\)")


def _measured() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in sorted(API_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found = path.read_text(encoding="utf-8").count("session.execute")
        if found:
            counts[path.name] += found
    return counts


def _documented_section() -> str:
    text = LIMITATIONS.read_text(encoding="utf-8")
    match = _HEADLINE_RE.search(text)
    assert match, (
        "the 'Routers issue SQL directly' claim is no longer in the expected form. "
        "If the limitation was resolved, delete this test with it; if it was only "
        "reworded, this test is now checking nothing."
    )
    # the breakdown follows the headline on the next line or two
    start = match.start()
    return text[start : start + 400]


def test_the_documented_totals_match_the_code() -> None:
    section = _documented_section()
    match = _HEADLINE_RE.search(section)
    assert match

    measured = _measured()
    assert measured, "no session.execute calls found under api/ -- has the tree moved?"

    stated_calls = int(match.group("calls"))
    stated_files = int(match.group("files"))

    assert stated_calls == sum(measured.values()), (
        f"known-limitations.md says {stated_calls} session.execute calls under api/, "
        f"the code has {sum(measured.values())}. Update the document, or remove the "
        f"query you just added from the router."
    )
    assert stated_files == len(measured), (
        f"known-limitations.md says {stated_files} files, the code has {len(measured)}: "
        f"{sorted(measured)}"
    )


def test_the_documented_breakdown_matches_the_code() -> None:
    """The per-file figures, not just the totals.

    Totals alone can agree while the detail is wrong -- one call moving from
    `ai.py` to `documents.py` leaves 17 across 6 and makes both lines false.
    """

    documented = {
        m.group("name"): int(m.group("count"))
        for m in _BREAKDOWN_RE.finditer(_documented_section())
    }
    assert documented, "the per-file breakdown is no longer parseable from the document"

    measured = _measured()
    assert documented == dict(measured), (
        f"per-file counts disagree.\n  documented: {dict(sorted(documented.items()))}"
        f"\n  measured:   {dict(sorted(measured.items()))}"
    )


def test_the_patterns_can_actually_fail() -> None:
    """Both regexes must reject text that does not state what they claim to read.

    A regex that matches nothing makes every assertion above vacuous: the
    dictionaries would be empty, compare equal, and pass.
    """

    assert _HEADLINE_RE.search("**17** `session.execute` calls remain across **6** files")
    assert not _HEADLINE_RE.search("some `session.execute` calls remain in a few files")
    assert not _HEADLINE_RE.search("**17** `session.commit` calls remain across **6** files")

    assert _BREAKDOWN_RE.findall("`ai.py` (6), `documents.py` (5)") == [
        ("ai.py", "6"),
        ("documents.py", "5"),
    ]
    assert not _BREAKDOWN_RE.findall("`ai.py` and `documents.py`")
