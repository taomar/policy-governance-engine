"""The plan decides; the prose explains. They are read from one reply, separately.

WHAT THIS MODULE IS FOR

A gather returns one object holding two different kinds of thing:

  * **A plan** — the structured claims that decide the outcome: which status was
    reached, which rules were relied on, which values are outstanding, whether
    the reply declined at all.
  * **Prose** — the sentences a reader is shown: the answer, the determination as
    written, the note, the human labels beside each outstanding value.

Before this module the two travelled together as one dictionary, and every
consumer was trusted to read only the half it was entitled to. That is the shape
of defect this repository keeps finding: not a wrong line, but a boundary that
exists in everyone's head and nowhere in the code. A field is added, someone
reads it in the natural place, and a sentence the model wrote is suddenly
deciding a status.

So the boundary is made real here. :func:`plan_from_reply` reads a reply through
a **closed list of structural keys** and returns an object that *cannot* carry a
sentence, because it has no field that could hold one. Whatever the model wrote
in its prose, and however a future field is added beside it, the plan is the same
plan — and the decision is a function of the plan.

WHY THIS IS NOT MERELY TIDINESS

`_decision_from_parsed` already resolved status by comparing one structured field
against another, and its docstring says so. What it could not do was *prove* it.
"No repair reads the prose" was a property of the code as written, re-established
by reading it, and lost the moment someone added a field. With the plan extracted
first, the claim becomes a property of the type: prose is not in the object the
decision is computed from, so it cannot participate in the computation.

That is the difference between a convention and an invariant, and it is the whole
of what M3's split buys.

WHAT IS DELIBERATELY NOT HERE

No second model call. AD-2 described the plan as a separate adjudication stage;
the sampled-bit instability that justified paying for another call was measured
away before this milestone (the status flip stabilised once retrieval was fixed),
so the expensive half of that design is not bought. The *separation* is what
carried the value, and the separation is free: the reply already contains both
halves, and all that was missing was a boundary that reads them apart.

Nothing here decides anything. This module extracts and describes; the decision
stays where it was, so a reader chasing "what makes a case answered" still finds
one place, not two.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: The versioned statement of *what counts as the plan*.
#:
#: Moves when the structural key list moves — when a field starts or stops
#: deciding an outcome. It does not move when a prompt is reworded or a prose
#: field is added, because neither changes what the decision is computed from.
#: Carried on the receipt so a stored decision can say which reading produced it.
PLAN_PROFILE: Final[str] = "case-plan-v1"

#: The keys a reply may state that **decide** the outcome. Closed on purpose: a
#: key absent from this list cannot reach the decision however it is spelled,
#: which is what makes the boundary a property of the code rather than of
#: everyone's memory.
PLAN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "status",
        "declined",
        "cited_rule_ids",
        "missing_required_facts",
        "missing_required_facts_detail",
        "unsettled_reason",
    }
)

#: The keys that are prose. Declared rather than inferred as "everything else",
#: so that a genuinely new *structural* field fails loudly as unclassified
#: instead of being silently treated as decorative — the failure direction that
#: keeps a boundary honest.
PROSE_KEYS: Final[frozenset[str]] = frozenset({"answer", "verdict", "note"})

#: The prose keys whose **presence** is structural even though their content is
#: not. "Did the reply compose an answer at all" and "did it name a verdict at
#: all" are facts about the reply, not sentences in it, and the decision has
#: always turned on them: a state that promises a reader an explanation cannot
#: stand with nothing to show, and `answered` with no verdict string is the one
#: confusion the status vocabulary exists to prevent.
#:
#: The plan therefore carries one boolean per key and never the string. That is
#: the whole distinction: whether the model wrote is structural, what it wrote is
#: not, and no amount of rewording can move a boolean that only counts
#: characters.
PROSE_PRESENCE_KEYS: Final[frozenset[str]] = frozenset({"answer", "verdict"})

#: `missing_required_facts_detail` is the one entry that is both. Its `fact` and
#: `required_by_rule_ids` decide; its `label` and `why_needed` are shown. It is
#: listed in `PLAN_KEYS` because the deciding half is what the plan needs, and
#: the prose half is carried through untouched by the caller that renders it —
#: this module never reads it.
DETAIL_PROSE_FIELDS: Final[frozenset[str]] = frozenset({"label", "why_needed"})


@dataclass(frozen=True, slots=True)
class CasePlan:
    """What a reply claims, with no field that could hold a sentence.

    Every member is a status token, a name, an identifier, or a count of them.
    There is deliberately no ``answer``, no ``verdict`` string and no ``note``:
    not because a caller would misuse them, but so that no caller *can*, and so
    that a test can assert the decision is unchanged when only prose changes.

    The two ``states_*`` booleans are the single concession, and they are a
    concession about *presence*, never content — see :data:`PROSE_PRESENCE_KEYS`.
    """

    #: The status the reply labelled itself with, lowercased and stripped, or ""
    #: when it stated none. Not validated here — whether it is a status this
    #: platform recognises is the decision stage's question, not the plan's.
    status: str = ""
    #: Whether the reply declined outright.
    declined: bool = False
    #: The rule ids the reply says it relied on, unfiltered and in the order it
    #: gave them. Checking them against the closed rule set is the decision
    #: stage's job; the plan reports what was claimed.
    cited_rule_ids: tuple[str, ...] = ()
    #: The outstanding values the reply named, as written, in the order it named
    #: them — the flat field first and then the detail, deduplicated by the exact
    #: text. The union, because each is something the model actually said.
    #:
    #: These are names, not sentences: they are what a follow-up form is keyed
    #: on. Resolving them against the records' declared vocabulary, and folding
    #: two spellings onto one identifier, is the decision stage's work.
    named_facts: tuple[str, ...] = ()
    #: Which kind of non-settlement was reported, if any.
    unsettled_reason: str = ""
    #: Whether the reply composed an answer at all. Presence, never content.
    states_answer: bool = False
    #: Whether the reply named a verdict at all. Presence, never content.
    states_verdict: bool = False

    @property
    def names_a_fact(self) -> bool:
        return bool(self.named_facts)


def plan_from_reply(parsed: dict) -> CasePlan:
    """Read the deciding half of a reply, and only that half.

    Reads by key from :data:`PLAN_KEYS`, plus the emptiness of the two keys in
    :data:`PROSE_PRESENCE_KEYS`. No prose value can leave this function, because
    nothing it returns has anywhere to put one.
    """

    detail = parsed.get("missing_required_facts_detail")
    flat = parsed.get("missing_required_facts")

    named: list[str] = []
    seen: set[str] = set()

    def _note(raw: object) -> None:
        text = str(raw).strip()
        if text and text not in seen:
            seen.add(text)
            named.append(text)

    if isinstance(flat, list):
        for item in flat:
            _note(item)

    if isinstance(detail, list):
        for entry in detail:
            if not isinstance(entry, dict):
                continue
            # `label` is read *only* as a name when there is no `fact`, which is
            # what the pre-split reader did. It is the one place a prose field
            # names a plan member, and it is here rather than hidden because a
            # reply that names its outstanding value in the label and nowhere
            # else has still named it — and a name is not an assertion about the
            # case, so it cannot contradict the plan, only supply it.
            fact = str(entry.get("fact") or "").strip()
            label = str(entry.get("label") or "").strip()
            _note(fact or label)

    cited = parsed.get("cited_rule_ids")
    return CasePlan(
        status=str(parsed.get("status") or "").strip().lower(),
        declined=bool(parsed.get("declined")),
        cited_rule_ids=tuple(str(rule_id) for rule_id in cited) if isinstance(cited, list) else (),
        named_facts=tuple(named),
        unsettled_reason=str(parsed.get("unsettled_reason") or "").strip().lower(),
        states_answer=bool(str(parsed.get("answer") or "").strip()),
        states_verdict=bool(str(parsed.get("verdict") or "").strip()),
    )


def prose_from_reply(parsed: dict) -> dict[str, str]:
    """The half a reader is shown, carried through without being read.

    Returned as its own object so that "what was shown" and "what was decided"
    are two values a caller holds separately, rather than one dictionary a caller
    is trusted to use carefully. Carried verbatim — stripping or rewording here
    would be this layer editing the model's words.
    """

    return {key: str(parsed.get(key) or "") for key in sorted(PROSE_KEYS)}


def unclassified_keys(parsed: dict) -> tuple[str, ...]:
    """Reply keys this module has not placed on either side of the boundary.

    A new field is a decision about whether it decides or describes, and this is
    how that decision is forced to be made explicitly rather than by whichever
    consumer reads it first.
    """

    known = PLAN_KEYS | PROSE_KEYS
    return tuple(sorted(key for key in parsed if key not in known))
