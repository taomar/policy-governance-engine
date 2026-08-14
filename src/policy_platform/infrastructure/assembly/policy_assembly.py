"""Group rules into the policies their source stated, derived on read.

The key is `lineage.source_elements` -- the document element a rule was
formulated from, already recorded per rule so that one rule from a multi-topic
batch cannot appear to come from another rule's clause. A rule citing several
elements is anchored to the first, which is where its subject is introduced.

Chosen over the alternatives because it is the only one that is actually
populated: `payload.clause_id` has no non-null values anywhere, and
`evidence[].source_hash` is a document-level digest with exactly one distinct
value per set, so grouping on it yields a single policy containing everything.
`source_elements` is populated on 1,830 of 1,830 stored rules across all six
policy sets, and agrees with `evidence[i].clause_id` on 2,383 comparisons with
no mismatch.

Not `group_label`: that is a topical cluster the model names, so it can put two
paragraphs together because they are both about leave. This has to answer a
narrower question -- did these rules come from the same passage -- and only
provenance can answer it.

The boundary of the idea, worth stating so nobody later expects more of it:

    Grouping makes a bad slice legible; it doesn't make it a good slice.

Duplicates that read as four unrelated policies become visibly two-plus-two once
grouped -- which is assembly doing its job. It does not repair the slice; it
stops the slice from hiding. Repairing it belongs upstream, in how the document
is segmented and how rules are formulated.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
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
class AssembledRule:
    """One rule as it sits inside its policy, keeping its own route."""

    rule_id: str
    title: str
    #: This rule's own route. Routing is a property of the rule, so it survives
    #: assembly untouched -- the policy summarises its rules and never replaces
    #: them.
    evaluation_mode: EvaluationMode


@dataclass(frozen=True)
class AssembledPolicy:
    """One passage of the source, carrying every rule stated in it."""

    #: The grouping key. Stable across runs because it names the document
    #: element, not the extraction.
    key: str
    #: The rule's full attribution, kept verbatim for display. Differs from
    #: `key` when the rules cite several elements.
    source_elements: str
    page: int | None
    rules: tuple[AssembledRule, ...]

    @property
    def rule_count(self) -> int:
        return len(self.rules)

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


def policy_key(rule: CanonicalRule) -> str:
    """The passage a rule belongs to.

    A rule formulated from several elements is anchored to the first. The
    grouping is presentational, so anchoring is a display choice rather than a
    claim that the later elements are unrelated -- they stay visible in
    `source_elements`.

    A rule with no recorded provenance gets a key of its own rather than
    joining a bucket of other unattributed rules. Two rules that each fail to
    say where they came from have not thereby said they came from the same
    place, and grouping them would manufacture a relationship the document
    never stated.
    """

    for element in rule.lineage.source_elements.split(";"):
        anchor = element.strip()
        if anchor:
            return anchor
    return f"rule:{rule.rule_id}"


def _document_position(key: str) -> tuple[int, str]:
    """Sort policies the way the document reads.

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


def assemble(rules: Sequence[CanonicalRule]) -> list[AssembledPolicy]:
    """Group rules into policies, in document order.

    Every rule that goes in comes out, in exactly one policy. Nothing is
    composed, deleted or reworded; a policy holding one rule is the ordinary
    case and is built the same way as a policy holding nine.
    """

    grouped: dict[str, list[CanonicalRule]] = {}
    for rule in rules:
        grouped.setdefault(policy_key(rule), []).append(rule)

    policies = [
        AssembledPolicy(
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
        for key, members in grouped.items()
    ]
    policies.sort(key=lambda policy: _document_position(policy.key))

    # Assembly is a partition or it is nothing. A dropped rule would silently
    # remove a decision from the review queue, and a duplicated one would show
    # a reviewer the same obligation twice under two headings -- both worse
    # than the fragmentation this exists to fix, and both cheap to rule out.
    assert all(policy.rules for policy in policies), "assembly produced an empty policy"
    placed = [rule.rule_id for policy in policies for rule in policy.rules]
    assert len(placed) == len(rules), "assembly lost or duplicated a rule"

    return policies
