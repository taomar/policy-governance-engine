"""A link in a published document must point at something else that is published.

This repository keeps a deliberate local-only tree (`docs/internal/`), and the
documents in it are excluded from the published repository by `.gitignore`. That
arrangement has a failure mode that is invisible from the machine that writes
it: a relative link from a published page to a local-only page resolves
perfectly in the author's editor and 404s for every reader on GitHub.

It had already happened. The published `README.md` linked to
`docs/running-path.md` and `docs/failures/README.md`, both correctly local, so
two rows of the documentation table were dead for everybody who was not the
author. Nothing detected it because both files existed on the workstation, and
the only way to see the defect was to look at the repository as a stranger.

WHY THIS IS ASSERTED AGAINST THE INDEX, NOT THE FILESYSTEM. `Path.exists()` is
the check that cannot find this class of defect, because the file does exist
locally -- that is the whole point. The question is whether git is publishing
it, so the question is put to git.

WHY THERE IS A FLOOR. A link scan that matched nothing would pass silently and
report success, and this repository has shipped a guard that measured an empty
set more than once. The count of links actually examined is asserted before
anything is concluded from it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

#: `[text](target)` -- the only link form that can point at a repository path.
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

#: Links that name a location rather than a repository file.
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")


def _tracked() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, errors="replace"
    )
    return {line for line in result.stdout.splitlines() if line}


def _normalise(base: Path, target: str) -> str:
    """Resolve `target` relative to `base` without touching the filesystem."""

    parts: list[str] = []
    for segment in (base / target).as_posix().split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment not in ("", "."):
            parts.append(segment)
    return "/".join(parts)


def _published_links() -> tuple[list[tuple[str, str, str]], int]:
    """Every relative link in a published markdown file, and how many were seen."""

    tracked = _tracked()
    directories = {Path(path).parent.as_posix() for path in tracked}

    broken: list[tuple[str, str, str]] = []
    examined = 0

    for path in sorted(p for p in tracked if p.endswith(".md")):
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        base = Path(path).parent
        for raw in _LINK.findall(text):
            target = unquote(raw.split("#")[0].strip())
            if not target or target.startswith(_EXTERNAL_PREFIXES):
                continue
            examined += 1
            resolved = _normalise(base, target)
            if resolved in tracked or resolved.rstrip("/") in directories:
                continue
            broken.append((path, raw, resolved))

    return broken, examined


def test_the_link_scan_examines_a_realistic_number_of_links():
    """The floor. An empty scan passes the assertion below while checking nothing."""

    _, examined = _published_links()
    assert examined > 100, (
        f"only {examined} relative links found across the published documentation; "
        "the scan is not reading what it thinks it is reading"
    )


def test_no_published_document_links_to_an_unpublished_one():
    broken, _ = _published_links()

    assert broken == [], "published documents link to files that are not published:\n" + "\n".join(
        f"  {source}\n      -> {written!r} resolves to {resolved!r}, which git does not track"
        for source, written, resolved in broken
    ) + (
        "\n\nA reader of the public repository gets a 404 for each of these, while the "
        "link resolves for whoever wrote it. Either publish the target, or stop linking "
        "to it and describe the material instead -- see `docs/internal/README.md`."
    )
