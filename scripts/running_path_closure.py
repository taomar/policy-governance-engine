#!/usr/bin/env python
"""List the production call closure, so the running-path page can be re-derived.

`docs/running-path.md` is checked by
`tests/unit/test_the_running_path_is_the_documented_path.py`, but only in one
direction: every symbol the page names must exist. Nothing checks the inverse —
that every capability on the path is named by the page. A step added and left
off the page is exactly how the divergence the page exists to prevent begins.

This is that inverse direction, deliberately shipped as a **script rather than a
test**. The measurement behind that choice is recorded at the bottom of this
docstring: at module granularity the check has around four in five findings
genuine, and no mechanical rule separates a capability that belongs on the page
from a helper that does not. A build-failing guard at that precision gets
disabled within a week, and a suppressed alarm is worse than the stated gap the
page already carries.

So this prints, and a person decides. Run it when revising the page:

    python scripts/running_path_closure.py

Precision, measured 2026-08-14 over 126 production modules: the closure reached
46 modules, of which 31 were not named by the page. Restricting to the
extraction, correlation and ingestion packages left 10 findings, 8 of them
genuine — imports confirmed by hand — and 2 artefacts (a class the page names
without its module, and one name collision). The other 21 were data shapes,
repositories and routers: reached on every run, never a step.

The closure over-approximates on purpose. Where a called name is defined in more
than one module, every definition is followed, because losing a real edge would
make this quietly useless in the one direction it is meant to help.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "policy_platform"
PAGE = ROOT / "docs" / "running-path.md"

#: The two production entry points. Everything the platform does hangs off
#: these; see docs/running-path.md.
ENTRY_POINTS = [
    ("api/routers/documents.py", "upload_document"),
    ("api/routers/ai.py", "extract_with_ai"),
]

#: Packages where an unnamed module is worth a human look. Contracts,
#: repositories and routers are reached on every run and are data shapes or
#: storage, not steps, so including them buries the finding under the traffic.
PACKAGES_OF_INTEREST = (
    "infrastructure/extraction/",
    "infrastructure/correlation/",
    "infrastructure/ingestion/",
    "infrastructure/docling/",
    "infrastructure/quality/",
)


def _parse_production_modules() -> dict[str, ast.Module]:
    trees: dict[str, ast.Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = str(path.relative_to(SRC)).replace("\\", "/")
        try:
            trees[relative] = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue
    return trees


def _index(trees: dict[str, ast.Module]):
    """Map every function name to the modules defining it, and its callees."""
    defines: dict[str, set[str]] = defaultdict(set)
    callees: dict[tuple[str, str], set[str]] = {}
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defines[node.name].add(module)
            names: set[str] = set()
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
            callees[(module, node.name)] = names
    return defines, callees


def _closure(defines, callees) -> set[tuple[str, str]]:
    reached: set[tuple[str, str]] = set()
    pending = list(ENTRY_POINTS)
    while pending:
        item = pending.pop()
        if item in reached:
            continue
        reached.add(item)
        for name in callees.get(item, ()):
            for owner in defines.get(name, ()):
                if (owner, name) not in reached:
                    pending.append((owner, name))
    return reached


def _modules_named_by_the_page(text: str) -> set[str]:
    return set(re.findall(r"`([\w/]+\.py)(?:::\w+)?`", text))


def main() -> int:
    if not SRC.is_dir():
        print(f"FATAL: {SRC} does not exist. Nothing was scanned.", file=sys.stderr)
        return 2
    if not PAGE.is_file():
        print(f"FATAL: {PAGE} does not exist. Nothing to compare against.", file=sys.stderr)
        return 2

    trees = _parse_production_modules()
    defines, callees = _index(trees)

    # A closure computed from nothing reports nothing and looks like health.
    # Refuse a verdict the scan did not earn.
    if len(trees) < 50:
        print(f"FATAL: only {len(trees)} production modules parsed.", file=sys.stderr)
        return 2
    for module, function in ENTRY_POINTS:
        if (module, function) not in callees:
            print(
                f"FATAL: entry point {module}::{function} was not found. "
                "The closure would start from nowhere and report nothing.",
                file=sys.stderr,
            )
            return 2

    reached = _closure(defines, callees)
    modules = sorted({module for module, _ in reached})
    named = _modules_named_by_the_page(PAGE.read_text(encoding="utf-8"))

    print(f"production modules parsed : {len(trees)}")
    print(f"functions in the closure  : {len(reached)}")
    print(f"modules in the closure    : {len(modules)}")
    print(f"modules named by the page : {len(named)}")

    interesting = [
        module
        for module in modules
        if module not in named and module.startswith(PACKAGES_OF_INTEREST)
    ]

    print(f"\nOn the path, in a package of interest, not named by the page: {len(interesting)}")
    for module in interesting:
        print(f"    {module}")
    print(
        "\nThese are candidates, not defects. A helper does not belong on a page "
        "of steps; a capability does. Read them before writing."
    )

    other = [m for m in modules if m not in named and not m.startswith(PACKAGES_OF_INTEREST)]
    print(f"\n(Suppressed: {len(other)} reached modules outside those packages.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
