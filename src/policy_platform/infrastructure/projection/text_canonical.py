"""One way to compare two pieces of text, shared by everything that has to.

WHY THIS EXISTS

Several places in this platform ask the same question of two strings: *are these
the same name?* A retrieval score asks it of a question's words against a rule's
words. A missing-fact key asks it of what a gather wrote against what a rule
declared. A selector catalogue asks it of every spelling a record uses for one
thing. Each had its own answer, and the answers disagreed.

They disagreed in a way that was invisible in English and destructive elsewhere,
because two strings a reader would call identical are often different sequences
of code points:

  - ``café`` is one character composed and two decomposed. A comparison that does
    not normalise sees two different words.
  - Arabic carrying tashkeel is the same word as Arabic without it. A tokeniser
    built on ``\\w+`` does not merely fail to match them — the marks are not word
    characters, so it *splits the word* at every mark and produces four fragments
    where there was one word.
  - The same is true, and worse, of Devanagari: the vowel signs that carry the
    word's meaning are spacing marks, so ``कितना`` came apart into ``क`` and
    ``तन`` — a different word, and one that matches nothing.
  - Tatweel stretches an Arabic word for justification and means nothing. Two
    spellings of one word, one stretched, did not match.
  - Fullwidth forms, ligatures and other compatibility spellings are the same
    letters set differently.

Every one of those is a property of Unicode, not of a language, and none of them
is fixed by knowing what the document is about.

WHAT IT DOES, AND WHAT IT REFUSES TO DO

Fold to a normal form, drop what carries no distinction, keep what does, and
treat everything else as a separator:

  1. ``NFKC`` → ``casefold`` → ``NFKC``. The second normalisation is not
     redundant: case folding can itself denormalise, and this is the sequence
     that makes a caseless comparison stable in either direction.
  2. Drop marks that do not occupy space — Unicode categories ``Mn`` and ``Me``.
     These are the optional ones: tashkeel, a decomposed accent, a cantillation
     sign. Dropping them is what lets a pointed word meet its unpointed self.
  3. **Keep** marks that do occupy space — category ``Mc``. This distinction is
     the whole reason step 2 is written by category and not as "drop the marks".
     In Devanagari and its neighbours the spacing marks *are* the vowels; folding
     them away would collapse words that mean different things into one key, and
     collapsing distinct things is a worse failure than failing to match.
  4. Drop code points that exist only to shape or join — see
     :data:`_PRESENTATION_ONLY`.
  5. Keep anything alphanumeric, in any script.
  6. Everything else ends the current run. Runs are then joined by whatever the
     caller needs: a hyphen for a key, or kept apart as a token list.

It carries **no vocabulary**. There is no stop-word list, no stemmer, no
language detection and no branch that asks what script it is looking at. The
only string constants in the module are Unicode identifiers — a normalisation
form and three general-category names — which is a property of the character
table rather than of any document. That is deliberate and is asserted by a test:
a word constant here would be a subject leaking into an identifier, and would
work for one corpus and quietly fail for the next.

WHAT THIS IS NOT, AND WHY THAT MATTERS TO THE TRANSLATION BOUNDARY

This is **not a translation and must never be used as one**. It folds two
spellings of one name onto one identifier; it does not carry a name from one
language into another, and it cannot: ``الساعات`` keys as ``الساعات``.

It is language-neutral for one reason, and it is not the reason it might look
like. It is *not* here so that a question in one language can be matched against
a record in another — nothing here does that, and nothing here should be extended
to. It is here because the text it is given is **stored, authoritative data**: a
record holds its document's sentences verbatim, in whatever language that
document was written in, and those sentences are never rewritten. Whatever
language the pipeline reasons in, this module still has to read what is on disk.

That is also why the keys it produces come out in the document's own script, and
why a translating layer must leave them alone. A key is an identifier: callers
store state against it, compare one reply to the next by it, and resolve it
against a catalogue built from those same records. Translating one would break
every one of those, and would break them silently, because the translated string
still looks like a key.

So the line a translating layer must not cross runs between two kinds of field,
and this module governs exactly one side of it:

  - **identifiers** — a fact key, a catalogue key, an alias key — are produced
    here, are record-derived, and are passed through untouched;
  - **prose** — an answer, an explanation, a human label, a note — is not
    produced here and never passes through here.

Keeping those apart is what makes a translation boundary possible at all. A
layer that cannot tell them apart has to choose between translating identifiers
(and orphaning state) or leaving prose untranslated (and failing the reader).

What language anything is *processed* in is decided above this module and is
deliberately not encoded in it. There is no parameter for it, no default for it,
and no behaviour that changes with it.
"""
from __future__ import annotations

import unicodedata
from typing import Final

#: The normalisation form applied before and after case folding. Compatibility
#: (``K``) as well as canonical, so that fullwidth letters, ligatures and other
#: presentation spellings fold onto the letters they stand for.
_NORMAL_FORM: Final[str] = "NFKC"

#: Marks that occupy no space of their own. They are orthographically optional in
#: the scripts that use them, so a name spelled with them and one spelled without
#: are the same name, and a key that kept them would never match across the two.
_INVISIBLE_MARKS: Final[frozenset[str]] = frozenset({"Mn", "Me"})

#: Marks that *do* occupy space. In several scripts these carry the vowel and
#: therefore the word: dropping them would fold distinct names onto one key. They
#: are kept as part of the run for exactly that reason, which is why steps 2 and 3
#: are two rules rather than one rule about "marks".
_SPACING_MARKS: Final[frozenset[str]] = frozenset({"Mc"})

#: Code points that shape or join what is around them and distinguish nothing on
#: their own. They are neither part of a word nor a break between two words, so
#: they are skipped without ending the run — the alternative would split one name
#: into two.
#:
#: This is a character table, not a vocabulary: each entry is a formatting device
#: with no semantic content of its own, named by code point rather than by the
#: language that happens to use it.
#:
#: - ``U+0640`` stretches a letter to justify a line and means nothing.
#: - ``U+200C``/``U+200D`` control whether neighbouring letters join.
#: - ``U+00AD`` marks where a word *may* be broken if it has to be.
#: - ``U+FEFF`` is a byte-order mark that survives a careless decode.
_PRESENTATION_ONLY: Final[frozenset[str]] = frozenset(
    {"\u0640", "\u200c", "\u200d", "\u00ad", "\ufeff"}
)

#: What :func:`canonical_key` puts between runs. A single character, so a key
#: never carries a run of them and two keys cannot differ by spacing alone.
KEY_SEPARATOR: Final[str] = "-"


def fold(value: object) -> str:
    """Normalise and case-fold, with nothing removed yet.

    Separated from :func:`canonical_runs` so that the normalisation sequence has
    one home: a caller that needs the folded text without the character rules —
    or a test that needs to prove the sequence is what it claims — does not have
    to repeat it and risk repeating it differently.
    """

    text = unicodedata.normalize(_NORMAL_FORM, str(value or "").strip())
    return unicodedata.normalize(_NORMAL_FORM, text.casefold())


def canonical_runs(value: object) -> list[str]:
    """The canonical word-runs of ``value``, in order.

    This is the one scan every other function here is built from, so there is
    exactly one place where the character rules live and no way for two callers
    to disagree about them.
    """

    runs: list[str] = []
    current: list[str] = []

    for char in fold(value):
        if char in _PRESENTATION_ONLY:
            # Invisible and joining: skipped without ending the run, so a
            # stretched or explicitly joined spelling keys as one word.
            continue
        category = unicodedata.category(char)
        if category in _INVISIBLE_MARKS:
            continue
        if char.isalnum() or category in _SPACING_MARKS:
            current.append(char)
            continue
        if current:
            runs.append("".join(current))
            current = []

    if current:
        runs.append("".join(current))
    return runs


def canonical_key(value: object, *, separator: str = KEY_SEPARATOR) -> str:
    """A stable identifier for one name.

    Empty when the value carries nothing that distinguishes it — a string of
    punctuation, or of marks with no letters. The caller decides what to do about
    that; returning a separator or a placeholder here would hand every such value
    the same identifier, which is the collision this whole module exists to
    prevent.
    """

    return separator.join(canonical_runs(value))


def canonical_tokens(value: object, *, min_chars: int = 1) -> list[str]:
    """The canonical runs as tokens, dropping any shorter than ``min_chars``.

    ``min_chars`` is a floor on how much a token can distinguish, not a stop-word
    list: it carries no language's vocabulary and applies the same way to every
    script.
    """

    return [run for run in canonical_runs(value) if len(run) >= min_chars]
