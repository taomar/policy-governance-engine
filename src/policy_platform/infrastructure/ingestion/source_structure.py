"""Domain-neutral structural signals read off a document's own text.

Everything here answers a question about *document structure*, never about
subject matter. It is used by ingestion (to enrich canonical elements) and by
window assembly and relationship discovery (to connect elements the document
itself connects). No function in this module knows what an employee, a device,
an invoice or a control is, and none may ever be given a branch that does.

Three signals are detected:

* **Heading numbering** — ``"4.1 Faulty equipment"`` is a child of ``"4.
  Replacement"``. Numbering is the one hierarchy signal that survives both PDF
  and DOCX ingestion, because it is written in the text rather than carried in
  layout metadata that one of the two parsers always loses.
* **Explicit references** — ``"see section 11"``, ``"Article 74"``,
  ``"clause 3.2"``, ``"Table 2.1"``. These are the strongest possible evidence
  for a relationship, because the author stated it.
* **Salient terms** — capitalised or quoted phrases that behave like defined
  vocabulary in *any* domain. Used to propose ``definition_used_by`` candidates,
  never to classify content.

Detection is deliberately conservative. A missed reference costs a candidate a
reviewer could have seen; a fabricated one costs trust in every relationship the
platform reports.
"""
from __future__ import annotations

import re

#: Structural nouns that introduce a cross-reference in formal documents of any
#: domain. Deliberately generic: these are document-architecture words (the same
#: set an ISO standard, a statute, an HR handbook and a runbook all use), not
#: subject-matter words. `_REFERENCE_RE` requires one of these *followed by* a
#: number-like token, so the noun alone never produces a reference.
_REFERENCE_NOUNS = (
    "section",
    "sections",
    "clause",
    "clauses",
    "article",
    "articles",
    "paragraph",
    "paragraphs",
    "subsection",
    "annex",
    "appendix",
    "schedule",
    "table",
    "figure",
    "exhibit",
    "part",
    "chapter",
    "rule",
    "step",
    "item",
)

_REFERENCE_RE = re.compile(
    r"\b(?P<noun>" + "|".join(_REFERENCE_NOUNS) + r")\s*"
    r"(?P<label>\(?[A-Za-z]?\d+(?:[.\-]\d+)*\)?)",
    re.IGNORECASE,
)

#: A leading outline number: ``4.``, ``4.1``, ``4.1.2``, ``(3)``. Used both to
#: detect that a heading is numbered and to derive its depth.
_HEADING_NUMBER_RE = re.compile(r"^\(?(?P<number>\d+(?:\.\d+)*)\)?[.)]?\s+")

#: The other universal heading shape: a structural noun followed by its number
#: (``Article 74. Annual leave``, ``Section 5 — Retention``, ``Step 3: Approve``).
#: Both shapes appear across every domain — statutes and standards prefer the
#: noun form, handbooks and procedures the bare-number form — so supporting only
#: one silently loses the hierarchy of half the corpora the platform ingests.
_HEADING_NOUN_RE = re.compile(
    r"^(?P<noun>" + "|".join(_REFERENCE_NOUNS) + r")\s+(?P<number>\d+(?:[.\-]\d+)*)\b",
    re.IGNORECASE,
)

#: A quoted or Title-Cased multiword phrase, the shape defined vocabulary takes
#: in formal prose. Two words minimum: a single capitalised word is far more
#: often a sentence start than a defined term.
_QUOTED_TERM_RE = re.compile(r"[\"“”']([A-Za-z][A-Za-z \-/]{2,60}?)[\"“”']")
_TITLE_TERM_RE = re.compile(r"\b([A-Z][a-z]+(?:[ \-][A-Z][a-z]+){1,4})\b")


def normalize_reference(label: str) -> str:
    """Canonical form of a reference label, for comparison across phrasings.

    ``"Section 4.1"``, ``"section 4.1."`` and ``"(4.1)"`` all normalise to
    ``"4.1"`` so a reference and the heading it points at can be matched without
    the caller re-implementing punctuation handling.
    """

    return label.strip().strip("()[].,;:").casefold()


def detect_references(text: str) -> list[str]:
    """Explicit structural references made by this text, in order of appearance.

    Returns strings like ``"section 11"`` and ``"table 2.1"`` — the noun and the
    label together, lower-cased. The noun is kept because ``"table 2.1"`` and
    ``"section 2.1"`` point at different things, and a bare ``"2.1"`` would
    match both.
    """

    found: list[str] = []
    for match in _REFERENCE_RE.finditer(text or ""):
        noun = match.group("noun").casefold().rstrip("s")
        label = normalize_reference(match.group("label"))
        if not label or not any(char.isdigit() for char in label):
            continue
        reference = f"{noun} {label}"
        if reference not in found:
            found.append(reference)
    return found


def heading_number(text: str) -> str | None:
    """The outline number a heading carries, or None when it has none.

    Recognises both universal shapes: a leading number (``4.1 Faulty
    equipment``) and a structural noun followed by its number (``Article 74.
    Annual leave``). Returns the number alone in both cases, normalised on
    ``.``, so ``"section 4.1"`` and ``"4.1"`` compare equal.
    """

    stripped = (text or "").strip()
    match = _HEADING_NUMBER_RE.match(stripped)
    if match:
        return match.group("number")
    noun_match = _HEADING_NOUN_RE.match(stripped)
    if noun_match:
        return noun_match.group("number").replace("-", ".")
    return None



def heading_depth(text: str) -> int:
    """Nesting depth implied by a heading's own numbering.

    ``"4. Replacement"`` is depth 1, ``"4.1 Faulty equipment"`` depth 2. An
    unnumbered heading returns 1: without numbering there is no evidence of
    nesting, and guessing depth from font size is exactly the kind of
    parser-specific inference that does not survive both PDF and DOCX.
    """

    number = heading_number(text)
    return len(number.split(".")) if number else 1


def push_heading(path: list[str], heading: str, *, outline_level: int | None = None) -> list[str]:
    """Return the section path after entering ``heading``.

    ``outline_level`` is the depth the *document itself* declares (Word's
    Heading 1/2/3 style). It is authoritative when supplied, because it is a
    statement by the author rather than an inference: an unnumbered
    ``Scope`` -> ``Eligibility`` -> paragraph structure has a real hierarchy
    that no amount of text analysis can recover, and treating it as flat put
    every paragraph of such a document in the same section.

    Without a declared level, numbering is the fallback: a numbered heading
    nests by its own numbering, so a depth-2 heading replaces only the depth-2
    entry and keeps its parent. An unnumbered heading with no declared level
    replaces the whole path, because it makes no claim to be a child of
    anything and inheriting a stale parent would assert a hierarchy the
    document never stated.
    """

    if outline_level is not None and outline_level >= 1:
        return [*path[: outline_level - 1], heading]

    depth = heading_depth(heading)
    if heading_number(heading) is None:
        return [heading]
    return [*path[: depth - 1], heading]


def section_key(section_path: list[str]) -> str:
    """A comparable identity for a section path."""

    return " / ".join(part.strip() for part in section_path if part.strip()).casefold()


def outline_path(text: str) -> tuple[int, ...]:
    """The outline number a clause carries, as a comparable path.

    ``"3.2.1. Annual increase..."`` becomes ``(3, 2, 1)``, which makes
    parent/child a tuple-prefix test rather than string matching. Returns an
    empty tuple when the clause carries no outline number.

    Deliberately reuses `heading_number`, so a clause and a heading are read by
    one parser: a document that numbers its clauses is numbering its structure,
    and two readings of the same convention would eventually disagree.
    """

    number = heading_number(text)
    if not number:
        return ()
    try:
        return tuple(int(part) for part in number.split("."))
    except ValueError:
        return ()


#: Words that point *forward* at material the clause does not itself contain.
#:
#: Domain-neutral by construction: these are English discourse markers, not
#: policy vocabulary. A statute, an HR handbook and a procurement manual all use
#: them and none means anything different by them.
_CATAPHORIC_RE = re.compile(
    r"\b(?:the\s+following|as\s+follows|these\s+are|namely|"
    r"listed\s+below|set\s+out\s+below|below)\b",
    re.IGNORECASE,
)

#: How far back from the colon a marker may sit and still be pointing at it.
#: "…in one of the following cases only:" has two words of tail; a marker forty
#: words earlier in a long paragraph is describing something else.
_PROMISE_TAIL_CHARS = 90


def promises_enumeration(text: str) -> bool:
    """True when a clause promises material that must follow it.

    The generalisation behind enumeration linking: whatever numbering scheme a
    document uses — or none at all — a clause ending "in one of the following
    cases only:" is *incomplete by its own words*. That makes an unsatisfied
    promise a provable extraction failure rather than a matter of taste, and it
    holds for unstructured documents where no outline number exists to follow.

    Two conditions, both required. The clause must end in a colon, which is how
    documents almost universally open an enumeration; and a forward-pointing
    marker must sit close to that colon. Either alone over-fires: a bare
    "Definitions:" heading is a label rather than a promise, and a paragraph
    mentioning "the following" mid-sentence before going on to state its own
    rule is complete.
    """

    stripped = " ".join((text or "").split()).rstrip()
    if not stripped.endswith((":", "：")):
        return False
    tail = stripped[-_PROMISE_TAIL_CHARS:]
    return bool(_CATAPHORIC_RE.search(tail))



def salient_terms(text: str, *, limit: int = 12) -> list[str]:
    """Quoted and Title-Cased phrases that behave like defined vocabulary.

    Used only to *propose* definition relationships and enrichment candidates.
    A false positive costs a reviewer one glance; the alternative — a
    domain-specific term list — would put HR/IT/finance vocabulary into shared
    code, which the architecture forbids.
    """

    terms: list[str] = []
    for pattern in (_QUOTED_TERM_RE, _TITLE_TERM_RE):
        for match in pattern.finditer(text or ""):
            term = " ".join(match.group(1).split()).casefold()
            if len(term) < 4 or term in terms:
                continue
            terms.append(term)
            if len(terms) >= limit:
                return terms
    return terms
