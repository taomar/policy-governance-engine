"""Group rules into the policies their source stated.

THE GROUPING IS NOW THE PIPELINE'S, AND THIS IS THE FALLBACK

Extraction records which provision of the document states each rule
(`candidate_rules.provision_id`, written at step 13a), and the caller passes
that down as `provisions`. That is the grouping. It persists, so approval,
export and every other consumer see the same policies a reviewer does, rather
than each rebuilding a grouping of its own.

What remains here is the read-time derivation, kept for rules that carry no
link: extracted before provisions existed, or from a document whose structure
defeated grouping. Removing it would make those rules unreviewable, which is a
worse failure than grouping them by a coarser signal.

THE FALLBACK KEY IS THE HEADING

A policy is a numbered section of the document, and the passages beneath it are
its rules. `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES SPONSORSHIP` states
that a medical test is needed and that the employee pays half the transfer cost;
those are two sentences of one policy about work permits, and a reviewer decides
them together or not at all.

The key was `lineage.source_elements` -- the document element a rule was
formulated from -- and that is a strictly narrower question: it can join rules
stated in one sentence and can never join a policy stated across several. Two
consecutive elements under one heading came back as two cards bearing the same
name, which is the fragmentation this module exists to remove, one level up.

MEASURED

On the AIS handbook, 279 rules sit in 155 passages under 38 headings; on GMU,
413 rules in 187 passages under 32 headings. Every stored rule carries a
section -- 0 of 279 and 0 of 413 lack one -- so there is no orphan bucket in
practice, though silence is still handled below rather than assumed away.

Passages per heading are mostly 2 to 4, which is exactly the case the element
key could not reach. The largest is `Table of Violations and Penalties`: 72
rules across 50 passages. That is not a catch-all -- it is a disciplinary
schedule, one policy with a row per offence -- but 72 rules in one flat list is
not a workload a reviewer can hold, which is why the passage boundary below is
load-bearing rather than decorative.

WHAT ASSEMBLY MAY NOT DO

Grouping adds a container and takes nothing away. Rules keep their own id,
their own route, their own condition and outcome; a policy of fourteen rules
shows fourteen. And the passage boundary survives inside the policy, because a
reviewer reading a long card needs to see which sentence each rule came from --
so a policy is a sequence of passages, each holding its own rules, rather than
one flat list that has forgotten where its members were stated.

Not `group_label`: that is a topical cluster the model names, so it can put two
paragraphs together because they are both about leave. The heading is the
document's own structure, recorded per rule as evidence, and it says where a
rule sits rather than what a model thought it was about.

The boundary of the idea, worth stating so nobody later expects more of it:

    Grouping makes a bad slice legible; it doesn't make it a good slice.

Duplicates that read as four unrelated policies become visibly two-plus-two once
grouped -- which is assembly doing its job. It does not repair the slice; it
stops the slice from hiding. Repairing it belongs upstream, in how the document
is segmented and how rules are formulated.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from policy_platform.contracts.policy import CanonicalRule, EvaluationMode, evaluation_mode_for

#: How a policy is decided, given how its rules are.
#:
#: `mixed` is an ordinary and expected outcome, not a degraded one: "thirty days
#: annual leave" is a computable comparison and "subject to Immigration rules"
#: is decided by a judge reading it, and one paragraph can state both. A policy
#: is `deterministic` only when every one of its rules is.
PolicyRoute = Literal["deterministic", "mixed", "ai_ready"]

_ELEMENT_ORDER = re.compile(r"E(\d+)\s*$")


@dataclass(frozen=True)
class ProvisionGrouping:
    """The persisted policy a rule was linked to when it was extracted.

    Supplied by the caller rather than looked up here, so this module stays a
    pure function of the rules it is given and remains testable without a
    database. Absent for a rule extracted before provisions existed, or for one
    whose document defeated grouping; those take the heading fallback below.
    """

    key: str
    #: The persisted row's identity. Carried so the policy can state which
    #: provision it is, and so the reference the flat candidate list already
    #: sends resolves to a policy on this page without either side deriving
    #: anything. A plain value: this dataclass still touches no database.
    provision_id: str
    #: The governing headings, outermost first, exactly as the document wrote
    #: them. Carried so the card can be named by its own heading rather than by
    #: a sentence taken out of one of its passages.
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class AssembledRule:
    """One rule as it sits inside its policy, keeping its own route."""

    rule_id: str
    title: str
    #: This rule's own route. Routing is a property of the rule, so it survives
    #: assembly untouched -- the policy summarises its rules and never replaces
    #: them.
    evaluation_mode: EvaluationMode


@dataclass(frozen=True)
class AssembledPassage:
    """One passage of the source, carrying the rules stated in it.

    The unit the previous key grouped on, kept as the inner boundary of a
    policy. It is what tells a reviewer which words a rule came from, and
    dissolving it into a flat list of fourteen rules would answer the owner's
    complaint by creating a smaller version of it.
    """

    #: The anchoring element, e.g. `p9-E000074`.
    key: str
    #: The rules' full attribution, kept verbatim. Differs from `key` when the
    #: rules cite several elements.
    source_elements: str
    page: int | None
    rules: tuple[AssembledRule, ...]

    @property
    def rule_count(self) -> int:
        return len(self.rules)


@dataclass(frozen=True)
class AssembledPolicy:
    """One section of the source, carrying every passage stated under it."""

    #: The grouping key: the heading, exactly as the document wrote it. Stable
    #: across runs because it names the document's structure, not the
    #: extraction.
    key: str
    #: The document this heading belongs to. Two documents in one set may use
    #: the same heading and are not thereby stating one policy, so the grouping
    #: is scoped by version even though the key displayed is the heading alone.
    document_version_id: str | None
    page: int | None
    passages: tuple[AssembledPassage, ...]
    #: The governing headings, outermost first, verbatim. A persisted provision
    #: carries the whole chain; the fallback knows only the innermost heading
    #: its rules cite, so it carries that one. Empty only when the document
    #: recorded no heading at all -- which is the one case where this policy has
    #: no name of its own, and the client has to say so rather than print the
    #: element id it was keyed by.
    heading_path: tuple[str, ...] = ()
    #: Whether this policy is the one the pipeline recorded, or one derived at
    #: read time from the headings its rules cite. Reported rather than hidden:
    #: a reviewer approving a policy is entitled to know whether its boundary is
    #: stored or inferred.
    persisted: bool = False
    #: The persisted row this policy is, when it is one. Present exactly when
    #: `persisted` is true. It is what the flat candidate list's `provision_id`
    #: points at, so a client holding both lists resolves rule to policy by
    #: identity — never by matching headings, which is the derivation this
    #: field exists to make unnecessary.
    provision_id: str | None = None

    @property
    def heading(self) -> str:
        """What to call this policy: its own innermost heading, quoted whole.

        The card *is* the section, so it is named by the section's heading and
        never by a sentence lifted out of one of its passages. Naming a card by
        its first passage's opening statement was correct while a card was a
        passage; under this grouping it would take one of fourteen sentences and
        present it as the name of all fourteen.

        Empty when the document recorded no heading, and empty rather than the
        key. The key is then an element id, and `p9-E000074` is not a name -- a
        client shown one would print it as though the document had written it.
        Saying nothing lets the client say it found nothing.
        """

        if self.heading_path:
            return self.heading_path[-1]
        return ""

    @property
    def rules(self) -> tuple[AssembledRule, ...]:
        """Every rule under this heading, in the order the document states it."""

        return tuple(rule for passage in self.passages for rule in passage.rules)

    @property
    def rule_count(self) -> int:
        return len(self.rules)

    @property
    def passage_count(self) -> int:
        return len(self.passages)

    @property
    def source_elements(self) -> str:
        """The passages under this heading, in document order."""

        return "; ".join(passage.key for passage in self.passages)

    @property
    def route(self) -> PolicyRoute:
        """Summarise the routes of the rules without discarding any of them.

        A reader asking "can this policy be decided by comparison alone" is
        asking about all of it, so one rule stated in words makes the answer
        `mixed` -- both routes are live and both are served.
        """

        modes = {rule.evaluation_mode for rule in self.rules}
        if modes == {EvaluationMode.DETERMINISTIC}:
            return "deterministic"
        if modes == {EvaluationMode.AI_READY}:
            return "ai_ready"
        return "mixed"


def passage_key(rule: CanonicalRule) -> str:
    """The passage a rule was formulated from.

    A rule formulated from several elements is anchored to the first, which is
    where its subject is introduced. The later elements stay visible in
    `source_elements`.
    """

    for element in rule.lineage.source_elements.split(";"):
        anchor = element.strip()
        if anchor:
            return anchor
    return f"rule:{rule.rule_id}"


def _heading(rule: CanonicalRule) -> str:
    """The section a rule sits under, as its evidence recorded it."""

    for reference in rule.evidence:
        section = (reference.section or "").strip()
        if section:
            return section
    return ""


def _document_version(rule: CanonicalRule) -> str | None:
    for reference in rule.evidence:
        if reference.document_version_id:
            return str(reference.document_version_id)
    return None


def policy_key(rule: CanonicalRule) -> str:
    """The policy a rule belongs to: the heading it sits under.

    A rule whose evidence records no heading falls back to its own passage
    rather than joining a bucket of other unattributed rules. Two rules that
    each fail to say where they came from have not thereby said they came from
    the same place, and grouping them would manufacture a relationship the
    document never stated. No stored rule in the corpus takes this path.
    """

    return _heading(rule) or passage_key(rule)


def _document_position(key: str) -> tuple[int, str]:
    """Sort by where the document first states this.

    Element ids are allocated in document order, so the trailing number orders
    passages across pages without having to parse the page prefix -- which is
    itself a range on elements spanning a page break (`p5-6-E000050`).
    """

    match = _ELEMENT_ORDER.search(key)
    if match is None:
        return (2**31, key)
    return (int(match.group(1)), key)


def _page(rules: Sequence[CanonicalRule]) -> int | None:
    pages = [
        reference.page
        for rule in rules
        for reference in rule.evidence
        if reference.page is not None
    ]
    return min(pages) if pages else None


def _assemble_passage(key: str, members: Sequence[CanonicalRule]) -> AssembledPassage:
    return AssembledPassage(
        key=key,
        source_elements=members[0].lineage.source_elements,
        page=_page(members),
        rules=tuple(
            AssembledRule(
                rule_id=member.rule_id,
                title=member.title,
                evaluation_mode=evaluation_mode_for(member),
            )
            for member in members
        ),
    )


def assemble(
    rules: Sequence[CanonicalRule],
    *,
    provisions: Mapping[str, ProvisionGrouping] | None = None,
) -> list[AssembledPolicy]:
    """Group rules into policies, in document order.

    Every rule that goes in comes out, in exactly one policy and exactly one
    passage of it. Nothing is composed, deleted or reworded; a policy holding
    one rule is the ordinary case and is built the same way as a policy holding
    seventy-two.

    `provisions` maps a rule id to the policy the pipeline recorded for it. When
    supplied, that is the grouping — the heading fallback below is used only for
    rules it does not cover, which is what keeps a document extracted before
    provisions existed reviewable at all.

    The two groupings are kept separate rather than reconciled. A persisted
    provision and a read-time heading are different claims: the first is a fact
    about the document's structure recorded when it was read, the second is an
    inference from what each rule happened to cite. Mixing them into one bucket
    would let a rule whose link is missing silently join a policy it was never
    filed under.
    """

    lookup = provisions or {}
    grouped: dict[tuple[str | None, str], dict[str, list[CanonicalRule]]] = {}
    for rule in rules:
        provision = lookup.get(rule.rule_id)
        key = provision.key if provision is not None else policy_key(rule)
        policy = grouped.setdefault((_document_version(rule), key), {})
        policy.setdefault(passage_key(rule), []).append(rule)

    policies: list[AssembledPolicy] = []
    for (version, key), passages in grouped.items():
        assembled = tuple(
            sorted(
                (_assemble_passage(passage, members) for passage, members in passages.items()),
                key=lambda passage: _document_position(passage.key),
            )
        )
        pages = [passage.page for passage in assembled if passage.page is not None]
        first_rule = passages[assembled[0].key][0]
        provision = lookup.get(first_rule.rule_id)
        if provision is not None:
            heading_path = provision.heading_path
        else:
            # The fallback knows one heading, not a chain, so it claims one. An
            # empty tuple here means the document recorded no heading for these
            # rules, and that is a different statement from "the chain is short".
            recorded = _heading(first_rule)
            heading_path = (recorded,) if recorded else ()
        policies.append(
            AssembledPolicy(
                key=key,
                document_version_id=version,
                page=min(pages) if pages else None,
                passages=assembled,
                heading_path=heading_path,
                persisted=provision is not None,
                provision_id=provision.provision_id if provision is not None else None,
            )
        )
    policies.sort(key=lambda policy: _document_position(policy.passages[0].key))

    # Assembly is a partition or it is nothing. A dropped rule would silently
    # remove a decision from the review queue, and a duplicated one would show
    # a reviewer the same obligation twice under two headings -- both worse
    # than the fragmentation this exists to fix, and both cheap to rule out.
    assert all(policy.passages for policy in policies), "assembly produced an empty policy"
    assert all(
        passage.rules for policy in policies for passage in policy.passages
    ), "assembly produced an empty passage"
    placed = [rule.rule_id for policy in policies for rule in policy.rules]
    assert len(placed) == len(rules), "assembly lost or duplicated a rule"

    return policies
