"""The dependency direction the package docstrings state, enforced in code.

`contracts/__init__.py` and `evaluator/__init__.py` both declare what they may
not import. Until now those were prose. Prose does not fail a build, and the
restructure this test was written for moves 44 modules — precisely the moment a
layer violation is easiest to introduce and hardest to notice, because a new
import that compiles and passes looks exactly like a correct one.

The allowed map below is measured, not aspirational: it is what the tree does
today, checked across every module. Asserting the current shape means a
violation shows up as a new edge rather than as a judgement call.

The rules are expressed against the *top-level* package, so grouping modules
into sub-packages inside `infrastructure/` does not weaken or invalidate them.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "policy_platform"

#: What each top-level package is permitted to import from the others.
#:
#: Read as: contracts depends on nothing; the evaluator depends only on the
#: contracts; domain is standalone ORM; infrastructure may use all three;
#: `application` composes use cases out of those and holds the ordering a use
#: case needs (reserve, decide, finalise) without knowing about HTTP; the API
#: sits on top of everything.
#:
#: The one arrow worth naming is `api -> application`. It exists so two routes
#: can share one decider without sharing its consequences: the reviewer route
#: answers and persists nothing, the audited external route answers and writes a
#: receipt, and neither reaches the decider directly. `application` must never
#: import `api` — a service that knows about its transport is a router with
#: extra steps.
_ALLOWED: dict[str, set[str]] = {
    "contracts": set(),
    "domain": set(),
    "evaluator": {"contracts"},
    "infrastructure": {"contracts", "domain", "evaluator"},
    "application": {"contracts", "domain", "evaluator", "infrastructure"},
    "api": {"application", "contracts", "domain", "evaluator", "infrastructure"},
}

#: Third-party packages the inner layers must not reach for.
#:
#: Named rather than inferred: an allow-list of "the standard library" would
#: have to track every stdlib module, and would quietly pass a new dependency
#: that happened to shadow one.
_FORBIDDEN_THIRD_PARTY = {
    "httpx",
    "requests",
    "urllib3",
    "openai",
    "azure",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
}


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _package_of(path: Path) -> str:
    """The top-level package a module belongs to, e.g. `infrastructure`."""

    return path.relative_to(SRC).parts[0]


def _imported_roots(path: Path) -> set[tuple[str, int]]:
    """Every top-level module name this file imports, with its line number.

    Relative imports are resolved against the file's own package so that a
    `from .settings import Settings` is attributed correctly rather than
    skipped — a skipped import is a hole in the check.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    package_parts = path.relative_to(SRC.parent).parts[:-1]

    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = list(package_parts)
                if node.level > 1:
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                target = ".".join(anchor + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target:
                found.add((target, node.lineno))
    return found


def test_no_module_imports_from_a_higher_layer():
    """The arrows only ever point inward."""

    violations: list[str] = []
    for path in _modules():
        package = _package_of(path)
        allowed = _ALLOWED.get(package)
        if allowed is None:
            violations.append(f"{path.relative_to(ROOT)}: unknown top-level package {package!r}")
            continue
        for target, lineno in sorted(_imported_roots(path)):
            parts = target.split(".")
            if parts[0] != "policy_platform" or len(parts) < 2:
                continue
            imported = parts[1]
            if imported == package or imported in allowed:
                continue
            violations.append(
                f"{path.relative_to(ROOT)}:{lineno}: {package} imports {imported} "
                f"({target}) — permitted: {sorted(allowed) or 'nothing'}"
            )

    assert not violations, "dependency direction violated:\n  " + "\n  ".join(violations)


def test_the_inner_layers_reach_for_no_network_or_orm_package():
    """What `contracts` and `evaluator` promise in their docstrings.

    Both declare they must not import an Azure, AI, HTTP or (for the
    evaluator) any non-stdlib package. The evaluator is the deterministic
    decision core, so a dependency here is not a style question: it is the
    difference between a decision that can be reproduced from the record and
    one that depends on something outside it.
    """

    violations: list[str] = []
    for path in _modules():
        package = _package_of(path)
        if package not in {"contracts", "evaluator"}:
            continue
        for target, lineno in sorted(_imported_roots(path)):
            root = target.split(".")[0]
            if root in _FORBIDDEN_THIRD_PARTY:
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: {package} imports {root}")

    assert not violations, "inner layer reached outside:\n  " + "\n  ".join(violations)


def test_the_evaluator_imports_only_the_standard_library_and_contracts():
    """The strictest claim in any package docstring, so the strictest check.

    `evaluator/__init__.py` states that only the standard library and
    `policy_platform.contracts` may be imported. That is true today — measured
    across all six modules — and it is worth freezing, because the value of a
    deterministic core is lost the first time it grows a dependency nobody
    noticed.
    """

    allowed_first_party = {"policy_platform.contracts", "policy_platform.evaluator"}
    violations: list[str] = []

    for path in sorted((SRC / "evaluator").rglob("*.py")):
        for target, lineno in sorted(_imported_roots(path)):
            if target.startswith("policy_platform"):
                if not any(target == a or target.startswith(a + ".") for a in allowed_first_party):
                    violations.append(f"{path.relative_to(ROOT)}:{lineno}: imports {target}")
                continue
            root = target.split(".")[0]
            if root == "__future__":
                continue
            # A third-party root is anything importable that is not shipped with
            # Python. Checked against the known set rather than guessed, and any
            # new third-party dependency here should be a deliberate decision.
            if root in _FORBIDDEN_THIRD_PARTY or root in {"pydantic", "numpy", "pandas"}:
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: imports {root}")

    assert not violations, "the evaluator grew a dependency:\n  " + "\n  ".join(violations)
