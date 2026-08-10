"""Deciding which clauses continue which, when the document does not say.

A policy statement is frequently split across clauses. A governing stem opens
it — "salary shall be increased … in one of the following cases only:" — and
enumerated clauses complete it. Extracted separately and left unlinked, the stem
becomes a rule asserting an exhaustive limit with nothing to limit it to, and
each case becomes a rule with no idea what it is a case *of*. Both are wrong in
the dangerous direction: they look complete.

Documents signal this in descending order of reliability, and this module tries
them in that order rather than reaching for the model first:

1. **Docling list structure** — the document literally encodes parent and level.
   Free and exact. Absent whenever numbering was typed by hand rather than
   applied as a Word list, which is most policy documents in practice.
2. **Outline numbering** — ``3.2.1`` is a child of ``3.2``. Free and exact when
   the numbering is present and consistent.
3. **Cataphoric promise** — a clause ending "…the following:" is incomplete by
   its own words. Free, and independent of numbering, but only catches the
   phrasings the marker list knows.
4. **Model adjudication** — this module. Used only for clauses the first three
   left unresolved, because a model call per clause window is the expensive
   option and the least auditable.

The discipline that makes tier 4 admissible: the model must **quote the source**
for every link it proposes. The quote is checked verbatim against the parent
clause, and a link whose quote does not appear stays a ``candidate`` regardless
of how confident the model was. A model asserting a relationship is an opinion;
a model pointing at the words that establish it is evidence, and only the second
may enter ``related_rule_ids``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from policy_platform.contracts.relationships import (
    PolicyRelationship,
    PolicyRelationshipType,
    RelationshipEvidence,
)
from policy_platform.infrastructure import source_structure

logger = logging.getLogger(__name__)

#: Clauses per model call. Large enough that a stem and its cases fall in one
#: window — a stem separated from its last case by more than this cannot be
#: linked by this tier at all — and small enough to keep the prompt reviewable.
WINDOW_SIZE = 12

#: Characters of each clause shown to the model. Enough to carry the stem's
#: trailing promise and the case's opening, without paying for whole pages.
CLAUSE_PREVIEW_CHARS = 400

PROMPT_VERSION = "continuation-v1"

_SYSTEM_PROMPT = """You identify which policy clauses continue which.

A GOVERNING clause opens a statement it does not finish: it promises cases,
conditions or items that appear in later clauses. A CONTINUATION clause
completes a governing clause — it is one of the promised cases, and read alone
it does not say what it is a case of.

Return JSON only:

{"links": [{"parent": "<element id>", "child": "<element id>",
            "quote": "<verbatim text from the PARENT clause that shows it is
                       incomplete and expects continuation>"}]}

Rules you must follow:
- `quote` MUST be copied character-for-character from the parent clause text as
  given. Do not paraphrase, correct, translate or re-punctuate it. A quote that
  does not appear in the parent will be rejected.
- Quote the part of the parent that does the promising, not the whole clause.
- Only link a child to a parent that is genuinely incomplete without it. Two
  complete, adjacent rules about the same topic are NOT a parent and child.
- A clause that merely mentions a related subject is not a continuation.
- If nothing in the window is a continuation, return {"links": []}. Returning
  nothing is correct and expected for ordinary prose.
"""


@dataclass(frozen=True)
class ClauseWindow:
    """One clause as the adjudicator sees it."""

    element_id: str
    rule_id: str
    text: str


def _prompt_for(window: list[ClauseWindow]) -> str:
    lines = []
    for item in window:
        preview = " ".join(item.text.split())[:CLAUSE_PREVIEW_CHARS]
        lines.append(f"[{item.element_id}] {preview}")
    return "\n\n".join(lines)


def _verify_quote(quote: str, parent_text: str) -> bool:
    """Whether the model's quote actually appears in the parent clause.

    Compared on collapsed whitespace only. Line breaks differ between the stored
    clause text and any rendering of it, and rejecting a correct quote because a
    newline became a space would push honest links into `candidate` and teach
    nobody anything. Every other character must match: this is the check that
    separates a citation from an assertion.
    """

    if not quote or not parent_text:
        return False
    normalized_quote = " ".join(quote.split())
    normalized_parent = " ".join(parent_text.split())
    if len(normalized_quote) < 8:
        # Too short to be evidence of anything — "the following" alone appears
        # in most documents and would verify against the wrong clause.
        return False
    return normalized_quote in normalized_parent


def unresolved_clauses(
    windows: list[ClauseWindow], resolved_element_ids: set[str]
) -> list[ClauseWindow]:
    """Clauses the deterministic tiers did not place.

    Also drops clauses that are complete on their own reading — a clause with no
    outline number, no promise, and a terminal full stop is ordinary prose, and
    paying for a model opinion about it buys nothing.
    """

    remaining: list[ClauseWindow] = []
    for item in windows:
        if item.element_id in resolved_element_ids:
            continue
        remaining.append(item)
    return remaining


def should_adjudicate(window: list[ClauseWindow]) -> bool:
    """Whether a window is worth a model call.

    A window with no plausible governing clause cannot yield a link, so calling
    the model over it spends money to be told nothing. "Plausible" is read
    generously here — an unterminated clause counts — because tier 4 exists
    precisely for the phrasings tiers 1-3 do not recognise.
    """

    for item in window:
        text = " ".join((item.text or "").split())
        if not text:
            continue
        if source_structure.promises_enumeration(text):
            return True
        # An unterminated clause is the format-independent hint: policy prose
        # ends in a full stop, and one that does not is usually the opening
        # half of something.
        if not text.endswith((".", "。", "!", "?")):
            return True
    return False


async def adjudicate_window(
    client,
    settings,
    window: list[ClauseWindow],
) -> list[PolicyRelationship]:
    """Ask the model which clauses continue which, and verify what it says."""

    by_id = {item.element_id: item for item in window}
    raw = await client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _prompt_for(window)},
        ],
        deployment=settings.azure_openai_deployment,
        response_format={"type": "json_object"},
    )
    payload = json.loads(raw)

    edges: list[PolicyRelationship] = []
    for link in payload.get("links", []):
        parent_id = str(link.get("parent") or "")
        child_id = str(link.get("child") or "")
        quote = str(link.get("quote") or "")
        parent = by_id.get(parent_id)
        child = by_id.get(child_id)
        if parent is None or child is None or parent_id == child_id:
            # A link naming a clause outside the window cannot be checked, so it
            # cannot be trusted.
            continue

        verified = _verify_quote(quote, parent.text)
        edges.append(
            PolicyRelationship(
                relationship_type=PolicyRelationshipType.SAME_DECISION,
                source_rule_id=parent.rule_id,
                target_rule_id=child.rule_id,
                source_element_id=parent.element_id,
                target_element_id=child.element_id,
                evidence=RelationshipEvidence(
                    signals=["model_adjudicated"] + (["verified_quote"] if verified else []),
                    score=0.9 if verified else 0.4,
                    source_quote=quote if verified else "",
                    detail=(
                        "the model quoted the parent's own promise"
                        if verified
                        else "the model's quote could not be found in the parent clause"
                    ),
                ),
                origin="model",
                # The whole point of the tier: a verified quote is evidence a
                # reviewer can check against the document, so it may act like
                # structure. An unverified one is the model's word, and stays a
                # proposal.
                state="confirmed" if verified else "candidate",
            )
        )
    return edges


async def discover_continuations(
    client,
    settings,
    clauses: list[ClauseWindow],
    resolved_element_ids: set[str] | None = None,
) -> list[PolicyRelationship]:
    """Adjudicate every window the deterministic tiers left unresolved."""

    remaining = unresolved_clauses(clauses, resolved_element_ids or set())
    edges: list[PolicyRelationship] = []
    for start in range(0, len(remaining), WINDOW_SIZE):
        window = remaining[start : start + WINDOW_SIZE]
        if len(window) < 2 or not should_adjudicate(window):
            continue
        try:
            edges.extend(await adjudicate_window(client, settings, window))
        except Exception:
            # One bad window must not cost the run its other links. Adjudication
            # is the last tier, so a failure here degrades to the structure the
            # earlier tiers already found.
            logger.exception("continuation adjudication failed for window at %d", start)
    return edges
