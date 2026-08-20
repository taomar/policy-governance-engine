"""The running-path page must keep naming symbols that exist.

`docs/running-path.md` exists because a designed pipeline diverged from the
running one and nothing noticed. Prose cannot hold that on its own: a document
has no test that runs it, which is exactly why it can be wrong indefinitely.

Two claims from that page are checkable, so they are checked here.

1. Every ``module.py::symbol`` reference in it resolves. That catches a rename
   or a deletion turning the page into a confident falsehood.

2. ``run_extraction`` still has no caller under ``src/policy_platform``. This is
   not a check that the code is right — wiring it in would be an improvement.
   It is a check that the page *notices*, so a reader is never told the designed
   stages are unreachable after they have stopped being unreachable.

What is deliberately not checked: whether a step was added to the running path
and left out of the page. Nothing detects an omission. That is why the page says
it should be re-derived from the call path rather than edited from memory.

WHY THIS MODULE CAN SKIP

`docs/running-path.md` is kept on the workstation and out of the published
repository: it describes what this build actually executes, including which
designed stages are unreachable, which is internal working knowledge rather than
documentation of the product. So a clone of the public repository does not have
the page, and every check below would fail on a file that was never meant to be
there.

The module therefore skips as a whole when the page is absent, and runs in full
when it is present. The distinction that matters is preserved: an absent page
skips *visibly*, with this reason, while a present page is checked exactly as
before -- including the floor that fails when the page stops naming symbols.
Absence is a policy, breakage is a failure, and the two never look alike.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAGE = _REPO_ROOT / "docs" / "running-path.md"
_SOURCE_ROOT = _REPO_ROOT / "src" / "policy_platform"

pytestmark = pytest.mark.skipif(
    not _PAGE.exists(),
    reason=(
        "docs/running-path.md is deliberately local-only and absent from the "
        "published repository. These checks run wherever the page is kept."
    ),
)

# `path/to/module.py::symbol`, as written inside backticks on the page.
_REFERENCE = re.compile(r"`([\w/]+\.py)::(\w+)`")

# Repository and agent classes are named without a module, because the page
# names them where they are used rather than where they live. Each is listed
# with the module that defines it so the reference is still checked.
_UNQUALIFIED = {
    "PolicySetRepository": "infrastructure/persistence/repositories/policy_sets.py",
    "ClauseRepository": "infrastructure/persistence/repositories/documents.py",
    "ExtractionRunRepository": "infrastructure/persistence/repositories/candidates.py",
    "CandidateRuleRepository": "infrastructure/persistence/repositories/candidates.py",
    "PassageExtractorAgent": "infrastructure/extraction/passage_extractor.py",
    "PolicyFormulatorAgent": "infrastructure/extraction/policy_formulator.py",
    "discover_structural_relationships": "infrastructure/correlation/relationship_discovery.py",
    "discover_semantic_role_relationships": "infrastructure/correlation/relationship_discovery.py",
    "discover_split_decision_relationships": "infrastructure/correlation/relationship_discovery.py",
    "discover_referent_relationships": "infrastructure/correlation/relationship_discovery.py",
    "discover_enumeration_relationships": "infrastructure/correlation/relationship_discovery.py",
    "stems_needing_adjudication": "infrastructure/correlation/relationship_discovery.py",
}


def _defined_names(module: Path) -> set[str]:
    """Top-level and one-level-nested names defined by a module."""

    tree = ast.parse(module.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(child.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_the_page_is_present() -> None:
    """A scan pointed at a file that is not there passes silently."""

    assert _PAGE.exists(), (
        f"{_PAGE} is missing. Every other check in this module would pass "
        "vacuously without it."
    )


def test_every_named_symbol_exists() -> None:
    text = _PAGE.read_text(encoding="utf-8")
    references = _REFERENCE.findall(text)

    # Guard the guard: if the page is reworded so no reference matches, this
    # test must fail loudly rather than assert nothing.
    assert len(references) >= 15, (
        f"Only {len(references)} `module.py::symbol` references found in "
        f"{_PAGE.name}. The page names a symbol for every step; if it no longer "
        "does, this check has stopped seeing anything."
    )

    missing: list[str] = []
    for relative, symbol in references:
        module = _SOURCE_ROOT / relative
        if not module.exists():
            missing.append(f"{relative} (module not found) :: {symbol}")
            continue
        if symbol not in _defined_names(module):
            missing.append(f"{relative}::{symbol} (symbol not defined)")

    assert not missing, (
        f"{_PAGE.name} names symbols that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\nThe page describes what runs. A name that does not resolve means "
        "the page has drifted from the code, not that the code is wrong."
    )


def test_every_unqualified_name_exists() -> None:
    missing: list[str] = []
    text = _PAGE.read_text(encoding="utf-8")

    for symbol, relative in _UNQUALIFIED.items():
        if f"`{symbol}" not in text and f"::{symbol}`" not in text:
            missing.append(f"{symbol} is no longer named by the page")
            continue
        module = _SOURCE_ROOT / relative
        if not module.exists() or symbol not in _defined_names(module):
            missing.append(f"{symbol} not defined in {relative}")

    assert not missing, (
        "The unqualified names in docs/running-path.md have drifted:\n  "
        + "\n  ".join(missing)
    )


def _callers_of_run_extraction() -> list[str]:
    """Modules under src/policy_platform that reference `run_extraction`."""

    definition = _SOURCE_ROOT / "infrastructure" / "docling" / "pipeline.py"
    callers: list[str] = []
    for module in _SOURCE_ROOT.rglob("*.py"):
        if module == definition:
            continue
        if "run_extraction" in module.read_text(encoding="utf-8"):
            callers.append(str(module.relative_to(_REPO_ROOT)).replace("\\", "/"))
    return sorted(callers)


def test_the_designed_stages_still_have_no_production_caller() -> None:
    """The page tells the reader the nine designed stages are unreachable.

    If that changes, the page must change with it. This test exists to make the
    page fail rather than mislead.
    """

    definition = _SOURCE_ROOT / "infrastructure" / "docling" / "pipeline.py"
    if not definition.exists():
        pytest.fail(
            "src/policy_platform/infrastructure/docling/pipeline.py is gone. "
            "docs/running-path.md still points a reader at it; update the page."
        )

    assert "def run_extraction" in definition.read_text(encoding="utf-8"), (
        "run_extraction is no longer defined in "
        "infrastructure/docling/pipeline.py. docs/running-path.md names it; "
        "update the page."
    )

    callers = _callers_of_run_extraction()
    assert not callers, (
        "docs/running-path.md states that run_extraction has no caller under "
        "src/policy_platform. It now has one:\n  "
        + "\n  ".join(callers)
        + "\n\nThis is not a failure of the code — connecting the designed "
        "stages would be an improvement. It is a failure of the page, which "
        "must be re-derived from the call path before this test can pass."
    )
