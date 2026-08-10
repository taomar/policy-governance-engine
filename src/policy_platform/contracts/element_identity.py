"""Deterministic canonical element identity.

WHY THE ORDINAL SCHEME HAD TO GO
--------------------------------
Both legacy ingest paths assigned ``element_id = f"E{n:06d}"`` from the
position of the element in the parser's output list. That has one fatal
property: it is *globally* unstable under a *local* change. If a converter
upgrade detects one extra element on page 1 — a header it now recognises, a
paragraph it now splits — every element after it shifts by one. Every stored
span, every published evidence reference, and every cross-run comparison then
points at the wrong element while still resolving successfully, which is the
worst possible failure: silent, and invisible to a reviewer.

The Docling integration directive also states as a zero-tolerance acceptance
gate that no canonical identity may depend on model-local labels, filenames, or
list order.

WHAT REPLACES IT
----------------
Identity is derived from three things that describe *what and where* an element
is, rather than *when it was emitted*:

1. the **source release** — the SHA-256 of the uploaded bytes, so the same
   sentence in two different documents never collides;
2. a **structural path** — the element's position in the document tree
   (``sec:2.1/para``), not its index in a flat list;
3. a **content digest** — a digest over the element's exact text.

Because all three are properties of the document itself, inserting a new
element changes the identity of that element only. Its neighbours keep the
identities their stored spans already reference.

STRUCTURAL PATH IS NOT LIST ORDER
---------------------------------
A path may legitimately contain a sibling index (``.../para[3]``): "the third
paragraph under heading 2.1" is a structural fact about the document. What it
must not contain is a position in the converter's flat output stream, which is
an artifact of the converter rather than of the document. The distinction is
exactly the difference between an edit shifting one branch and an edit shifting
everything.

COLLISIONS
----------
Two elements can legitimately be identical in all three inputs — most often
repeated table rows with the same values under the same header. Rather than
silently merging them (which would lose a row) or falling back to output order
(which would reintroduce the defect), a deterministic occurrence suffix is
appended and the collision is recorded, so it is visible rather than assumed.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

#: Length of the hex digest carried in an element id. 16 hex characters is 64
#: bits: with even a very large document (10^5 elements) the birthday collision
#: probability is around 10^-9, and collisions are handled explicitly anyway.
#: Kept short because the id appears in every clause reference a reviewer reads.
_DIGEST_LENGTH = 16

_ELEMENT_ID_RE = re.compile(r"^E[0-9a-f]{%d}(?:-\d+)?$" % _DIGEST_LENGTH)

#: Legacy ordinal ids (``E000001``). Recognised so already-published releases
#: keep resolving: the directive forbids silently recanonicalizing them.
_LEGACY_ELEMENT_ID_RE = re.compile(r"^E\d{6}$")


def normalize_for_identity(text: str) -> str:
    """Reduce text to the form used for identity and matching.

    Deliberately conservative. Identity must survive irrelevant whitespace and
    Unicode-encoding differences between converters, because a converter change
    that reflows a line is not a change to the policy. It must *not* survive
    anything that could change meaning, so case, digits, punctuation, negation
    and wording are all preserved: "must not exceed 5" and "must not exceed 5.0"
    are different rules and must never share an identity.

    NFKC folds compatibility forms (ligatures, full-width digits) that different
    converters emit for the same glyphs.
    """

    normalized = unicodedata.normalize("NFKC", text)
    # Collapse every run of whitespace, including the newlines a cross-page join
    # introduces, so page layout cannot alter identity.
    return " ".join(normalized.split())


def structural_path(
    *,
    element_type: str,
    section_path: list[str] | None = None,
    sibling_index: int | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
    column_index: int | None = None,
    list_level: int | None = None,
) -> str:
    """Build the structural location component of an element identity.

    The path describes where the element sits in the document's own structure.
    Table coordinates are included because a table's meaning is positional: the
    value "5" is a different fact in row 2 than in row 7, even though the text
    is identical.
    """

    parts: list[str] = []
    for heading in section_path or []:
        normalized = normalize_for_identity(heading)
        if normalized:
            parts.append(f"sec:{normalized}")

    if table_id:
        parts.append(f"tbl:{table_id}")
    if row_index is not None:
        parts.append(f"r{row_index}")
    if column_index is not None:
        parts.append(f"c{column_index}")
    if list_level is not None:
        parts.append(f"lvl{list_level}")

    leaf = element_type
    if sibling_index is not None:
        leaf = f"{leaf}[{sibling_index}]"
    parts.append(leaf)

    return "/".join(parts)


def element_identity(
    *,
    source_release: str,
    element_type: str,
    text: str,
    section_path: list[str] | None = None,
    sibling_index: int | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
    column_index: int | None = None,
    list_level: int | None = None,
    occurrence: int = 0,
) -> str:
    """Return the deterministic canonical element id.

    `source_release` should be the immutable content hash of the uploaded file.
    `occurrence` disambiguates elements that are genuinely identical in type,
    structural position and text; `assign_element_ids` manages it, so callers
    building one id at a time normally leave it at 0.
    """

    path = structural_path(
        element_type=element_type,
        section_path=section_path,
        sibling_index=sibling_index,
        table_id=table_id,
        row_index=row_index,
        column_index=column_index,
        list_level=list_level,
    )
    payload = "\x1f".join((source_release, path, normalize_for_identity(text)))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    if occurrence:
        return f"E{digest}-{occurrence}"
    return f"E{digest}"


def assign_element_ids(
    source_release: str,
    elements: list[dict],
) -> tuple[list[str], list[str]]:
    """Assign ids to a whole document, resolving collisions deterministically.

    Each entry in `elements` supplies the identity inputs as keyword-compatible
    keys. Returns the assigned ids in the same order, plus a list of
    human-readable collision descriptions.

    Collisions are *returned*, not logged and forgotten: two elements that are
    indistinguishable structurally and textually are usually a real repeated
    table row, but they can also be a converter emitting a paragraph twice. The
    caller records them as ingestion diagnostics so the difference is a review
    decision rather than a silent assumption.
    """

    assigned: list[str] = []
    seen: dict[str, int] = {}
    collisions: list[str] = []

    for element in elements:
        base = element_identity(source_release=source_release, **element)
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            # Re-derive with the occurrence suffix rather than string-appending,
            # so every id in the system comes from the one identity function.
            element_id = element_identity(
                source_release=source_release, occurrence=count, **element
            )
            collisions.append(
                f"{base}: repeated {element.get('element_type', 'element')} with identical "
                f"structural position and text (occurrence {count + 1})"
            )
        else:
            element_id = base
        assigned.append(element_id)

    return assigned, collisions


def is_valid_element_id(value: str) -> bool:
    """True for a content-derived id produced by `element_identity`."""

    return bool(_ELEMENT_ID_RE.match(value))


def is_legacy_element_id(value: str) -> bool:
    """True for an ordinal id from a release ingested before this scheme.

    Published releases keep their original identifiers; the directive forbids
    recanonicalizing them. Recognising the old shape is what lets both resolve
    side by side without one being mistaken for corruption.
    """

    return bool(_LEGACY_ELEMENT_ID_RE.match(value))
