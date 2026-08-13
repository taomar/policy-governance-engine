"""Every path a document points at is a path that exists.

The docs describe the system by naming its modules, and a restructure moves
modules. A reference that has gone stale is not a cosmetic problem: these pages
are how someone decides where to make a change, and a confident wrong pointer
costs more than no pointer at all.

This was checked by hand before, and by hand it missed things twice. The first
pass matched only references ending in a file extension, so every directory
reference in the tree went unchecked — which is how `src/policy_platform/worker/`
survived in two documents describing a package that has never existed. Widening
to directories then found a third false claim on a pass already reported clean.

What is checked, and what is deliberately not:

* A reference must contain a separator and end either in a known extension or
  in `/`. That admits `infrastructure/mappers.py` and `docs/specs/` while
  leaving out HTTP routes (`/api/policy-sets`), media types
  (`application/problem+json`) and GitHub slugs (`casbin/casbin`), none of
  which are paths in this repository.
* A `module.py::symbol` reference is checked as far as the file. The symbol is
  left alone: resolving it would mean parsing for a name that may be a method,
  a constant or a nested function, and a check that is wrong in either
  direction is worse than one with a stated limit.
* A bare filename is not checked. The docs establish a directory in one table
  cell and use basenames in the next, so `passage_extractor.py` on its own is
  ambiguous by design; matching it anywhere in the tree would assert almost
  nothing while producing the false positives that teach people to ignore a
  check.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

INLINE_CODE = re.compile(r"`([^`\n]+)`")

#: A first segment carrying an interior dot is a hostname, not a directory.
#:
#: Written to allow a leading dot, because `.github/workflows/` and
#: `.venv-graph/` are repository paths while `iso.org/standard/75080.html` and
#: `docs.camunda.io/docs/` are citations that happen to be written without a
#: scheme.
_HOSTNAME_SEGMENT = re.compile(r"^\.?[^/.]+\.[^/]*$")

#: Extensions that mark a reference as naming a file rather than a route.
_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yml", ".yaml",
    ".ps1", ".sh", ".sql", ".toml", ".cfg", ".ini", ".txt", ".html", ".css",
    ".bicep", ".lock", ".xml", ".csv",
)

#: Where a documented path may be rooted.
#:
#: More than the repository root because the docs address modules the way a
#: reader thinks about them. A table about the infrastructure layer writes
#: `docling/converter.py`, and a page about the web app writes
#: `components/RuleCard.tsx`; both are correct and neither is repo-relative.
def _roots(doc: Path) -> list[Path]:
    return [
        ROOT,
        doc.parent,
        ROOT / "src" / "policy_platform",
        ROOT / "src" / "policy_platform" / "infrastructure",
        ROOT / "apps" / "web" / "src",
    ]


#: References that are correct while naming nothing in the tree.
#:
#: Each is here for a stated reason. Left as a set rather than a pattern so
#: adding one is a decision someone makes explicitly, in a diff, with the
#: reason next to it.
_EXPECTED_ABSENT: dict[str, str] = {
    # Documented precisely because they do not exist. The sentence around each
    # of these says so; the reference is the subject of a negative claim.
    "docs/adr/": "known-limitations.md records that ADRs are cited in code but absent",
    ".github/workflows/": "configuration.md records that no CI pipeline exists yet",
    # Real when the platform runs, absent from a clean checkout by design.
    ".venv-graph/": "git-ignored virtual environment",
    # Owned by an upstream package or an external document, not by this repo.
    "docling_graph/templategen/snippets.py": "a module inside the docling-graph dependency",
}


def _documents() -> list[Path]:
    found = sorted(DOCS.rglob("*.md"))
    readme = ROOT / "README.md"
    if readme.is_file():
        found.append(readme)
    return found


def _is_checkable(reference: str) -> bool:
    text = reference.strip()
    if not text or " " in text:
        return False
    if text.startswith(("http://", "https://", "/", "...")):
        return False
    if any(character in text for character in "{}<>#*"):
        return False
    if "/" not in text:
        return False
    if _HOSTNAME_SEGMENT.match(text.split("/", 1)[0]):
        return False
    path_part = text.split("::", 1)[0]
    return path_part.endswith("/") or path_part.lower().endswith(_EXTENSIONS)


def _references() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for doc in _documents():
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for span in INLINE_CODE.findall(line):
                if _is_checkable(span):
                    found.append((doc, lineno, span.strip()))
    return found


def _resolves(reference: str, doc: Path) -> bool:
    # The symbol after `::` names something inside the file, so only the file
    # part is a path.
    path_part = reference.split("::", 1)[0].lstrip("./")
    return any((root / path_part).exists() for root in _roots(doc))


def test_there_are_documents_and_references_to_check():
    """Guard the guard: an empty scan would pass while checking nothing."""

    documents = _documents()
    assert documents, f"no documents found under {DOCS}"
    references = _references()
    assert len(references) > 100, (
        f"only {len(references)} checkable path references found across "
        f"{len(documents)} documents — the extraction has probably stopped matching"
    )


def test_every_documented_path_exists():
    """A reader following a reference must arrive somewhere."""

    missing: list[str] = []
    for doc, lineno, reference in _references():
        if reference in _EXPECTED_ABSENT:
            continue
        if not _resolves(reference, doc):
            missing.append(f"{doc.relative_to(ROOT)}:{lineno}: {reference}")

    assert not missing, (
        "documents point at paths that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\nIf the code moved, update the document in the same commit. If the "
        "reference is correct while naming nothing in the tree, add it to "
        "_EXPECTED_ABSENT with the reason."
    )


@pytest.mark.parametrize("reference", sorted(_EXPECTED_ABSENT))
def test_each_documented_absence_is_still_referenced(reference: str):
    """An exception outlives its reference and then hides the next mistake.

    Checked rather than trusted: once nothing cites a path, the entry is a
    standing permission for a broken reference nobody meant to allow.
    """

    cited = any(reference == found for _, _, found in _references())
    assert cited, (
        f"_EXPECTED_ABSENT lists {reference!r} but no document mentions it any more — "
        "remove the entry so it cannot excuse a future reference"
    )
