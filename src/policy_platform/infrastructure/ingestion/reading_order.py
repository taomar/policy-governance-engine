"""Recover logical (reading) order from glyphs recorded in visual (paint) order.

WHY THIS EXISTS
---------------
A PDF does not store a document's words. It stores instructions to paint glyphs
at coordinates. For a left-to-right script the two coincide, so reading the
glyphs left to right recovers the text. For a right-to-left script they do not:
the producer already ran the Unicode Bidirectional Algorithm (UBA, UAX #9) to
turn the author's *logical* character sequence into a *visual* one, and it is
the visual one that reaches the page.

Reading such a page left to right therefore yields a character sequence the
document does not contain. It looks like text, it has the right letters, and it
is not the document's words. Everything downstream — extraction, evidence,
verbatim validation — then quotes something nobody wrote.

This module performs the inverse of the UBA's reordering step (UAX #9 rule L2)
using the one piece of information a text extractor has that a plain string does
not: the coordinate of every glyph.

WHAT IT MUST NEVER DO
---------------------
Reverse a string. Reversing a right-to-left line does make its prose read
correctly, and it silently destroys every number in it, because a number is a
left-to-right sub-run embedded inside a right-to-left run: "50%" becomes "05%".
In a document whose operative content is quantities that is worse than the
original defect, because the prose now looks repaired.

Ordering is therefore always done by coordinate, and always *within* a
directional run, never across one.

HOW IT WORKS
------------
1. Each glyph is assigned a Unicode bidirectional character class
   (``unicodedata.bidirectional``). This is a property of the character, so the
   same code serves Arabic, Hebrew, Farsi, Urdu, Thaana, Syriac and a single
   foreign term quoted inside English. Nothing here inspects language, script,
   locale, or the identity of the document.
2. Weak and neutral classes are resolved against their neighbours, following the
   UBA's W and N rules.
3. Each glyph gets an embedding level (UBA rules I1/I2): even levels read left
   to right, odd levels read right to left.
4. Glyphs are arranged by level: a run at an even level is ordered by ascending
   x, a run at an odd level by descending x, and a higher-level run nested
   inside a lower one is placed as a unit and ordered internally by its own
   direction. That is the inverse of L2, expressed as coordinate comparisons.
5. Glyphs placed at an odd level are un-mirrored (the inverse of UBA rule L4):
   the glyph painted as "(" at the left edge of a right-to-left number is the
   display form of a logical ")".

WHERE IT IS APPROXIMATE
-----------------------
The UBA's W rules are defined over the logical sequence, which is precisely what
is not yet known. They are applied here over the visual sequence, using both
neighbours rather than only the preceding one. The rules that matter in practice
(a separator between two digits; a currency or percent sign against a number; a
neutral between two runs of the same direction) are symmetric, so this is exact
for them. UBA W2 — a European number takes Arabic-number type after a preceding
Arabic letter — is deliberately not applied: it cannot be evaluated without
logical order, and it has no effect on ordering, because rules I1 and I2 give
European and Arabic numbers the same embedding level.

Paragraph direction (UBA rules P2/P3) is the direction of the first strong
character in logical order, which is likewise not yet known. It is taken from
the strong characters at the two visual ends when they agree — they do for any
line that is wholly one direction, and for a right-to-left line ending in a
left-to-right quotation — and from the dominant strong class when they do not.
The ambiguity is inherent: a left-to-right line ending in a foreign phrase and a
right-to-left line opening with one are painted identically.

UBA W7 — a European number takes left-to-right type when the nearest preceding
strong character is left-to-right — is applied symmetrically here, against the
nearest strong character on either side. Without it a comma inside a Latin
phrase quoted in a right-to-left line resolves to right-to-left and splits the
phrase in two, which then gets re-sequenced.

Finally, one extracted visual line is not always one passage. A layout can set
two independently composed regions side by side on the same baseline — two table
cells, or two columns — and a text extractor reports them as a single line. When
the text on either side of a gap wide enough to be such a boundary is dominantly
of *different* directions, the two sides are ordered separately, because they
were composed separately. A wide gap within text of a single direction changes
nothing, so an indent, a tab stop or justified spacing is never mistaken for a
boundary.

A source with no right-to-left characters at all is returned untouched, so a
document in a left-to-right script is not merely unchanged in practice but
unchanged by construction.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

__all__ = ["Glyph", "has_rtl", "logical_order", "normalize_presentation_forms"]

#: Bidirectional classes that make a character strongly right-to-left, plus the
#: Arabic-number class. Their absence means visual order already is logical
#: order and there is nothing to recover.
_RTL_CLASSES = frozenset({"R", "AL", "AN"})
_STRONG_LTR = "L"
_STRONG_RTL = frozenset({"R", "AL"})
_NUMBER_CLASSES = frozenset({"EN", "AN"})
_NEUTRAL_CLASSES = frozenset({"B", "S", "WS", "ON"})
#: Explicit formatting and boundary-neutral characters. They carry no glyph and
#: are dropped by the parser before this module sees anything, but a stray one
#: must not be treated as strong.
_IGNORED_CLASSES = frozenset({"BN", "LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"})

#: Compatibility decomposition tags that mark a *contextual presentation form* —
#: a glyph variant chosen for its position in a word rather than a distinct
#: character. Normalising these is lossless: the decomposition is the letter the
#: author typed. Every other tag is excluded, which is why the Latin "fi"
#: ligature (tag ``<compat>``), a superscript digit (``<super>``) and a
#: no-break space (``<noBreak>``) survive untouched.
_PRESENTATION_TAGS = ("<isolated>", "<initial>", "<medial>", "<final>")

#: A horizontal gap at least this wide, in the source's own units, is not a word
#: space at any ordinary body size — it is where the page's layout set two
#: independently composed regions beside each other, such as two table cells or
#: two columns. It is consulted only to decide whether a direction change across
#: such a gap is a change of *context* rather than a directional run inside one
#: passage, so a wide gap within text of a single direction has no effect.
_CONTEXT_GAP_POINTS = 16.0

#: Mirrored pairs whose names do not differ only by LEFT/RIGHT, so they cannot
#: be derived by name substitution. Unicode character data, not a script list.
_EXPLICIT_MIRRORS = {
    "<": ">",
    "\u2264": "\u2265",  # ≤ ≥
    "\u2266": "\u2267",
    "\u226A": "\u226B",  # ≪ ≫
    "\u2208": "\u220B",  # ∈ ∋
    "\u2209": "\u220C",
    "\u220A": "\u220D",
    "\u2282": "\u2283",  # ⊂ ⊃
    "\u2284": "\u2285",
    "\u2286": "\u2287",  # ⊆ ⊇
    "\u2288": "\u2289",
    "\u227A": "\u227B",  # ≺ ≻
    "\u2264\uFE00": "\u2265\uFE00",
}


@dataclass(frozen=True)
class Glyph:
    """One painted character and where it was painted.

    ``group`` identifies the token the glyph came from, so a separator can be
    re-inserted between tokens after reordering without inventing one inside a
    token. It is opaque to this module.
    """

    text: str
    x0: float
    x1: float
    group: int = 0


def has_rtl(text: str) -> bool:
    """Whether any character in ``text`` is of a right-to-left class."""

    return any(unicodedata.bidirectional(char) in _RTL_CLASSES for char in text)


def paint_order_is_visual(glyphs: list[Glyph]) -> bool | None:
    """Decide, from the file itself, whether these glyphs were painted visually.

    Recovering reading order is only correct if the producer actually ran the
    Unicode Bidirectional Algorithm before painting. Mainstream producers do,
    but that is an assumption about the tool rather than evidence from the
    document, and a source that paints a right-to-left run left to right in
    logical order would be *corrupted* by reordering it. So the question is
    asked of the file rather than assumed.

    Some scripts answer it directly. Their letters take a different form
    according to where they sit in a word, and Unicode records which form each
    codepoint is via its decomposition tag: a word runs ``<initial>`` then
    ``<medial>`` then ``<final>``. Reading the glyphs by ascending x therefore
    settles it — ``<final>`` before ``<initial>`` means the word was painted
    right to left, and the reverse means it was painted in logical order.

    This is a property of the characters present, not of any language: it holds
    for every script that shapes positionally, and it is silent for every script
    that does not. Returns ``None`` when the source carries no such evidence,
    which is a genuine "cannot be determined from this file" rather than a no --
    a bare run in an unshaped script is painted identically either way, and the
    caller must decide what to do without evidence rather than be told a guess.
    """

    by_group: dict[int, list[Glyph]] = {}
    for glyph in glyphs:
        by_group.setdefault(glyph.group, []).append(glyph)

    score = 0
    for group in by_group.values():
        tags = [
            (index, _positional_tag(glyph.text))
            for index, glyph in enumerate(sorted(group, key=lambda item: item.x0))
        ]
        initials = [index for index, tag in tags if tag == "<initial>"]
        finals = [index for index, tag in tags if tag == "<final>"]
        if not initials or not finals:
            continue
        if min(initials) > min(finals):
            score += 1
        elif min(initials) < min(finals):
            score -= 1
    if score == 0:
        return None
    return score > 0


def _positional_tag(char: str) -> str | None:
    parts = unicodedata.decomposition(char).split()
    if parts and parts[0] in _PRESENTATION_TAGS:
        return parts[0]
    return None


def logical_order(glyphs: list[Glyph]) -> list[Glyph]:
    """Return ``glyphs`` in the order the document's author wrote them.

    ``glyphs`` may be given in any order; only the coordinates are trusted.
    Input containing no right-to-left character is returned in ascending x,
    which is what visual order already means for such a source.

    Glyphs are only rearranged where the source shows it was painted in visual
    order (see :func:`paint_order_is_visual`). Where the file carries no
    evidence either way, they are returned in ascending x untouched, because
    reordering text that was already stored correctly would corrupt it just as
    surely as leaving reversed text alone.

    A run of glyphs painted on one visual line is not necessarily one passage:
    a table row or a two-column page puts independently composed regions side
    by side, and they can be composed in opposite directions. Where a wide
    horizontal gap separates regions whose direction differs, each is resolved
    against its own paragraph direction, because applying one region's direction
    to the other is what turns an intact Latin phrase into a scrambled one.
    """

    if not glyphs:
        return []

    visual = sorted(glyphs, key=lambda glyph: (glyph.x0, glyph.x1))

    if not any(unicodedata.bidirectional(glyph.text) in _RTL_CLASSES for glyph in visual):
        return visual

    if paint_order_is_visual(visual) is not True:
        return visual

    ordered: list[Glyph] = []
    for segment in _context_segments(visual):
        ordered.extend(_order_segment(segment))
    return ordered


def _order_segment(visual: list[Glyph]) -> list[Glyph]:
    """Resolve one passage: glyphs sharing a single paragraph direction."""

    classes = [unicodedata.bidirectional(glyph.text) or "L" for glyph in visual]
    base_rtl = _base_is_rtl(classes)
    base_level = 1 if base_rtl else 0
    resolved = _resolve_classes(classes, base_rtl)
    levels = _levels(resolved, base_level=base_level)

    xs = [glyph.x0 for glyph in visual]
    ordered = _arrange(list(range(len(visual))), levels, xs, level=base_level)
    return [_place(visual[index], levels[index]) for index in ordered]


def _context_segments(visual: list[Glyph]) -> list[list[Glyph]]:
    """Split a visual line where layout, not language, changed the direction.

    Splitting happens only where both conditions hold: a gap too wide to be a
    word space, and a different dominant direction on each side. A wide gap
    inside text of a single direction therefore has no effect, which matters
    because an indent, a tab stop or a justified line would otherwise be torn
    into pieces and reassembled in the wrong order.
    """

    chunks: list[list[Glyph]] = [[visual[0]]]
    for previous, glyph in zip(visual, visual[1:]):
        if glyph.x0 - previous.x1 >= _CONTEXT_GAP_POINTS:
            chunks.append([glyph])
        else:
            chunks[-1].append(glyph)

    segments: list[list[Glyph]] = []
    directions: list[str | None] = []
    for chunk in chunks:
        direction = _dominant_direction(chunk)
        if segments and (direction is None or directions[-1] is None or direction == directions[-1]):
            segments[-1].extend(chunk)
            directions[-1] = directions[-1] or direction
        else:
            segments.append(list(chunk))
            directions.append(direction)
    return segments


def _dominant_direction(glyphs: list[Glyph]) -> str | None:
    """Which direction the strong characters of a chunk agree on, if any."""

    ltr = rtl = 0
    for glyph in glyphs:
        cls = unicodedata.bidirectional(glyph.text)
        if cls == _STRONG_LTR:
            ltr += 1
        elif cls in _STRONG_RTL:
            rtl += 1
    if not ltr and not rtl:
        return None
    return "R" if rtl > ltr else "L"


def normalize_presentation_forms(text: str) -> str:
    """Replace contextual presentation forms with the letters they present.

    Applied per character and only to characters whose Unicode decomposition
    marks them as a positional variant, so this cannot alter a character that
    merely has some other compatibility mapping. A ligature that presents two
    letters expands to those two letters, in their own logical order.
    """

    if not any(_is_presentation_form(char) for char in text):
        return text
    return "".join(
        unicodedata.normalize("NFKC", char) if _is_presentation_form(char) else char
        for char in text
    )


def _is_presentation_form(char: str) -> bool:
    return unicodedata.decomposition(char).startswith(_PRESENTATION_TAGS)


def _base_is_rtl(classes: list[str]) -> bool:
    """Paragraph direction (UBA P2/P3), inferred from a visually ordered line.

    The first strong character in logical order sits at whichever visual end the
    paragraph starts from, so when the strong characters at the two ends agree
    the answer is exact. When they disagree the source is genuinely ambiguous
    and the dominant strong class decides.
    """

    strong = [cls for cls in classes if cls == _STRONG_LTR or cls in _STRONG_RTL]
    if not strong:
        return False
    leading_rtl = strong[0] in _STRONG_RTL
    trailing_rtl = strong[-1] in _STRONG_RTL
    if leading_rtl == trailing_rtl:
        return leading_rtl
    rtl_count = sum(1 for cls in strong if cls in _STRONG_RTL)
    return rtl_count * 2 > len(strong)


def _resolve_classes(classes: list[str], base_rtl: bool) -> list[str]:
    """Reduce weak and neutral classes to L, R, AL, EN or AN (UBA W and N rules)."""

    resolved = list(classes)
    count = len(resolved)

    # W1: a non-spacing mark takes the class of the character it attaches to.
    for index in range(count):
        if resolved[index] != "NSM":
            continue
        neighbour = _nearest(resolved, index, lambda cls: cls != "NSM")
        resolved[index] = neighbour or ("R" if base_rtl else "L")

    for index in range(count):
        if resolved[index] in _IGNORED_CLASSES:
            resolved[index] = "ON"

    # W4: a single separator between two numbers of one type joins them, which
    # is what keeps "1,250" and "31/12" and "3.5" from being torn into pieces.
    for index in range(1, count - 1):
        cls = resolved[index]
        if cls not in ("ES", "CS"):
            continue
        before, after = resolved[index - 1], resolved[index + 1]
        if before == "EN" and after == "EN":
            resolved[index] = "EN"
        elif cls == "CS" and before == "AN" and after == "AN":
            resolved[index] = "AN"

    # W5: a run of terminators next to a European number joins it, which is what
    # keeps a percent sign, a currency symbol or a degree sign with its quantity.
    for index in range(count):
        if resolved[index] != "ET":
            continue
        span = [index]
        cursor = index + 1
        while cursor < count and resolved[cursor] == "ET":
            span.append(cursor)
            cursor += 1
        before = resolved[span[0] - 1] if span[0] > 0 else None
        after = resolved[cursor] if cursor < count else None
        if before == "EN" or after == "EN":
            for position in span:
                resolved[position] = "EN"

    # W6: any terminator or separator that did not join a number is neutral.
    for index in range(count):
        if resolved[index] in ("ET", "ES", "CS"):
            resolved[index] = "ON"

    # W7: a European number whose nearest strong neighbour is left-to-right is
    # itself left-to-right. This is what keeps "15" in "for work, 15 minutes"
    # part of the Latin phrase instead of becoming an island that splits it.
    strong = [
        (index, cls)
        for index, cls in enumerate(resolved)
        if cls == _STRONG_LTR or cls in _STRONG_RTL
    ]
    if strong:
        for index in range(count):
            if resolved[index] != "EN":
                continue
            nearest = min(strong, key=lambda item: (abs(item[0] - index), item[0] > index))
            if nearest[1] == _STRONG_LTR:
                resolved[index] = _STRONG_LTR

    # N1/N2: a neutral between two runs of the same direction joins them.
    # Numbers count as right-to-left for this purpose, per N1, which is what
    # keeps a bracket around a number attached to the surrounding right-to-left
    # text. Where a neutral has a resolved direction on only one side it takes
    # that side rather than the paragraph direction: the end of an extracted
    # visual line is where the parser cut, not necessarily where a paragraph
    # ended, so the one known neighbour is better evidence than a base direction
    # inferred for the line as a whole.
    base = "R" if base_rtl else "L"
    directions = ["R" if cls in _STRONG_RTL or cls in _NUMBER_CLASSES else cls for cls in resolved]
    for index in range(count):
        if resolved[index] not in _NEUTRAL_CLASSES:
            continue
        before = _nearest(directions, index, lambda cls: cls in ("L", "R"), forward=False)
        after = _nearest(directions, index, lambda cls: cls in ("L", "R"), forward=True)
        if before is not None and after is not None:
            resolved[index] = before if before == after else base
        else:
            resolved[index] = before or after or base

    return resolved


def _nearest(values: list[str], index: int, predicate, forward: bool | None = None) -> str | None:
    """The closest neighbouring value satisfying ``predicate``.

    ``forward`` restricts the search to one side; the default searches to the
    left first and then to the right.
    """

    if forward is not True:
        cursor = index - 1
        while cursor >= 0:
            if predicate(values[cursor]):
                return values[cursor]
            cursor -= 1
        if forward is False:
            return None
    cursor = index + 1
    while cursor < len(values):
        if predicate(values[cursor]):
            return values[cursor]
        cursor += 1
    return None


def _levels(resolved: list[str], base_level: int) -> list[int]:
    """Embedding level per character (UBA I1/I2).

    Even levels read left to right, odd levels right to left. Numbers always sit
    two levels above an even base and one above an odd one, which is exactly why
    a quantity inside right-to-left prose keeps its own direction.
    """

    levels: list[int] = []
    for cls in resolved:
        if base_level % 2 == 0:
            if cls in _STRONG_RTL:
                levels.append(base_level + 1)
            elif cls in _NUMBER_CLASSES:
                levels.append(base_level + 2)
            else:
                levels.append(base_level)
        else:
            if cls in _STRONG_RTL:
                levels.append(base_level)
            else:
                levels.append(base_level + 1)
    return levels


def _arrange(indices: list[int], levels: list[int], xs: list[float], level: int) -> list[int]:
    """Order one embedding level by coordinate, recursing into nested runs.

    ``indices`` arrive in ascending x. A maximal stretch of characters above
    ``level`` is a nested run: it is placed as a single unit at this level, at
    its own leftmost coordinate, and ordered internally by its own direction.
    Everything at this level is then ordered by ascending x if the level is
    even, descending if it is odd.

    No sequence is reversed. Order is decided by comparing coordinates, which is
    both the inverse of UBA rule L2 and robust to glyphs that are not laid out
    monotonically.
    """

    nodes: list[tuple[float, list[int]]] = []
    cursor = 0
    while cursor < len(indices):
        if levels[indices[cursor]] > level:
            end = cursor
            while end < len(indices) and levels[indices[end]] > level:
                end += 1
            nested = indices[cursor:end]
            anchor = min(xs[index] for index in nested)
            nodes.append((anchor, _arrange(nested, levels, xs, level + 1)))
            cursor = end
        else:
            nodes.append((xs[indices[cursor]], [indices[cursor]]))
            cursor += 1

    nodes.sort(key=lambda node: node[0], reverse=level % 2 == 1)
    return [index for _, node in nodes for index in node]


def _place(glyph: Glyph, level: int) -> Glyph:
    """Undo the display mirroring a right-to-left level applies (UBA L4)."""

    if level % 2 == 0 or not unicodedata.mirrored(glyph.text):
        return glyph
    mirrored = _mirror(glyph.text)
    if mirrored == glyph.text:
        return glyph
    return Glyph(text=mirrored, x0=glyph.x0, x1=glyph.x1, group=glyph.group)


def _mirror(char: str) -> str:
    explicit = _EXPLICIT_MIRRORS.get(char)
    if explicit:
        return explicit
    for source, target in _EXPLICIT_MIRRORS.items():
        if char == target:
            return source
    try:
        name = unicodedata.name(char)
    except ValueError:
        return char
    if "LEFT" in name and "RIGHT" not in name:
        candidate = name.replace("LEFT", "RIGHT")
    elif "RIGHT" in name and "LEFT" not in name:
        candidate = name.replace("RIGHT", "LEFT")
    else:
        return char
    try:
        return unicodedata.lookup(candidate)
    except KeyError:
        return char
