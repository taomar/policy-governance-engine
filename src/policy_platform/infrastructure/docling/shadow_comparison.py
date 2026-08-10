"""Fidelity comparison between the legacy parsers and Docling.

The directive permits the legacy parser to run in shadow mode for migration QA
only, and requires text and layout fidelity to be compared before Docling is
promoted to the sole new-ingestion converter. This module produces that
comparison; it is not part of the ingestion path and must never be used to
reconcile two live text authorities.

WHAT IS COMPARED, AND WHY NOT RAW TEXT EQUALITY
-----------------------------------------------
The two converters legitimately disagree about *segmentation*: where one
paragraph ends and the next begins, whether a heading is its own element,
whether a table becomes rows or cells. Comparing element counts or raw strings
would therefore report enormous differences that mean nothing.

What actually matters for this platform is whether **the words survived**. If a
sentence exists in the legacy output but appears nowhere in the Docling output,
a policy statement has been lost, and no amount of structural improvement
compensates for that. The comparison is consequently token-based:

* recall — legacy content that Docling also recovered. Below 1.0 means content
  the old parser found is now missing, which blocks cutover.
* addition — content Docling recovered that the legacy parser missed. Usually
  an improvement (headers, table cells, footnotes the old path dropped), but
  reported rather than assumed good.

Structural gains are reported separately as counts, because they are the reason
to migrate but are not evidence of fidelity.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from policy_platform.contracts.canonical_document import CanonicalDocument

_WORD_RE = re.compile(r"\w+", re.UNICODE)

#: Tokens too common to carry meaning when checking whether content survived.
#: Kept deliberately small: aggressive stopword removal would hide the loss of a
#: short but decisive clause such as "not more than".
_TRIVIAL = frozenset({"the", "a", "an", "of", "to", "and", "or", "in", "for", "is", "be"})


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _WORD_RE.findall(normalized)


def _content_tokens(document: CanonicalDocument) -> list[str]:
    """Tokens carrying document content, including list enumeration labels.

    The marker is included because converters differ in where they put it:
    the legacy parsers leave "D." inside the element text, while Docling holds
    it as structure in ``list_marker``. Comparing text alone would report the
    label as lost when it was merely relocated — and would equally hide the case
    where it really was dropped.
    """

    tokens: list[str] = []
    for element in document.elements:
        tokens.extend(t for t in _tokens(element.text) if t not in _TRIVIAL)
        if element.list_marker:
            tokens.extend(t for t in _tokens(element.list_marker) if t not in _TRIVIAL)
    return tokens


@dataclass
class ShadowComparison:
    """Measured fidelity of one document under both converters."""

    document_name: str
    legacy_parser: str
    legacy_elements: int = 0
    docling_elements: int = 0
    legacy_tokens: int = 0
    docling_tokens: int = 0
    #: Distinct legacy tokens absent from the Docling output, capped for report
    #: readability. Any entry here is potential content loss.
    missing_tokens: list[str] = field(default_factory=list)
    added_tokens: list[str] = field(default_factory=list)
    missing_token_count: int = 0
    added_token_count: int = 0
    #: Structural capability gained, by canonical element type.
    docling_type_counts: dict[str, int] = field(default_factory=dict)
    legacy_type_counts: dict[str, int] = field(default_factory=dict)
    legacy_fragment_failures: int = 0
    docling_fragment_failures: int = 0

    @property
    def recall(self) -> float:
        """Share of distinct legacy content tokens present in Docling output."""

        legacy_distinct = self.legacy_tokens
        if not legacy_distinct:
            return 1.0
        return (legacy_distinct - self.missing_token_count) / legacy_distinct

    @property
    def blocks_cutover(self) -> bool:
        """True when Docling lost content the legacy parser recovered.

        Structural difference is expected and fine. Missing words are not: they
        are a policy statement that can no longer be extracted at all.
        """

        return self.missing_token_count > 0 or self.docling_fragment_failures > 0


def compare(
    legacy: CanonicalDocument,
    docling: CanonicalDocument,
    *,
    document_name: str,
    sample_limit: int = 25,
) -> ShadowComparison:
    """Compare two canonical documents produced from the same source file."""

    legacy_tokens = set(_content_tokens(legacy))
    docling_tokens = set(_content_tokens(docling))

    missing = sorted(legacy_tokens - docling_tokens)
    added = sorted(docling_tokens - legacy_tokens)

    return ShadowComparison(
        document_name=document_name,
        legacy_parser=legacy.parser,
        legacy_elements=len(legacy.elements),
        docling_elements=len(docling.elements),
        legacy_tokens=len(legacy_tokens),
        docling_tokens=len(docling_tokens),
        missing_tokens=missing[:sample_limit],
        added_tokens=added[:sample_limit],
        missing_token_count=len(missing),
        added_token_count=len(added),
        legacy_type_counts=_type_counts(legacy),
        docling_type_counts=_type_counts(docling),
        legacy_fragment_failures=len(legacy.verify_fragments()),
        docling_fragment_failures=len(docling.verify_fragments()),
    )


def _type_counts(document: CanonicalDocument) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element in document.elements:
        counts[element.element_type] = counts.get(element.element_type, 0) + 1
    return dict(sorted(counts.items()))


def format_report(comparisons: list[ShadowComparison]) -> str:
    """Render a human-readable cutover report."""

    lines: list[str] = ["# Docling shadow comparison", ""]

    for comparison in comparisons:
        verdict = "BLOCKS CUTOVER" if comparison.blocks_cutover else "no content loss"
        lines.extend(
            [
                f"## {comparison.document_name}",
                "",
                f"- verdict: **{verdict}**",
                f"- token recall: {comparison.recall:.4f}",
                f"- elements: legacy {comparison.legacy_elements} -> docling {comparison.docling_elements}",
                f"- distinct content tokens: legacy {comparison.legacy_tokens} -> docling {comparison.docling_tokens}",
                f"- tokens missing from docling: {comparison.missing_token_count}",
                f"- tokens added by docling: {comparison.added_token_count}",
                f"- legacy element types: {comparison.legacy_type_counts}",
                f"- docling element types: {comparison.docling_type_counts}",
                f"- fragment resolution failures: legacy {comparison.legacy_fragment_failures}, "
                f"docling {comparison.docling_fragment_failures}",
            ]
        )
        if comparison.missing_tokens:
            lines.append(f"- sample missing tokens: {comparison.missing_tokens}")
        if comparison.added_tokens:
            lines.append(f"- sample added tokens: {comparison.added_tokens}")
        lines.append("")

    blocking = [c.document_name for c in comparisons if c.blocks_cutover]
    lines.extend(
        [
            "## Verdict",
            "",
            (
                f"{len(blocking)} document(s) block cutover: {blocking}"
                if blocking
                else "No document lost content under Docling."
            ),
            "",
        ]
    )
    return "\n".join(lines)
