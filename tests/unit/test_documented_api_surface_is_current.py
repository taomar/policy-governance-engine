"""The documented API surface must match the application's actual routes.

`docs/api.md` states a path count, an operation count, a tag count and a table
with per-tag operation counts. Every one of those was wrong when checked: the
page claimed 73 paths / 84 operations across 11 tags against a real 78 / 89 / 12,
and omitted the entire `extraction` tag -- five endpoints that answer "why was
this clause not extracted?", undiscoverable to anyone reading the page.

Nothing had made it stay true. This is the same defect as a hand-counted number
in a limitations document: it decays silently, and a reader has no way to tell.

The check runs against the app object rather than a live server, so it needs no
port and no database.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from policy_platform.api.app import create_app

from tests.unit.published_docs import published_documents

ROOT = Path(__file__).resolve().parents[2]
API_DOC = ROOT / "docs" / "api.md"

_HEADLINE_RE = re.compile(
    r"\*\*(?P<paths>\d+) paths / (?P<ops>\d+) operations\*\* across (?P<tags>\d+) tags"
)
#: A row of the endpoint table: | `tag` | prefix | count | description |
_ROW_RE = re.compile(r"^\|\s*`(?P<tag>[a-z-]+)`\s*\|[^|]*\|\s*(?P<count>\d+)\s*\|", re.MULTILINE)

_METHODS = {"get", "post", "put", "patch", "delete"}


def _actual() -> tuple[int, int, Counter[str]]:
    schema = create_app().openapi()
    paths = schema.get("paths", {})
    tags: Counter[str] = Counter()
    operations = 0
    for item in paths.values():
        for method, op in item.items():
            if method.lower() not in _METHODS:
                continue
            operations += 1
            for tag in op.get("tags", ["untagged"]):
                tags[tag] += 1
    return len(paths), operations, tags


def test_the_documented_surface_totals_match_the_app() -> None:
    text = API_DOC.read_text(encoding="utf-8")
    match = _HEADLINE_RE.search(text)
    assert match, (
        "docs/api.md no longer states its surface in the expected form. If the "
        "sentence was reworded, this test is checking nothing."
    )

    paths, operations, tags = _actual()
    assert paths, "the app exposes no paths, so nothing was measured"

    assert int(match.group("paths")) == paths, (
        f"docs/api.md says {match.group('paths')} paths, the app has {paths}"
    )
    assert int(match.group("ops")) == operations, (
        f"docs/api.md says {match.group('ops')} operations, the app has {operations}"
    )
    assert int(match.group("tags")) == len(tags), (
        f"docs/api.md says {match.group('tags')} tags, the app has {len(tags)}: {sorted(tags)}"
    )


def test_every_tag_is_documented_with_its_operation_count() -> None:
    """Totals can agree while a whole tag is missing from the table.

    That is exactly what happened: the counts were merely stale, but `extraction`
    was absent altogether, so five endpoints existed that the page gave a reader
    no way to find.
    """

    documented = {
        m.group("tag"): int(m.group("count"))
        for m in _ROW_RE.finditer(API_DOC.read_text(encoding="utf-8"))
    }
    assert documented, "the endpoint table is no longer parseable"

    _, _, tags = _actual()

    missing = sorted(set(tags) - set(documented))
    assert not missing, f"tags exposed by the app but absent from docs/api.md: {missing}"

    invented = sorted(set(documented) - set(tags))
    assert not invented, f"tags documented but not exposed: {invented}"

    wrong = {
        tag: (documented[tag], tags[tag]) for tag in documented if documented[tag] != tags[tag]
    }
    assert not wrong, f"per-tag operation counts disagree (documented, actual): {wrong}"


def test_the_patterns_reject_text_that_does_not_state_the_surface() -> None:
    """Both regexes must be able to match nothing, or the assertions are vacuous."""

    assert _HEADLINE_RE.search("**78 paths / 89 operations** across 12 tags")
    assert not _HEADLINE_RE.search("a large number of paths across several tags")

    assert _ROW_RE.findall("| `ai` | /api/ai | 22 | things |") == [("ai", "22")]
    assert not _ROW_RE.findall("| ai | /api/ai | many | things |")


# ---------------------------------------------------------------------------
# THE CLASSIFIED-OPERATION COUNT, WHEREVER IT IS CLAIMED
# ---------------------------------------------------------------------------
#
# The headline above was guarded; the *capability* count was not, and it decayed
# exactly the same way and for exactly the same reason -- nothing made it stay
# true. Three published pages claimed the layer covered "all 105 API
# operations" while the registry held 108, so a reader was told three operations
# were unclassified when none were.
#
# That claim is load-bearing in a way the headline is not: it is the sentence a
# reader relies on to believe no route escapes classification. It is asserted
# against `OPERATION_BANDS` itself rather than against the OpenAPI document,
# because the claim is about the registry -- and the separate assertion that the
# registry covers the whole surface belongs to the RBAC tests, not here.

#: "all 105 API operations", "all 108 operations". The number is what matters;
#: the optional "API" is there because the pages word it both ways.
_CLASSIFIED_RE = re.compile(r"all (?P<count>\d+)\s+(?:API\s+)?operations", re.IGNORECASE)


def _pages_that_state_a_classified_count() -> list[tuple[Path, int, int]]:
    found: list[tuple[Path, int, int]] = []
    for doc in [*published_documents(), ROOT / "README.md"]:
        if not doc.is_file():
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for match in _CLASSIFIED_RE.finditer(line):
                found.append((doc, lineno, int(match.group("count"))))
    return found


def test_every_documented_classified_operation_count_matches_the_registry() -> None:
    from policy_platform.api.authz import OPERATION_BANDS

    actual = len(OPERATION_BANDS)
    assert actual, "the capability registry is empty, so nothing was measured"

    wrong = [
        f"{doc.relative_to(ROOT)}:{lineno}: says {claimed}, the registry holds {actual}"
        for doc, lineno, claimed in _pages_that_state_a_classified_count()
        if claimed != actual
    ]
    assert not wrong, "documented capability counts disagree with the registry:\n  " + "\n  ".join(
        wrong
    )


def test_the_classified_count_is_actually_claimed_somewhere() -> None:
    """An assertion over an empty set passes while checking nothing."""

    assert _pages_that_state_a_classified_count(), (
        "no published page states the classified-operation count any more — either "
        "the wording changed and this guard is checking nothing, or the claim was "
        "dropped and this guard should be too"
    )


def test_the_classified_pattern_rejects_text_that_states_no_count() -> None:
    assert _CLASSIFIED_RE.search("classifies all 108 API operations and enforces")
    assert _CLASSIFIED_RE.search("All 108 operations are classified into a band")
    assert not _CLASSIFIED_RE.search("all operations are classified into a band")
    assert not _CLASSIFIED_RE.search("108 operations exist")
