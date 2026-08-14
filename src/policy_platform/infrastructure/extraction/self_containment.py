"""Whether a record's own text supplies the things that record points at.

An `ai_ready` record is decided by a judge reading *it*. That promise is broken
the moment the record's operative wording points at something the record does
not contain: "In the case of absences on that day" states a condition whose
subject — which day — lives in the sentence before it. The record still looks
complete, still carries a condition, and is still routed as decidable, so
nothing downstream ever asks the question a reader asks immediately.

This is a defect in the *extraction*, not in the document and not in the
reading route. The passage is unambiguous where it is written; the slice taken
out of it is what lost the antecedent.

WHY THIS IS NOT A WORD LIST
---------------------------
"that", "such" and "these" are not defects. They are ordinary English, and a
check that flagged them would flag most policy prose and be ignored within a
day. What matters is whether the thing pointed at is *recoverable from this
record*: "during that period" is fine in a record that names the period, and
broken in a record that does not.

So the test has two halves, and both are structural:

1. *Is there a pointer at all?* A demonstrative or anaphoric determiner heading
   a noun phrase — `that day`, `such cases`, `these documents`, `the said
   period`. Recognised only where a noun phrase can begin (start of the field,
   after punctuation, after a preposition, conjunction or subordinator), which
   is what separates the determiner reading from the complementiser ("provided
   **that** the employee applies") and the relative pronoun ("the day **that**
   follows"). Both of those are frequent and neither points anywhere.

2. *Does it resolve here?* The head noun the pointer governs has to occur
   somewhere else in the record's own text. "that period" beside "the probation
   period" resolves; "that day" in a record that never says a day does not.

Recurrence of the head noun is a *sufficient* test for resolution, not a
necessary one — a document may name the antecedent in different words, as the
Saturday/`that day` pair does. That asymmetry is deliberate and it points the
right way: the check reports "this record gives a reader no anchor at all",
which is a claim about the record and can be checked by eye in seconds.

A CUT THAT LOST THE ANTECEDENT IS NOT ONE THAT KEPT IT
------------------------------------------------------
That asymmetry has a consequence, and until it was separated out the check
reported two different conditions as one finding:

1. *The antecedent is outside the record.* The passage this was cut from is a
   single sentence, so nothing precedes the pointer in the record's own
   evidence and no wording of it could resolve. The cut lost the context. This
   is the extraction defect described above and the remedy is upstream.

2. *The antecedent is inside the record but not named again.* The passage
   carries a sentence before the pointer. "The cut off point for late
   attendance is 7:05 AM. After this time, the minutes will be counted as
   tardiness" is the canonical case: `7:05 AM` answers `this time` and is not
   the token `time`. Nothing is wrong with the cut. The reference is opaque to
   a test made of tokens, which is a statement about the test.

Reporting them together makes the measure unable to register the improvement it
exists to drive. Re-cutting a record to pull its antecedent in moves it from (1)
to (2) — a real fix, correctly applied — and under a single finding the count
does not move. That failure is silent, which makes it worse than over-reporting:
a reviewer sees "unchanged" and concludes the fix did not work.

What (2) does *not* claim is that the antecedent is present. It claims only that
the record carries text before the pointer, so the reference may be answered by
wording this check cannot match. Deciding that needs meaning rather than tokens
and is deliberately not attempted here.

A POINTER AT THE DOCUMENT IS NOT A DANGLING ONE
-----------------------------------------------
"This handbook" in a handbook does not stand in for a noun phrase established
earlier in the text. It points outward, at the artefact the reader is holding —
exophoric deixis rather than anaphora — and every record carries its document by
construction. So the thing pointed at is recoverable from the record in the only
sense that matters here: no reader of a record has ever had to ask which
document it came from.

This is also what the extraction prompt specifies. It excludes sentences *about*
the document — its own enactment, approval, effective date, supersession — while
requiring that a sentence which merely names the document while stating a real
rule be extracted, offering "This policy applies to all full-time employees" as
an example to keep. A record arriving here with "this policy" in it is therefore
the prompt working as specified, and a finding against it penalises the system
for obeying its own instructions. A measure that does that will, given enough
revisions, train the instruction out of the system. `test_record_stands_alone`
pins the noun set below to the prompt's own worked examples, so the check and
the specification cannot drift apart quietly.

The exclusion is deliberately narrow, because its risk is the expensive one:
suppressing a real defect. It applies only to a singular `this` or `that`
heading a noun that names a document, never to a plural ("these policies"),
never to `such`, `said`, `these` or `those`, and never to a noun naming content
rather than the artefact. "This card", "these rules", "this stipulation" and
"such circumstances" all still report.

Deliberately out of scope: bare back-pointers with no head noun to look up
("thereof", "the above", "as mentioned"), except in the one case where local
resolution is impossible by construction — nothing precedes them in the record.
Anything more would need discourse structure a single record does not carry,
and a check that guesses is worth less than a narrow one that does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Determiners that make a noun phrase point outside itself. A closed
#: grammatical class, not a vocabulary of suspicious words: every member is a
#: pro-form standing in for a noun phrase established elsewhere.
_ANAPHORIC_DETERMINERS: frozenset[str] = frozenset(
    {
        "this",
        "that",
        "these",
        "those",
        "such",
        "said",
        "aforesaid",
        "aforementioned",
        "abovementioned",
        "foregoing",
        "former",
        "latter",
    }
)

#: Back-pointers carrying no noun to look up. Reported only when nothing at all
#: precedes them in the record, where "resolves locally" is not merely unproven
#: but impossible.
_BARE_BACKPOINTERS: tuple[str, ...] = (
    "as mentioned",
    "as stated above",
    "as described above",
    "as set out above",
    "as noted above",
    "the above",
    "the aforementioned",
    "the foregoing",
    "thereof",
    "therein",
    "thereto",
    "hereinabove",
)

#: Nouns that name the document a record was taken from rather than anything
#: inside it. A pointer at one of these is exophoric: it points at the artefact
#: carrying the record, which every record has by construction, so it resolves
#: without the record having to say anything more.
#:
#: The first group is exactly the set of forms the extraction prompt names when
#: it states what "merely names the document" means, and a test asserts this set
#: still covers every one of them, so a prompt revision that adds a document
#: type fails loudly here instead of quietly reinstating the false positives.
#: The second group the prompt does not name. It is held to nouns that cannot
#: denote a fragment: a handbook has clauses, but no clause is "this handbook".
_THE_DOCUMENT_ITSELF: frozenset[str] = frozenset(
    {
        # Named by the extraction prompt's own worked examples.
        "document",
        "law",
        "policy",
        "agreement",
        "sop",
        "standard",
        # Artefact nouns the prompt happens not to use. Additions belong here
        # only where the noun cannot name a part of a document.
        "handbook",
        "manual",
    }
)

#: Determiners that can head a pointer at the document. Singular only, because
#: "these policies" is a set of things inside the document rather than the
#: document, and `such`/`said` point at content far more often than at the
#: artefact.
_DOCUMENT_DEIXIS_DETERMINERS: frozenset[str] = frozenset({"this", "that"})


#: Tokens that can immediately precede a noun phrase. A demonstrative in any
#: other left context is doing a different job — "provided that ...",
#: "the day that follows", "ensure that ..." — and points at nothing.
_NOUN_PHRASE_OPENERS: frozenset[str] = frozenset(
    {
        "of", "in", "on", "at", "to", "for", "from", "with", "within", "without",
        "during", "after", "before", "by", "upon", "under", "over", "against",
        "between", "among", "per", "about", "into", "through", "throughout",
        "beyond", "across", "toward", "towards", "regarding", "concerning",
        "and", "or", "nor", "but",
        "if", "when", "whenever", "where", "wherever", "while", "unless",
        "until", "because", "although", "though", "whereas", "since",
    }
)

#: Words that cannot be the head of the noun phrase a determiner opens. Closed
#: classes only — articles, possessives, pronouns, auxiliaries, prepositions,
#: conjunctions and quantifiers. Their presence immediately after the
#: determiner means it was not a determiner at all, so no claim is made.
_NOT_A_HEAD_NOUN: frozenset[str] = frozenset(
    {
        "the", "a", "an",
        "his", "her", "its", "their", "our", "your", "my",
        "he", "she", "it", "they", "we", "you", "i", "who", "whom", "whose",
        "which", "what",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "has", "have", "had", "do", "does", "did",
        "will", "shall", "may", "might", "must", "can", "could", "would",
        "should",
        "not", "no", "any", "all", "each", "every", "both", "either", "neither",
        "more", "most", "other", "another", "same", "own",
        "and", "or", "nor", "but", "if", "as", "than", "then", "so",
        "of", "in", "on", "at", "to", "for", "from", "with", "by", "up",
        "this", "that", "these", "those", "such",
    }
)

#: How far past the determiner the head noun may sit. Covers the modifiers a
#: noun phrase routinely carries ("such written notice", "that same working
#: day") without running into the next phrase.
_HEAD_NOUN_WINDOW = 3

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")


@dataclass(frozen=True)
class UnresolvedReferent:
    """One pointer in a record that the record itself does not answer."""

    #: The canonical field the pointer sits in, so a reviewer can see why the
    #: record was routed the way it was rather than take the verdict on trust.
    field: str
    #: The pointer, quoted from the record. Never paraphrased and never
    #: repaired: the record's text is the document's text.
    phrase: str
    #: The noun the pointer governs, or "" for a bare back-pointer.
    head: str
    #: Whether the passage this record was cut from carries a sentence before
    #: the pointer. False means the antecedent cannot be inside the record and
    #: the cut is what lost it; True means the cut kept its context and the
    #: pointer is merely not answered in the same words. Defaults to False so a
    #: caller that supplies no source text gets the louder of the two findings,
    #: never the quieter one.
    source_carries_a_neighbour: bool = False

    def as_reason(self) -> str:
        opener = "opens with" if not self.head else "says"
        if self.source_carries_a_neighbour:
            return (
                f"'{self.field}' {opener} {self.phrase!r}, which the record's own "
                f"evidence does not name again in those words"
            )
        return (
            f"'{self.field}' {opener} {self.phrase!r}, which points back at wording "
            f"this record does not contain"
        )


#: Characters that end a phrase, so a determiner following one begins a new
#: noun phrase regardless of the word before the punctuation.
_PHRASE_BOUNDARY = ",;:.()[]\u2014\u2013-\"'"


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def _spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def _stem(word: str) -> str:
    """Crude number-folding so 'day' matches 'days' and 'policy' 'policies'."""

    lowered = word.casefold()
    if lowered.endswith("ies") and len(lowered) > 4:
        return lowered[:-3] + "y"
    if lowered.endswith("es") and len(lowered) > 3:
        return lowered[:-2]
    if lowered.endswith("s") and len(lowered) > 2:
        return lowered[:-1]
    return lowered


def _noun_phrase_after(
    spans: list[tuple[str, int, int]], index: int, text: str
) -> list[str]:
    """The tokens of the noun phrase a determiner at `index` governs.

    Walks forward while the tokens can still belong to one phrase: it stops at
    the first closed-class word and at the first punctuation mark, because both
    end the phrase. Returning nothing means the determiner was not governing a
    noun phrase at all — "that the employee applies", "this will be explained"
    — and no claim is made about it.
    """

    collected: list[str] = []
    previous_end = spans[index][2]
    for token, start, end in spans[index + 1 : index + 1 + _HEAD_NOUN_WINDOW]:
        if any(ch in _PHRASE_BOUNDARY for ch in text[previous_end:start]):
            break
        if token.casefold() in _NOT_A_HEAD_NOUN:
            break
        collected.append(token)
        previous_end = end
    return collected


def _opens_a_noun_phrase(spans: list[tuple[str, int, int]], index: int, text: str) -> bool:
    """Whether a noun phrase can start at token `index`.

    True at the start of the field, after punctuation, and after a preposition,
    conjunction or subordinator. Anywhere else the demonstrative is doing a
    different job — a complementiser after a verb ("provided that the employee
    applies") or a relative pronoun after a noun ("the day that follows") — and
    points at nothing.
    """

    if index == 0:
        return True
    start = spans[index][1]
    between = text[spans[index - 1][2] : start].strip()
    if any(ch in _PHRASE_BOUNDARY for ch in between):
        return True
    return spans[index - 1][0].casefold() in _NOUN_PHRASE_OPENERS


def _phrase_at(spans: list[tuple[str, int, int]], index: int, length: int, text: str) -> str:
    """The determiner and the noun phrase it governs, quoted from the field."""

    end = spans[index + length][2] if length else spans[index][2]
    return text[spans[index][1] : end]


def _points_at_the_document_itself(determiner: str, phrase_tokens: list[str]) -> bool:
    """Whether the pointer names the document rather than anything inside it.

    All three conditions do work. The determiner must be singular, because
    `such` and `these` head a pointer at content far more often than at the
    artefact. The head must be singular, because "these policies" is a set of
    rules and not the document carrying them. And the noun itself is what
    separates "this handbook", which every record answers, from "this
    stipulation", which only the neighbouring record answers.
    """

    if determiner.casefold() not in _DOCUMENT_DEIXIS_DETERMINERS:
        return False
    head = phrase_tokens[-1].casefold()
    if head != _stem(head):
        return False
    return head in _THE_DOCUMENT_ITSELF


#: A sentence boundary inside an extracted passage: terminal punctuation,
#: whitespace, then the start of something new. Requiring a capital is what
#: separates "7:05 AM. After this time" from "No. 5" and "e.g. the applicant",
#: neither of which ends a sentence. It under-reports on scripts without case,
#: which errs toward the louder finding rather than the quieter one.
_SENTENCE_BREAK = re.compile("[.!?][\"')\\]]?\\s+(?=[\"'(\u201c]?[A-Z])")


def _carries_a_preceding_sentence(source_text: str) -> bool:
    """Whether the passage this record was cut from holds more than one sentence.

    This is the whole discriminator between the two findings, and it is
    deliberately a question about the *cut* rather than about the referent: a
    record whose evidence is one sentence cannot contain the antecedent whatever
    words it uses, and a record carrying a neighbour may well contain it. No
    claim is made about which.
    """

    return bool(_SENTENCE_BREAK.search((source_text or "").strip()))


def unresolved_referents(
    fields: dict[str, str], record_text: str, source_text: str = ""
) -> list[UnresolvedReferent]:
    """Pointers in `fields` that `record_text` does not answer.

    `fields` is the wording whose failure to resolve would matter — the slots a
    reader has to understand to apply the rule. `record_text` is everything the
    record carries, because a referent answered anywhere in the record is
    answered.

    `source_text` is the passage the record was cut from, and it decides which of
    the two findings each pointer is — see "A CUT THAT LOST THE ANTECEDENT IS NOT
    ONE THAT KEPT IT" above. Omitting it reports every pointer as a lost
    antecedent, which is the conservative reading and the one this check made
    before the two conditions were told apart.
    """

    available = [_stem(t) for t in _tokens(record_text)]
    kept_a_neighbour = _carries_a_preceding_sentence(source_text)
    found: list[UnresolvedReferent] = []
    seen: set[tuple[str, str]] = set()

    for field, raw in fields.items():
        text = (raw or "").strip()
        if not text:
            continue
        spans = _spans(text)
        for index, (token, _, _) in enumerate(spans):
            if token.casefold() not in _ANAPHORIC_DETERMINERS:
                continue
            if not _opens_a_noun_phrase(spans, index, text):
                continue
            phrase_tokens = _noun_phrase_after(spans, index, text)
            if not phrase_tokens:
                continue
            # The last token of the phrase is its head; the ones before it are
            # modifiers, and a modifier recurring elsewhere ("written", "same")
            # says nothing about whether the thing itself was named.
            head = phrase_tokens[-1]
            phrase = _phrase_at(spans, index, len(phrase_tokens), text)
            if _points_at_the_document_itself(token, phrase_tokens):
                continue
            if _resolves_locally([token, *phrase_tokens], available):
                continue
            key = (field, phrase.casefold())
            if key in seen:
                continue
            seen.add(key)
            found.append(
                UnresolvedReferent(
                    field=field,
                    phrase=phrase,
                    head=head,
                    source_carries_a_neighbour=kept_a_neighbour,
                )
            )

        bare = _bare_backpointer_at_start(text)
        if bare:
            key = (field, bare.casefold())
            if key not in seen:
                seen.add(key)
                found.append(
                    UnresolvedReferent(
                        field=field,
                        phrase=bare,
                        head="",
                        source_carries_a_neighbour=kept_a_neighbour,
                    )
                )

    return found


def _resolves_locally(phrase_tokens: list[str], available: list[str]) -> bool:
    """Whether the head noun occurs in the record outside the pointer itself.

    The pointer is part of the record, and the record's fields quote the same
    sentence the source text does, so the phrase is normally present several
    times over. Every one of those is discounted — the head is only evidence of
    resolution where it appears somewhere the pointer does not.
    """

    stems = [_stem(token) for token in phrase_tokens]
    head = stems[-1]
    pointers = _subsequence_count(available, stems)
    return available.count(head) > pointers * stems.count(head)


def _subsequence_count(haystack: list[str], needle: list[str]) -> int:
    """How many times `needle` appears contiguously in `haystack`."""

    if not needle or len(needle) > len(haystack):
        return 0
    return sum(
        1
        for start in range(len(haystack) - len(needle) + 1)
        if haystack[start : start + len(needle)] == needle
    )


def _bare_backpointer_at_start(text: str) -> str:
    """A back-pointer with nothing before it in the field to resolve against."""

    lowered = text.casefold().lstrip()
    for marker in _BARE_BACKPOINTERS:
        if lowered.startswith(marker):
            return text.strip()[: len(marker)]
    return ""
