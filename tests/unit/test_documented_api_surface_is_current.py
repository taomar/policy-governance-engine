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
