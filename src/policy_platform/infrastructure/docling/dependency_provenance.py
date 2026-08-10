"""Provenance and immutability enforcement for the extraction dependencies.

The Docling integration directive requires that the Docling and Docling Graph
codebases be treated as *immutable third-party software*: their source may be
imported and configured, but never edited, patched, monkey-patched, or
regenerated in place. A build- and test-time check must fail when an immutable
file differs from its recorded hash, while explicitly allowlisted runtime paths
(environment files, caches, generated outputs) are permitted to change.

WHY THIS USES PACKAGING METADATA RATHER THAN A COPIED SOURCE TREE
----------------------------------------------------------------
The obvious reading of "copy an exact upstream snapshot and record SHA-256
hashes" is to vendor the upstream git trees. That was measured and rejected:
the Docling repository is ~202 MB, of which ~197 MB is tests and documentation
that a hand-built manifest would then have to cover and re-verify forever.

Python packaging already provides the same guarantee with better tooling:

* a released wheel on PyPI is an immutable artifact with a published digest;
* every installed distribution carries ``.dist-info/RECORD``, which lists a
  SHA-256 digest for *every* installed file;
* the installer writes that file, so verification needs no upstream network
  access and no second copy of the source.

Pinning an exact version and verifying installed files against ``RECORD``
therefore proves precisely what the directive asks for — that no upstream file
has been edited after import — using standard, auditable metadata rather than a
bespoke manifest.

The distinction the directive draws between immutable *code* and mutable
*runtime configuration* is preserved: ``MUTABLE_RUNTIME_PATTERNS`` names what
may legitimately differ, and everything else must match its recorded digest.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import re
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

#: Exact pinned versions. A mismatch is a hard failure rather than a warning:
#: the point of pinning is that extraction behaviour, prompt-schema output,
#: chunking, and provenance semantics stay reproducible across runs, and a
#: version range guarantees none of that.
PINNED_DISTRIBUTIONS: dict[str, str] = {
    "docling-graph": "1.9.1",
}

#: Distributions whose files are verified against their recorded hashes.
#: Deliberately wider than `PINNED_DISTRIBUTIONS`: the immutability rule covers
#: the Docling codebase too, which arrives transitively.
#:
#: `docling` is a meta-package that resolves to `docling-slim[standard]`, so it
#: contains almost no code of its own — verifying only it would check five
#: files and prove nothing. `docling-slim` holds the conversion backends,
#: pipelines and chunkers whose behaviour this integration actually depends on.
VERIFIED_DISTRIBUTIONS: tuple[str, ...] = (
    "docling-graph",
    "docling",
    "docling-slim",
    "docling-core",
)

#: Paths that may legitimately differ from their installed state — the "mutable
#: runtime allowlist" the directive requires. Configuration instances, caches,
#: and generated artifacts are expected to change, and treating them as
#: tampering would make the check useless in practice.
MUTABLE_RUNTIME_PATTERNS: tuple[str, ...] = (
    r"^\.env(\..*)?$",
    r".*\.env$",
    r".*/__pycache__/.*",
    r".*\.pyc$",
    r".*\.pyo$",
    r"^.*\.dist-info/(RECORD|INSTALLER|REQUESTED|direct_url\.json)$",
    r".*/outputs?/.*",
    r".*/\.cache/.*",
)

_MUTABLE_RE = tuple(re.compile(pattern) for pattern in MUTABLE_RUNTIME_PATTERNS)


class DependencyIntegrityError(RuntimeError):
    """Raised when a pinned dependency is missing, mis-versioned, or modified."""


@dataclass
class DistributionProvenance:
    """Recorded identity of one immutable third-party distribution."""

    name: str
    version: str
    license_name: str | None = None
    homepage: str | None = None
    #: Number of files whose digest was checked. Recorded so a verification that
    #: silently checked nothing is distinguishable from one that genuinely passed.
    files_verified: int = 0


@dataclass
class IntegrityReport:
    """Outcome of verifying every configured distribution."""

    distributions: list[DistributionProvenance] = field(default_factory=list)
    #: Files whose on-disk content differs from the hash recorded at install time.
    modified_files: list[str] = field(default_factory=list)
    #: Files listed in RECORD that are no longer present on disk.
    missing_files: list[str] = field(default_factory=list)
    #: Distributions that are not installed at all.
    missing_distributions: list[str] = field(default_factory=list)
    #: Distributions installed at a version other than the pinned one.
    version_mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.modified_files
            or self.missing_files
            or self.missing_distributions
            or self.version_mismatches
        )

    def failure_summary(self) -> str:
        parts: list[str] = []
        if self.missing_distributions:
            parts.append("not installed: " + ", ".join(sorted(self.missing_distributions)))
        if self.version_mismatches:
            parts.append("version mismatch: " + "; ".join(sorted(self.version_mismatches)))
        if self.modified_files:
            parts.append(
                f"{len(self.modified_files)} modified file(s): "
                + "; ".join(sorted(self.modified_files)[:10])
            )
        if self.missing_files:
            parts.append(
                f"{len(self.missing_files)} missing file(s): "
                + "; ".join(sorted(self.missing_files)[:10])
            )
        return " | ".join(parts)


def is_mutable_runtime_path(relative_path: str) -> bool:
    """True when `relative_path` is allowed to differ from its installed state."""

    normalized = relative_path.replace("\\", "/")
    return any(pattern.match(normalized) for pattern in _MUTABLE_RE)


def _record_digest(value: str) -> str | None:
    """Decode a RECORD hash field (``sha256=<urlsafe-b64>``) into a hex digest.

    RECORD stores digests base64url-encoded without padding, so they cannot be
    compared against `hashlib` output directly. Entries carrying no hash
    (directories, and RECORD itself) return None and are skipped by the caller.
    """

    if not value or not value.startswith("sha256="):
        return None
    encoded = value.split("=", 1)[1]
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding).hex()
    except (ValueError, TypeError):
        return None


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata_value(dist: metadata.Distribution, key: str) -> str | None:
    try:
        return dist.metadata.get(key)
    except Exception:  # noqa: BLE001 - metadata access must never break the gate
        return None


def _project_url(dist: metadata.Distribution) -> str | None:
    try:
        urls = dist.metadata.get_all("Project-URL") or []
    except Exception:  # noqa: BLE001
        return None
    for entry in urls:
        label, _, value = str(entry).partition(",")
        if label.strip().lower() in {"repository", "homepage", "source"}:
            return value.strip()
    return None


def _verify_distribution(name: str, report: IntegrityReport) -> None:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        report.missing_distributions.append(name)
        return

    pinned = PINNED_DISTRIBUTIONS.get(name)
    if pinned is not None and dist.version != pinned:
        report.version_mismatches.append(f"{name} expected {pinned}, found {dist.version}")

    provenance = DistributionProvenance(
        name=name,
        version=dist.version,
        license_name=(
            _metadata_value(dist, "License-Expression") or _metadata_value(dist, "License")
        ),
        homepage=_project_url(dist),
    )

    record = dist.read_text("RECORD")
    if record is None:
        # No RECORD means the install method wrote no verifiable hashes (editable
        # installs, some system packages). Treated as a failure rather than a
        # silent pass: an unverifiable dependency defeats the whole gate.
        report.missing_files.append(f"{name}: no RECORD metadata, integrity cannot be verified")
        report.distributions.append(provenance)
        return

    for row in csv.reader(record.splitlines()):
        if not row:
            continue
        relative_path = row[0]
        recorded = _record_digest(row[1] if len(row) > 1 else "")
        if recorded is None or is_mutable_runtime_path(relative_path):
            continue

        # `locate_file` resolves a RECORD-relative path against the install root,
        # which is the only reliable way to find files whether the distribution
        # lives in site-packages, a venv, or elsewhere.
        path = Path(str(dist.locate_file(relative_path)))
        if not path.is_file():
            report.missing_files.append(f"{name}: {relative_path}")
            continue
        if _file_digest(path) != recorded:
            report.modified_files.append(f"{name}: {relative_path}")
            continue
        provenance.files_verified += 1

    report.distributions.append(provenance)


def verify_dependency_integrity(
    distributions: tuple[str, ...] = VERIFIED_DISTRIBUTIONS,
) -> IntegrityReport:
    """Verify pinned versions and per-file hashes for the extraction dependencies.

    Returns a report rather than raising, so every problem can be presented at
    once. `require_dependency_integrity` is the raising variant used by gates.
    """

    report = IntegrityReport()
    for name in distributions:
        _verify_distribution(name, report)
    return report


def require_dependency_integrity(
    distributions: tuple[str, ...] = VERIFIED_DISTRIBUTIONS,
) -> IntegrityReport:
    """Verify integrity and raise `DependencyIntegrityError` on any drift."""

    report = verify_dependency_integrity(distributions)
    if not report.ok:
        raise DependencyIntegrityError(report.failure_summary())
    return report
