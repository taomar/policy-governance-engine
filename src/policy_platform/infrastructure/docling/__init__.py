"""Docling-based document conversion and graph discovery.

This package holds every project-owned wrapper, adapter, and validator around
the Docling and Docling Graph dependencies. Those dependencies are treated as
immutable third-party software: nothing in this package may patch, subclass to
override private behaviour, or otherwise reach around their public API.

Where Docling does not expose something the platform needs, it is solved here —
in a pre-call adapter, a post-call adapter, or a downstream validator — or the
limitation is recorded and the affected material is routed to review.
"""
from __future__ import annotations

from policy_platform.infrastructure.docling.dependency_provenance import (
    DependencyIntegrityError,
    IntegrityReport,
    require_dependency_integrity,
    verify_dependency_integrity,
)

__all__ = [
    "DependencyIntegrityError",
    "IntegrityReport",
    "require_dependency_integrity",
    "verify_dependency_integrity",
]
