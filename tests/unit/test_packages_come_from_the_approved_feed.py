"""Packages come from the approved feed, in configuration and in the lockfile.

The registry was already set correctly in a developer's `~/.npmrc`, and
installs still went somewhere else. Two reasons, and both had to be fixed:

  * A user-level setting is not part of the repository. It does not travel with
    a clone, CI never sees it, and nobody reviewing the project can tell which
    feed it will use.

  * The registry only decides where npm *looks a package up*. Once
    package-lock.json exists, an install fetches the literal URL in each
    entry's `resolved` field. This lockfile carried 220 of them pointing at
    four `ms-feed-*.pkgs.visualstudio.com` shards, so every install went there
    whatever `.npmrc` said.

Fixing one without the other looks fixed and is not, which is why this asserts
both and asserts they agree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

APPROVED_REGISTRY = "https://packagefeedproxy.microsoft.io/npm/"
APPROVED_HOST = "packagefeedproxy.microsoft.io"

#: Directories that are not ours to police.
_SKIP = ("node_modules", ".venv", ".venv-graph", "dist", "build")


def _ours(path: Path) -> bool:
    return not any(part in _SKIP for part in path.parts)


def _npmrc_files() -> list[Path]:
    return sorted(p for p in _ROOT.rglob(".npmrc") if _ours(p.relative_to(_ROOT)))


def _lockfiles() -> list[Path]:
    return sorted(
        p for p in _ROOT.rglob("package-lock.json") if _ours(p.relative_to(_ROOT))
    )


def test_the_repository_states_its_registry():
    """Not left to whoever happens to have the right user-level config.

    npm reads the `.npmrc` in the directory it runs from, so every directory a
    build is launched from needs one. `apps/web` is where the web commands run;
    the root copy covers anything run from the top.
    """

    found = {p.parent.relative_to(_ROOT).as_posix() or "." for p in _npmrc_files()}
    for required in (".", "apps/web"):
        assert required in found, (
            f"no .npmrc in {required!r} — npm run from there falls back to the "
            f"public registry. Present: {sorted(found)}"
        )


@pytest.mark.parametrize("npmrc", _npmrc_files(), ids=lambda p: str(p.name))
def test_every_npmrc_names_the_approved_registry(npmrc: Path):
    lines = [
        line.strip()
        for line in npmrc.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    registries = [line for line in lines if line.startswith("registry=")]
    assert registries, f"{npmrc} sets no registry"
    for entry in registries:
        assert entry == f"registry={APPROVED_REGISTRY}", (
            f"{npmrc} names {entry!r}, not the approved feed"
        )


@pytest.mark.parametrize("npmrc", _npmrc_files(), ids=lambda p: str(p.name))
def test_no_npmrc_carries_a_credential(npmrc: Path):
    """A feed URL is build configuration. A token is a secret.

    Committing the first is what makes the build reproducible; committing the
    second would publish a credential, and `.npmrc` is the usual place that
    accident happens.
    """

    text = npmrc.read_text(encoding="utf-8")
    for marker in ("_auth", "_authToken", "_password", "email="):
        assert marker not in text, (
            f"{npmrc} contains {marker!r} — move it to the user-level .npmrc "
            "or the environment; it must not be committed"
        )


@pytest.mark.parametrize("lockfile", _lockfiles(), ids=lambda p: str(p.name))
def test_every_locked_package_resolves_to_the_approved_feed(lockfile: Path):
    """The half that the registry setting does not govern.

    Rewriting these is safe and does not change what is installed: `integrity`
    is a sha512 over the tarball contents, not over its address, so the same
    package verifies identically from either host.
    """

    text = lockfile.read_text(encoding="utf-8")
    json.loads(text)

    hosts: dict[str, int] = {}
    for match in re.finditer(r'"resolved":\s*"https?://([^/"]+)', text):
        hosts[match.group(1)] = hosts.get(match.group(1), 0) + 1

    unapproved = {h: n for h, n in hosts.items() if h != APPROVED_HOST}
    assert not unapproved, (
        f"{lockfile.relative_to(_ROOT)} resolves packages from unapproved "
        f"hosts: {unapproved}. An install reads these URLs directly and will "
        "go there whatever .npmrc says."
    )
