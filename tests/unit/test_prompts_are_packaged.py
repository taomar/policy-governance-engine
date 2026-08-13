"""The prompts must survive a real install, not just an editable one.

The three agent prompts are source: `correlation_agent`, `passage_extractor` and
`policy_formulator` read them at call time. They are `.md` files, so setuptools
does not ship them unless something says to.

Nothing said to. A built wheel contained 103 `.py` files and zero `.md`, which
means a real `pip install .` -- exactly what the Dockerfile does -- produced an
image whose modules had no `prompts/` beside them. Extraction would have raised
`FileNotFoundError` partway through a run, from an agent that had been working.

It stayed invisible for two reasons that cancel each other locally: the
development install is editable, so `__file__` resolves into the source tree
where the prompts do exist; and the container has never run an extraction,
because no Azure environment has been provisioned from this repository.

Building a wheel here would make the suite slow and network-dependent, so this
asserts the declaration instead: every prompt the package ships must be matched
by a `package-data` glob. That catches both ways this breaks -- the declaration
being removed, and a new prompt being added outside its reach.
"""
from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PROMPTS = REPO_ROOT / "src" / "policy_platform" / "infrastructure" / "prompts"


def _package_data() -> dict[str, list[str]]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return config.get("tool", {}).get("setuptools", {}).get("package-data", {})


def _is_declared(relative: str, package: str, patterns: list[str]) -> bool:
    """True when `relative`, read from `package`'s directory, matches a glob."""

    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def test_every_prompt_file_is_declared_as_package_data() -> None:
    prompts = sorted(p.name for p in PROMPTS.glob("*.md"))
    assert prompts, (
        "no prompt files found -- if they moved, this test is now checking "
        "nothing and must be pointed at their new home"
    )

    patterns = _package_data().get("policy_platform.infrastructure", [])
    assert patterns, (
        "pyproject.toml declares no package-data for policy_platform.infrastructure, "
        "so a built wheel will not contain the prompts the agents load"
    )

    undeclared = [
        name for name in prompts if not _is_declared(f"prompts/{name}", "infrastructure", patterns)
    ]
    assert not undeclared, (
        f"these prompts would be missing from a built wheel: {undeclared}. "
        f"package-data patterns are {patterns}"
    )


def test_the_declaration_would_reject_an_unmatched_prompt() -> None:
    """The check above must be able to fail.

    A glob test that accepts anything passes whether or not the declaration is
    correct, which is the failure mode this file exists to prevent elsewhere.
    """

    patterns = _package_data().get("policy_platform.infrastructure", [])

    assert _is_declared("prompts/policy_formulator_v1.md", "infrastructure", patterns)
    assert not _is_declared("elsewhere/policy_formulator_v1.md", "infrastructure", patterns)
    assert not _is_declared("prompts/policy_formulator_v1.txt", "infrastructure", patterns)


def test_every_prompt_the_code_loads_actually_exists() -> None:
    """A declared glob is worthless if it points at files that are not there."""

    loaded = sorted(p.name for p in PROMPTS.glob("*.md"))
    for name in loaded:
        path = PROMPTS / name
        assert path.is_file(), f"{name} is declared but absent"
        assert path.stat().st_size > 0, f"{name} is present but empty"
