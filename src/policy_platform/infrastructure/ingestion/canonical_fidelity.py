"""Prove an element's canonical text was built from the fragments it records.

WHY THIS EXISTS
---------------
There is a chain from the PDF to a stored policy passage, and each link is
supposed to carry the guarantee that no word was invented:

1. ``CanonicalPage.raw_text`` -> ``SourceFragment.text``
   Proved by ``CanonicalDocument.verify_fragments()``, which runs on every
   ingest.
2. ``SourceFragment.text``    -> ``CanonicalElement.text``
   Proved by nothing. ``CanonicalElement.text`` carries the field description
   "Canonical text, derived only from source_fragments" and that claim was
   never checked.
3. ``CanonicalElement.text``  -> ``ClauseData.text``
   Identity (``document_extraction.py``: ``text=element.text``).
4. ``ClauseData.text``        -> the rendered extraction batch
   Concatenation with addressing markers.
5. the rendered batch         -> ``PolicyPassage.text``
   Proved by ``passage_extractor.verify_verbatim``.

Step 2 was the only unverified link, and it is the one that matters most,
because it is where canonical text is *written*. Steps 1 and 5 both pass while
step 2 is wrong: the fragments still resolve to their offsets, and the model
still copies faithfully from what it was shown. Both sides of the verbatim
comparison then carry the same corruption, and a fidelity figure computed
across it reads green over text that is not the document's text. That is
exactly the shape of the right-to-left paint-order defect, where quoted
wording was stored in the order the page painted it rather than the order it
reads.

Closing step 2 closes the chain end to end. It is deliberately not done by
re-pointing ``verify_verbatim`` at ``raw_text``: a passage may span several
elements, the fragment boundaries are no longer available at that point, and
the join tolerance would have to be reimplemented there in a second place
where it could drift.

WHY AN INDEPENDENT REIMPLEMENTATION IS CORRECT HERE
---------------------------------------------------
The joins are re-derived below rather than shared with ``_join_lines``, which
performs them. That is not duplication to be factored away: a verifier that
calls the code it verifies proves only that the code is self-consistent. The
value is in the second, independent derivation agreeing with the first.

The hazard an independent derivation does carry is silent divergence -- a new
transformation kind being added to the ``Transformation`` literal and this
module quietly tolerating it. So the check *fails closed*: a transformation it
does not know how to model is a failure, not an exemption. A verifier that
shrugs at the case it was not taught is worse than no verifier, because it
still reports success.

WHAT IS ACTUALLY PERMITTED
--------------------------
For prose, every declared transformation is a *join*. None substitutes,
deletes, or reorders a character. ``line_join_space`` puts a single space where
the source had a line break; ``line_break_hyphen_join`` puts nothing,
preserving the hyphen ("employ-" + "ment" -> "employ-ment", never
"employment"); ``cross_page_join`` labels which boundary was crossed without
changing how it is joined. So the comparison against source is exact once those
breaks are accounted for -- there is no need to decide "what does verbatim mean
when the text has legitimately changed", because within a prose element no
character ever legitimately changes.

WHAT THIS CANNOT PROVE, AND WHY THAT IS SAID OUT LOUD
-----------------------------------------------------
``table_cell_join`` is different in kind, and excluded. A table row's text is
``" | ".join(cells)`` -- a separator that appears nowhere in the source -- and
its fragments are the raw lines the row's *bounding box* covers, falling back
to the whole table's span when no row box is available. So a row's provenance
is geometric rather than textual: the recorded fragments of a multi-column row
interleave characters from cells the row does not contain, by construction.

Measured on the live corpus, this is 400 of 3,000 elements. Every one of them
is a table row, and none is a defect.

The consequence is worth stating plainly rather than burying in an exclusion:
**a table row's text cannot be proved to have come from the source by
reconstruction.** Its cells are individually verbatim, but nothing here can
demonstrate that. That is a genuinely weaker guarantee than prose enjoys, and
it applies to exactly the content -- rate tables, allowance schedules -- where a
misread number is most costly.

The right check for that class is containment-in-order rather than equality:
every character of the row present in the fragments, in order, interleaved with
others. That is precisely what ``FragmentResolution.span_not_isolating`` in
``contracts/canonical_document.py`` is being built to express, so it belongs
there and is deliberately not reimplemented here. A second, parallel judgement
about the same evidence is how two checks come to disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
)

#: A line break as the parser emitted it, with any padding either side.
_BREAK = re.compile(r"[ \t]*\n[ \t]*")

#: A break the hyphen rule swallows: a hyphen closing an alphabetic word,
#: continued by a lower-case fragment. Mirrors the condition in `_join_lines`.
_HYPHEN_BREAK = re.compile(r"(?<=[^\W\d_])-[ \t]*\n[ \t]*(?=[a-z])")

#: Transformations this module knows how to reproduce. Anything outside this
#: set fails rather than passing unmodelled -- see "fails closed" above.
_MODELLED: frozenset[str] = frozenset(
    {
        "line_join_space",
        "line_break_hyphen_join",
        "cross_page_join",
    }
)

#: Declared transformations whose element text is assembled rather than joined,
#: and so cannot be reconstructed here. Excluded knowingly, and counted.
_NOT_RECONSTRUCTIBLE: frozenset[str] = frozenset({"table_cell_join"})


@dataclass(frozen=True)
class FidelityReport:
    """Every element gets a disposition: verified, failed, or unprovable.

    Deliberately not a bare ``list[str]`` of failures. An empty failure list
    would read as "the document is proved", when it can equally mean "nothing
    was checked" -- and this repository has shipped that confusion more than
    once. Holding the unprovable count beside the verified one makes the
    difference impossible to miss.
    """

    verified: int = 0
    failures: list[str] = field(default_factory=list)
    unprovable: list[str] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return self.verified + len(self.failures)


def rebuild_element_text(element: CanonicalElement) -> str:
    """Rejoin an element's recorded fragments under its declared transformations.

    A page boundary is a line boundary, so fragments are rejoined with the
    break they were split at and the declared rule is then applied to every
    break uniformly.
    """

    raw = "\n".join(fragment.text for fragment in element.source_fragments)
    declared = set(element.transformations)
    if "line_break_hyphen_join" in declared:
        raw = _HYPHEN_BREAK.sub("-", raw)
    if declared:
        raw = _BREAK.sub(" ", raw)
    return raw.strip()


def verify_element_text(document: CanonicalDocument) -> FidelityReport:
    """Prove every element's text is its fragments joined as declared."""

    verified = 0
    failures: list[str] = []
    unprovable: list[str] = []

    for element in document.elements:
        declared = set(element.transformations)

        if declared & _NOT_RECONSTRUCTIBLE:
            unprovable.append(
                f"{element.element_id}: assembled from cells with a separator that is "
                "not in the source, and located by bounding box, so its text cannot be "
                "reconstructed from its fragments"
            )
            continue

        unknown = sorted(declared - _MODELLED)
        if unknown:
            failures.append(
                f"{element.element_id}: declares transformation(s) "
                f"{', '.join(unknown)} that this check cannot reproduce, so its "
                "text is unverified rather than verified"
            )
            continue

        if not element.source_fragments:
            # Reported, never skipped. An element with text and no recorded
            # source has no provenance at all, and passing over it silently is
            # the failure mode this repository has met more than once: a check
            # that walks nothing and reports success.
            if element.text.strip():
                failures.append(
                    f"{element.element_id}: has text but records no source "
                    "fragments, so nothing connects it to the document"
                )
            else:
                verified += 1
            continue

        if rebuild_element_text(element) == element.text:
            verified += 1
        else:
            failures.append(
                f"{element.element_id}: text is not its fragments joined as "
                f"declared ({', '.join(element.transformations) or 'no transformation'}); "
                f"expected {rebuild_element_text(element)[:80]!r}, "
                f"stored {element.text[:80]!r}"
            )

    return FidelityReport(verified=verified, failures=failures, unprovable=unprovable)
