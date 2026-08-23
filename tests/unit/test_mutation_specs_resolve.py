"""Every mutation spec still points at code that exists, exactly once.

`scripts/mutation_check.py` treats a mutation whose target is absent as an
error and exits 2, deliberately distinct from 1, so a stale spec can never be
mistaken for a clean pass. That protection only fires when someone runs the
harness, which is a manual step. Nothing in the suite noticed a spec that had
gone stale.

That gap matters most during a restructure. Moving a module leaves the `find`
text byte-identical while the `file` path stops resolving, and the specs are
the record of which guarantees have been shown to fail on purpose. A spec that
silently stopped pointing at anything would take 28 demonstrated guarantees
down to whatever remained, with a green suite the whole way.

The occurrence count is asserted as exactly one, which was measured across all
28 mutations before this test was written. One is the number the harness needs:
`apply_mutation` replaces the first occurrence only, so two matches would mean
the mutation applied somewhere other than where the spec's author was looking —
the exact outcome of moving code and leaving a copy behind.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MUTATIONS = ROOT / "tests" / "mutations"

# The harness is the authority on how a target file is read: it normalises
# newlines so specs written with `\n` match a checkout with `\r\n`. Importing
# its reader rather than reimplementing it means this test and the tool it
# guards cannot disagree about whether a target is present.
sys.path.insert(0, str(ROOT / "scripts"))
import mutation_check  # noqa: E402


def _specs() -> list[tuple[str, int, dict]]:
    found: list[tuple[str, int, dict]] = []
    for spec_path in sorted(MUTATIONS.glob("*.json")):
        for index, spec in enumerate(json.loads(spec_path.read_text(encoding="utf-8"))):
            found.append((spec_path.name, index, spec))
    return found


def test_there_are_mutation_specs_to_check():
    """Guard the guard: an empty glob would make every check below vacuous."""

    assert MUTATIONS.is_dir(), f"mutation spec directory is missing: {MUTATIONS}"
    specs = _specs()
    assert specs, f"no mutation specs found in {MUTATIONS}"
    assert len(specs) == 33, (
        f"expected the 33 recorded mutations, found {len(specs)} — if a mutation was "
        "added or retired deliberately, update this count so the change is visible"
    )


@pytest.mark.parametrize(
    ("spec_file", "index", "spec"),
    [pytest.param(f, i, s, id=f"{f}:{i}") for f, i, s in _specs()],
)
def test_each_mutation_targets_existing_code(spec_file: str, index: int, spec: dict):
    """The file resolves, and the text to break is in it exactly once."""

    target = ROOT / spec["file"]
    assert target.is_file(), (
        f"{spec_file}[{index}] names {spec['file']}, which does not exist. "
        "If the code moved, update the spec's `file` in the same commit."
    )

    text, _ = mutation_check._read(target)
    occurrences = text.count(spec["find"])

    assert occurrences != 0, (
        f"{spec_file}[{index}] ({spec.get('name')!r}) finds nothing in {spec['file']}. "
        "The guarantee it demonstrates is no longer being checked."
    )
    assert occurrences == 1, (
        f"{spec_file}[{index}] ({spec.get('name')!r}) matches {occurrences} places in "
        f"{spec['file']}. The harness mutates the first only, so it is no longer clear "
        "which one this mutation proves."
    )


@pytest.mark.parametrize(
    ("spec_file", "index", "spec"),
    [pytest.param(f, i, s, id=f"{f}:{i}") for f, i, s in _specs()],
)
def test_each_mutation_names_tests_that_exist(spec_file: str, index: int, spec: dict):
    """A mutation is only evidence if the tests it names are real and run.

    A `path::name` selector is checked to the function, not just the file.
    pytest exits 5 when a selector matches nothing, and the harness used to
    read any non-zero status as "the suite noticed" — so a mistyped test name
    reported every mutation in its spec as caught. The harness now raises on
    exits other than 0 and 1; this keeps the spec honest before it gets there.
    """

    tests = spec.get("tests") or []
    assert tests, f"{spec_file}[{index}] names no tests"
    for test in tests:
        path, _, selector = test.partition("::")
        target = ROOT / path
        assert target.is_file(), (
            f"{spec_file}[{index}] names {test}, which does not exist — the harness "
            "would report the mutation as caught because pytest errors on a missing path"
        )
        if not selector:
            continue
        defined = {
            node.name
            for node in ast.walk(ast.parse(target.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        wanted = selector.split("::")[0]
        assert wanted in defined, (
            f"{spec_file}[{index}] selects {selector!r} from {path}, which defines no "
            f"such test — pytest would collect nothing and the mutation would be "
            f"reported as caught having never been tested"
        )


@pytest.mark.parametrize(
    ("spec_file", "index", "spec"),
    [pytest.param(f, i, s, id=f"{f}:{i}") for f, i, s in _specs()],
)
def test_each_mutation_actually_changes_something(spec_file: str, index: int, spec: dict):
    """`replace` equal to `find` would apply cleanly and break nothing."""

    assert spec["find"] != spec["replace"], (
        f"{spec_file}[{index}] replaces the target with itself, so the suite would pass "
        "for the ordinary reason and the mutation would be recorded as caught"
    )
