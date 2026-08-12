"""Run mutations against the suite and report which ones survive.

This codebase leans on a particular discipline: a test that has never been seen
failing on the defect it describes proves nothing. Checking that means breaking
the code on purpose and confirming the suite notices.

Doing it by hand kept going wrong in the same way. The mutation was applied by
a shell one-liner, the quoting was subtly off, the substitution silently
matched nothing, and the suite passed — which is exactly what it looks like
when the tests genuinely fail to catch a defect. A near-miss on that reading is
worse than no check at all, because it produces a confident wrong conclusion
about coverage.

So a mutation that finds no target is an error here, never a no-op, and the
mutation text lives in a file rather than in a command line where a shell can
reinterpret it.

Usage:

    python scripts/mutation_check.py <spec.json>

The spec is a list of mutations::

    [
      {
        "name": "negation ignored",
        "file": "src/policy_platform/infrastructure/xacml_projection.py",
        "find": "if states_a_negation(rule):",
        "replace": "if False:",
        "tests": ["tests/unit/test_negation_never_projects_as_permit.py"]
      }
    ]

Each is applied on its own, the tests are run, and the file is restored
whatever happens. The exit status is non-zero when any mutation survived — when
the code was broken and the suite still passed — because that is the finding
worth acting on.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TargetNotFound(Exception):
    """The text to mutate is not in the file.

    Raised rather than skipped. A substitution that matches nothing leaves the
    code correct, so the suite passes and the run reports "not caught" for a
    mutation that was never made.
    """


@dataclass(frozen=True)
class Mutation:
    name: str
    file: Path
    find: str
    replace: str
    tests: tuple[str, ...]

    @classmethod
    def from_spec(cls, spec: dict, index: int) -> "Mutation":
        missing = [key for key in ("file", "find", "replace") if key not in spec]
        if missing:
            raise ValueError(f"mutation {index} is missing {missing}")
        tests = spec.get("tests") or []
        if not tests:
            raise ValueError(f"mutation {index} names no tests to run")
        return cls(
            name=spec.get("name") or f"mutation {index}",
            file=(REPO_ROOT / spec["file"]).resolve(),
            find=spec["find"],
            replace=spec["replace"],
            tests=tuple(tests),
        )


def _read(path: Path) -> tuple[str, str]:
    """Read the file with `\\n` endings, and report the endings it really uses.

    Mutation specs are written with `\\n`, because that is what a JSON string
    holds and what anyone editing the spec will type. A file checked out on
    Windows has `\\r\\n`, so a multi-line target matched nothing — the harness
    reported "target not found", which is at least loud, but it would have made
    every multi-line mutation unusable on this platform.

    Matching happens on normalised text and the original endings are restored
    on write, so a run leaves the file byte-identical.
    """

    with path.open("r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _write(path: Path, text: str, newline: str) -> None:
    """Replace the file's contents atomically.

    Written to a sibling temporary file and moved into place, so a failure
    part-way through leaves the original untouched rather than truncated. The
    naive version opened the target for writing directly, and a failure at that
    moment would have destroyed a source file with no restore to fall back on —
    the mutation harness would have become the thing that broke the tree.

    Observed on Windows while the API was running from the same checkout: the
    open failed with `Invalid argument`, after the read and outside the restore
    block. It failed harmlessly by luck.
    """

    body = text.replace("\n", newline) if newline != "\n" else text
    temporary = path.with_suffix(path.suffix + ".mutation-tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_mutation(path: Path, find: str, replace: str) -> tuple[str, str]:
    """Replace the first occurrence, returning the original text and endings."""

    original, newline = _read(path)
    if find not in original:
        raise TargetNotFound(f"{path}: {find!r}")
    _write(path, original.replace(find, replace, 1), newline)
    return original, newline


def run_tests(tests: tuple[str, ...]) -> bool:
    """True when the suite passed — that is, when the mutation went unnoticed."""

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def check(mutation: Mutation) -> bool:
    """Apply, test, restore. True when the mutation survived."""

    original, newline = apply_mutation(mutation.file, mutation.find, mutation.replace)
    try:
        return run_tests(mutation.tests)
    finally:
        _write(mutation.file, original, newline)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="JSON file describing the mutations")
    args = parser.parse_args(argv)

    specs = json.loads(args.spec.read_text(encoding="utf-8"))
    mutations = [Mutation.from_spec(spec, index) for index, spec in enumerate(specs)]

    survived: list[str] = []
    for mutation in mutations:
        try:
            lived = check(mutation)
        except TargetNotFound as error:
            print(f"ERROR  {mutation.name}: target not found — {error}")
            return 2
        status = "SURVIVED" if lived else "caught"
        print(f"{status:9} {mutation.name}")
        if lived:
            survived.append(mutation.name)

    print()
    if survived:
        print(f"{len(survived)} of {len(mutations)} mutations survived: {survived}")
        print("The code was broken on purpose and the suite still passed.")
        return 1
    print(f"all {len(mutations)} mutations were caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
