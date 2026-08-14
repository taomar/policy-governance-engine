"""Records that are fragments of one decision rather than decisions of their own.

The dual of `self_containment`. That module asks whether a record carries
*enough* of its sentence to be decided alone; this one asks whether several
records carry *the same* decision between them, each holding a piece.

    One record per DECISION the source states — not per clause, per condition,
    per grammatical constituent, and not per list item unless each item carries
    its own distinct obligation.

A single obligation with several occasions, or several objects, is one decision
whose condition or object carries them all. Two obligations on different
subjects or actions are two decisions, and splitting those is correct.

WHAT MAKES IT ONE DECISION
--------------------------
The obligation is *who must do what*: subject, predicate, modality, and the
rule type that classifies them. Records agreeing on all four, drawn from one
source sentence, are asserting one obligation. Whatever else they differ in —
a date, an object, an occasion — is an instance of that obligation, not a
second one.

This is why "employees must submit X and managers must approve Y" is never
reported: the subjects differ and the predicates differ, so nothing groups. The
signal is deliberately blind to *how many* fragments there are and to what the
differing values say, because both are properties of the document rather than
of the extraction.

WHAT THIS MODULE DELIBERATELY DOES NOT REPORT
---------------------------------------------
Fragments that are identical in every field are not a split — they are the same
reading stored twice, which `_duplicate_extraction_findings` already reports and
recommends a different remedy for. A family whose members share one
decomposition is therefore left alone here.

Nor is a *ladder*: records whose outcome varies together with the case that
selects it. "A breach draws a warning on the first occasion and suspension on
the second" is one obligation the document states across two occasions, and a
record per occasion is how the source states it. Each such record says which
case it covers and what follows, so a reader can decide it alone — the whole
requirement this module protects. Reporting a ladder would point a reviewer at
the document rather than the extraction.

The distinction is that both halves must vary. A varying outcome alone is the
defect: several outcomes with nothing to say which applies. A varying selector
alone is the same defect from the other side: one outcome cut across occasions
that a single condition should have carried. What remains reported is the case
nothing else sees: one obligation, several fragments, each carrying a piece and
none of them saying when it is the piece that applies.

A QUALIFIER PROMOTED TO A RULE
-----------------------------
A second shape, reported separately because the remedy differs. A relative
clause, an apposition or a trailing predicate qualifies the thing it hangs off;
it does not state a decision of its own. Split out, it becomes a record whose
subject is that thing:

    "all employees undergo an ongoing performance evaluation process, which is
     officially documented once a year"

The obligation is on the employees. That the process is documented annually is
a property of the process, and belongs in the record that names it. Cut apart,
the second record's subject is a *process*, and no case is ever about a
process, so nothing can ever be decided from it.

The signature is structural, not semantic: one record's subject is, verbatim,
another record's object, and both were cut from one sentence. No judgement
about what the words mean is involved, which is why it generalises.

What it cannot tell apart is a genuine hand-off — "the manager notifies the
employee, and the employee must respond" has the same shape and is two real
obligations. Distinguishing those needs to know that an employee is a party and
a process is not, which is a fact about vocabulary rather than about structure.
So this reports a shape for a reviewer to judge; it does not assert a defect.

NOT A MERGE
-----------
Nothing here rewrites, combines or supersedes a record. Merging fragments would
manufacture a statement no single sentence of the document makes, which is the
failure this platform exists to prevent. The output is a family, a reason and a
list of ids: enough for a reviewer to see the whole decision at once and decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: What identifies the decision. Not a sample of fields that happened to work:
#: these four are the whole of "who must do what", and every other canonical
#: field qualifies an obligation rather than constituting one.
_OBLIGATION_FIELDS: tuple[str, ...] = ("rule_type", "subject", "modality", "predicate")

#: Fields that carry an *instance* of the obligation — which thing, which
#: occasion, which limit. A family differing only in these is one decision.
#: `source_origin` is excluded: it records how a field was derived, not what
#: the rule says, so two records differing only there differ in nothing.
_INSTANCE_FIELDS: tuple[str, ...] = (
    "object",
    "actor",
    "beneficiary",
    "candidate",
    "recipient",
    "assigner",
    "trigger",
    "condition",
    "constraint",
    "threshold",
    "temporal_constraint",
    "frequency",
    "deadline",
    "location",
    "exception",
    "prerequisite",
    "sequence",
    "consequence",
    "remedy",
    "calculation",
    "unit",
    "currency",
)

#: Instance fields that say *which case a record covers*. They are what lets a
#: reader hold two records of one obligation and tell which applies. Fields
#: outside this set qualify an obligation without selecting between instances
#: of it.
_SELECTING_FIELDS: frozenset[str] = frozenset(
    {
        "trigger",
        "condition",
        "temporal_constraint",
        "frequency",
        "prerequisite",
        "location",
    }
)

#: The field that carries what the obligation lands on. A family varies its
#: outcome when this differs.
_OUTCOME_FIELD = "object"


@dataclass(frozen=True)
class FamilyMember:
    """One record, reduced to what family membership depends on."""

    rule_id: str
    #: The source sentence, verbatim. Two records only belong to one family if
    #: the document states them in one breath; agreeing on an obligation across
    #: two sentences is a document saying the same thing twice, not a split.
    sentence: str
    #: The canonical rule. Read by attribute name so this module stays usable
    #: from anywhere holding one, without a second adapter.
    core: Any


@dataclass(frozen=True)
class DecisionFamily:
    """Several records that state one decision between them."""

    sentence: str
    rule_ids: tuple[str, ...]
    #: The instance fields the members disagree on, in canonical field order.
    #: This is the finding's evidence — it names what was cut apart.
    varying: tuple[str, ...]

    def as_reason(self) -> str:
        fields = ", ".join(self.varying)
        return (
            f"{len(self.rule_ids)} records state one obligation and differ only in "
            f"{fields}"
        )


@dataclass(frozen=True)
class PromotedQualifier:
    """A record made about a thing another record's obligation lands on."""

    sentence: str
    #: The records stating the obligation, whose object names the thing. More
    #: than one when the sentence was cut into several that all act on it.
    antecedent_rule_ids: tuple[str, ...]
    #: The record that was cut out of the qualifier and made about that thing.
    qualifier_rule_id: str
    #: The shared noun phrase, in the wording the records use.
    phrase: str

    def as_reason(self) -> str:
        holders = ", ".join(self.antecedent_rule_ids)
        return (
            f"its subject is {self.phrase!r}, which is what the obligation in "
            f"{holders} already lands on"
        )


def _value(core: Any, name: str) -> str:
    raw = core.get(name) if isinstance(core, Mapping) else getattr(core, name, None)
    if raw is None:
        return ""
    text = getattr(raw, "value", raw)
    return text.strip().casefold() if isinstance(text, str) else str(text).strip().casefold()


def _display(core: Any, name: str) -> str:
    """The field as written, for a reason a reviewer reads."""

    raw = core.get(name) if isinstance(core, Mapping) else getattr(core, name, None)
    if raw is None:
        return ""
    text = getattr(raw, "value", raw)
    return text.strip() if isinstance(text, str) else str(text).strip()


def _obligation(core: Any) -> tuple[str, ...]:
    return tuple(_value(core, name) for name in _OBLIGATION_FIELDS)


def _instance(core: Any) -> tuple[str, ...]:
    return tuple(_value(core, name) for name in _INSTANCE_FIELDS)


def decision_families(members: Sequence[FamilyMember]) -> list[DecisionFamily]:
    """Families whose members are fragments of one decision.

    A family qualifies when its members share a sentence and an obligation, and
    at least two of them differ somewhere. Members that are identical
    throughout are duplicates rather than fragments and are reported elsewhere,
    so a family that turns out to be entirely duplicates yields nothing here.
    """

    grouped: dict[tuple[str, tuple[str, ...]], list[FamilyMember]] = {}
    for member in members:
        sentence = (member.sentence or "").strip()
        if not sentence or member.core is None:
            continue
        obligation = _obligation(member.core)
        if not any(obligation):
            # Nothing was decomposed, so nothing was asserted to be one
            # obligation. Grouping on emptiness would collect unrelated wrecks.
            continue
        grouped.setdefault((sentence, obligation), []).append(member)

    families: list[DecisionFamily] = []
    for (sentence, _), group in grouped.items():
        if len(group) < 2:
            continue
        varying = _varying_fields(group)
        if not varying:
            # One reading stored more than once. A different defect with a
            # different remedy, and already reported.
            continue
        if _is_a_ladder(varying):
            continue
        families.append(
            DecisionFamily(
                sentence=sentence,
                rule_ids=tuple(member.rule_id for member in group),
                varying=varying,
            )
        )
    return families


def _is_a_ladder(varying: Sequence[str]) -> bool:
    """Whether the members' outcomes are selected by the case each one covers.

    Both halves are required. A varying outcome on its own is the defect this
    module exists to report: several outcomes with nothing to say which
    applies. A varying selector on its own is the other half of the same
    defect: one outcome split across the occasions that should have been
    carried together in a single condition.

    Varying *together* is neither. Each record then states the case it covers
    and the outcome that follows, which is a reader's whole requirement for
    deciding it alone. The document states the obligation that way and the
    extraction preserved it, so there is nothing here to send a reviewer to.
    """

    return _OUTCOME_FIELD in varying and any(name in _SELECTING_FIELDS for name in varying)


def promoted_qualifiers(members: Sequence[FamilyMember]) -> list[PromotedQualifier]:
    """Records made about a thing that another record's obligation lands on.

    Grouped by sentence, as families are: a subject matching an object across
    two sentences is the document reusing a noun, not a decision cut in two.

    A record is never reported against itself. A rule whose subject and object
    are the same phrase says something reflexive; it is not a promotion.

    One report per record made about the thing, naming every record that acts
    on it. A sentence cut into several that all land on one noun would
    otherwise raise a report per pairing, and a reviewer would read the same
    defect four times.
    """

    grouped: dict[str, list[FamilyMember]] = {}
    for member in members:
        sentence = (member.sentence or "").strip()
        if not sentence or member.core is None:
            continue
        grouped.setdefault(sentence, []).append(member)

    promotions: list[PromotedQualifier] = []
    for sentence, group in grouped.items():
        if len(group) < 2:
            continue
        holders: dict[str, list[FamilyMember]] = {}
        for member in group:
            landed_on = _value(member.core, _OUTCOME_FIELD)
            # A record whose object repeats its own subject says nothing about
            # a second thing. It is malformed on its own account, and pairing
            # two of them would report each as the other's qualifier.
            if landed_on and landed_on != _value(member.core, "subject"):
                holders.setdefault(landed_on, []).append(member)

        for member in group:
            subject = _value(member.core, "subject")
            if not subject or subject == _value(member.core, _OUTCOME_FIELD):
                continue
            antecedents = tuple(
                holder.rule_id
                for holder in holders.get(subject, [])
                if holder.rule_id != member.rule_id
            )
            if not antecedents:
                continue
            promotions.append(
                PromotedQualifier(
                    sentence=sentence,
                    antecedent_rule_ids=antecedents,
                    qualifier_rule_id=member.rule_id,
                    phrase=_display(member.core, "subject"),
                )
            )
    return promotions


def _varying_fields(group: Iterable[FamilyMember]) -> tuple[str, ...]:
    """The instance fields on which a family's members disagree."""

    members = list(group)
    varying = []
    for position, name in enumerate(_INSTANCE_FIELDS):
        values = {_instance(member.core)[position] for member in members}
        if len(values) > 1:
            varying.append(name)
    return tuple(varying)
