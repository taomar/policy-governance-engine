"""What must never reach the published repository, asserted rather than trusted.

This repository is public. Several categories of file are deliberately kept on
disk and out of it, each because someone decided so:

  * the session handover and working notes -- written for whoever picks the
    work up on this machine, not documentation of the product;
  * decision records and task lists -- reasoning aids, same argument;
  * internal reports and unfinished work -- failure analyses, drift reports,
    and designs decided but not built. They describe how the product went
    wrong or what it is not yet, which is not what a reader of a public
    repository should have to sift through to learn how it behaves;
  * environment files -- they hold real endpoints, logins and keys;
  * local credentials and the key that signs their tokens.

Until now those decisions lived only in `.gitignore`. That file is itself
published, and it is edited by people who are usually thinking about something
else -- a build artefact, a new tool's cache directory. Nothing connected a
line in it to the decision it was carrying, so removing one looked like tidying
up.

WHY BY SHAPE. Every rule here is checked against names that do not exist yet,
because that is how the two real gaps in this repository were found. A single
`.env` line left `.env.local`, `.env.production` and
`infra/parameters/baseline.env` publishable. A `docs/todo/` rule left a
top-level `todos/` directory publishable. Both were written correctly for the
paths that existed at the time, and both were wrong the moment somebody chose a
different name. A copy called `local-accounts.backup.txt` is the same secret;
`HANDOVER-2.md` is the same session notes.

WHY THE FLOORS. Two of these tests could pass by checking nothing: a
`check_ignore` that always returned true, or a tracked-file listing that came
back empty. Both are asserted to be doing real work before anything is
concluded from them -- this repository has shipped a guard that silently
measured an empty set more than once, and the failure reads exactly like
success.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _is_ignored(path: str) -> bool:
    """Whether git would refuse to track `path`.

    Asks git rather than parsing `.gitignore`, because a reimplementation of
    those matching rules would be a second opinion about the thing under test.
    """

    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, errors="replace"
    )
    return [line for line in result.stdout.splitlines() if line]


#: Names that must never be publishable. Deliberately includes spellings
#: nobody has used, because those are the ones a rule written for today's
#: paths will miss.
MUST_NOT_PUBLISH: dict[str, tuple[str, ...]] = {
    "session handover": (
        "docs/HANDOVER.md",
        "HANDOVER.md",
        "docs/HANDOVER-2.md",
        "docs/handover/notes.md",
        "handover.md",
    ),
    "decision records and task lists": (
        "docs/adr/0001-something.md",
        "docs/todo/next.md",
        "docs/todos/next.md",
        "todos/2026-01-01.md",
        "todo/2026-01-01.md",
        "TODO.md",
        "todos.md",
    ),
    "internal reports and unfinished work": (
        "docs/failures/something.md",
        "docs/repair-passes.md",
        "docs/running-path.md",
        "docs/drift-report.md",
    ),
    "environment files": (
        ".env",
        ".env.local",
        ".env.production",
        "infra/parameters/baseline.env",
    ),
    "local credentials and signing keys": (
        ".local-accounts.txt",
        "local-accounts.txt",
        "local-accounts.backup.txt",
        ".local-accounts.dev.txt",
        ".local-signing-key.pem",
        "some-key.pem",
    ),
}

#: The other half of the rule. A pattern broad enough to catch every private
#: spelling can easily swallow product source, and silently un-publishing a
#: page nobody notices is its own failure.
MUST_STILL_PUBLISH: tuple[str, ...] = (
    ".env.example",
    "docs/specs/docling-integration-handoff.md",
    "src/policy_platform/infrastructure/docling/handoff.py",
    "docs/configuration.md",
    "README.md",
)


def test_git_check_ignore_actually_discriminates():
    """Positive control, before anything is concluded from `_is_ignored`.

    If it answered true for everything -- a wrong flag, a bad cwd -- every
    membership test below would pass while checking nothing.
    """

    assert _is_ignored(".env"), "check-ignore says .env is publishable; the helper is broken"
    assert not _is_ignored(
        "README.md"
    ), "check-ignore says README.md is ignored; the helper is broken"


def test_the_repository_has_tracked_files_to_check():
    """The other positive control. An empty listing passes every scan below."""

    tracked = _tracked_files()
    assert len(tracked) > 200, f"only {len(tracked)} tracked files; the listing is not working"


@pytest.mark.parametrize(
    ("category", "path"),
    [(category, path) for category, paths in MUST_NOT_PUBLISH.items() for path in paths],
)
def test_a_private_file_shape_is_not_publishable(category: str, path: str):
    assert _is_ignored(path), (
        f"{path!r} would be published. It belongs to the {category!r} category, which "
        "is kept out of the public repository on purpose. The rule that covered it has "
        "either been removed or was written for a name that is no longer the one in use."
    )


@pytest.mark.parametrize("path", MUST_STILL_PUBLISH)
def test_a_published_file_is_still_publishable(path: str):
    """A rule broad enough to hide every secret can hide the product too."""

    assert not _is_ignored(path), (
        f"{path!r} is no longer publishable. Something in .gitignore has widened past "
        "the private categories and is now excluding product source or documentation."
    )


def test_nothing_private_is_already_tracked():
    """The rules govern what happens next; this asks what already happened.

    A file added before its rule existed stays tracked, and `.gitignore` has no
    effect on it -- which is how a secret reaches a public repository while
    every check-ignore test passes.
    """

    offenders = [
        path
        for path in _tracked_files()
        if any(
            marker in path.lower()
            for marker in (
                "handover",
                "local-accounts",
                "signing-key",
                "repair-passes",
                "running-path",
                "drift-report",
            )
        )
        # The product's own handoff module and spec legitimately carry the word.
        and "docling-integration-handoff" not in path
        and "docling/handoff" not in path
        and "test_publication" not in path
    ]

    assert offenders == [], (
        "these files are tracked and would be published: "
        f"{offenders}. Being ignored does not untrack a file that was already added; "
        "use `git rm --cached` and confirm it leaves the published tree."
    )


def test_no_tracked_file_carries_a_local_account_password():
    """The rules are about paths; this is about content.

    A credential can reach the published tree inside a file that is perfectly
    publishable -- a doc example, a test fixture, a commit message quoted into
    source. The account file's own format is the thing to look for.
    """

    accounts = ROOT / ".local-accounts.txt"
    if not accounts.exists():
        pytest.skip("no local accounts file on this machine")

    secrets = set()
    for line in accounts.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 2 and len(parts[1]) >= 8:
            secrets.add(parts[1])

    assert secrets, "the accounts file parsed to no passwords; this check would pass vacuously"

    result = subprocess.run(
        ["git", "grep", "-I", "-l", "-F"]
        + [arg for secret in sorted(secrets) for arg in ("-e", secret)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        errors="replace",
    )
    leaked = [line for line in result.stdout.splitlines() if line]

    assert leaked == [], f"a local account password appears in tracked content: {leaked}"
