"""Turning an uploaded file into clauses the rest of the platform can read.

A PDF or DOCX arrives, is parsed layout-aware into a canonical document, and
becomes the clause rows every later stage cites. `source_structure` reads the
numbering a document carries -- section and clause references -- so a rule can
say where in the source it came from and a later stage can tell whether two
rules are neighbours.

`manual_extraction` is the path for a rule a person typed rather than a model
proposed. It is here because its output has to enter the same clause and
evidence shape as a parsed document, not because it parses anything.

Docling conversion stays in its own package next to this one. It wraps a
third-party dependency under a boundary its own docstring sets out, and
nesting it deeper would bury that statement without changing what it means.
"""
from __future__ import annotations
