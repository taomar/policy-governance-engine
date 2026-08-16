"""One rule_id is one rule on the draft surface, even with two live records.

WHY THIS EXISTS

A card in the review queue read `10 rules · 6 decide what happens · 4 supply
meanings` and drew one rule twice, byte-identical, while the published surface
read 9 and was clean. The cause was not a rule stated in two passages. It was
one `rule_id` carried by two live candidate *records* -- a published reading of
a provision and a later re-extraction of the same provision, which share the id
because it is a hash of the rule's logic, not of its prose. The draft path
lists every live record, so `assemble` received the id twice and counted,
listed and drew it twice. The published path passes one record per rule_id, so
it never saw the duplication.

`policyCards` trusts `policy.rule_count` as the denominator it renders against
(so a filter, a page and a stale assembly all read the same way), which is why
this has to be true at the server: a client that deduped locally would print
"9 of 10", implying a rule was filtered out, and invent a phantom hidden row.
The header, the flat list and each passage therefore have to be once per
rule_id here, or the card cannot be truthful without the client lying.

THE REPRESENTATIVE CHOICE, MADE DELIBERATELY

Two records for one rule differ only in prose (their logic, and so their route,
is identical -- the id is a hash of that logic). Collapsing them is not a set
operation but a choice of which reading represents the rule. The rule kept is
the first in document order. A duplicate can only be a later re-extraction of a
rule that already existed, so the earlier record is the incumbent: the reading
that has had the chance to be reviewed and published, and the one the published
surface already shows -- keeping it makes the two surfaces agree. The later
re-extraction's differing prose is not shown here; which reading a reviewer
should act on when the two disagree is a review affordance the producer is
routing separately, and is deliberately not decided by swapping the shown
sentence underneath them.

CONSTRAINT 1

The invariants are relationships -- listed == distinct, header == rows,
partition preserved -- never an observed count. No `9` or `10` appears below;
the only counts asserted are of the fixture's own records.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import CanonicalRule, EvidenceReference, RuleLineage
from policy_platform.infrastructure.assembly.policy_assembly import ProvisionGrouping, assemble
from tests.fixtures.factories import make_rule

# The passage the duplicated rule sits in, and two others in the same policy so
# the collapse is shown to be per rule_id rather than per passage.
_SHARED_PASSAGE = "p4-E000007"
_ALPHA_PASSAGE = "p4-E000006"
_GAMMA_PASSAGE = "p4-E000008"

_SHARED_ID = "R-shared"
_INCUMBENT_TITLE = "the reading already published"
_REEXTRACTION_TITLE = "a later re-extraction, worded differently"

_PREFACE = ProvisionGrouping(
    key="prov-preface", provision_id="id-prov-preface", heading_path=("Preface",)
)


def _record(rule_id: str, elements: str, title: str) -> CanonicalRule:
    """One stored candidate record, carrying the provenance assembly reads.

    `make_rule` sets neither lineage nor evidence, and both are what the
    grouping keys on, so they are copied in here the way the sibling assembly
    tests do it.
    """

    rule = make_rule(rule_id, FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS))
    return rule.model_copy(
        update={
            "title": title,
            "lineage": RuleLineage(source_elements=elements),
            "evidence": [EvidenceReference(document_version_id="dv1", source_hash="h", page=1)],
        }
    )


def _one_policy(records: list[CanonicalRule]):
    # Every record maps to the one provision, keyed by rule_id exactly as
    # `provision_groupings` produces it -- which is why a second record with no
    # provision_id of its own still lands in the same policy.
    provisions = {record.rule_id: _PREFACE for record in records}
    policies = assemble(records, provisions=provisions)
    assert len(policies) == 1, "the fixture is one provision and should be one policy"
    return policies[0]


class TestARuleWithTwoRecordsIsOneRule:
    """The queue counts and draws a shared rule_id once, like the published surface."""

    def _records_with_a_duplicate(self) -> list[CanonicalRule]:
        # Incumbent first, re-extraction second: the order the draft caller
        # supplies (candidates in creation order), and the order that makes the
        # earlier record the one kept.
        return [
            _record(_SHARED_ID, _SHARED_PASSAGE, _INCUMBENT_TITLE),
            _record(_SHARED_ID, _SHARED_PASSAGE, _REEXTRACTION_TITLE),
            _record("R-alpha", _SHARED_PASSAGE, "alpha, a distinct rule in the same passage"),
            _record("R-gamma", _GAMMA_PASSAGE, "gamma, a distinct rule elsewhere"),
        ]

    def test_the_flat_list_holds_each_rule_id_once(self) -> None:
        records = self._records_with_a_duplicate()
        policy = _one_policy(records)

        listed = [rule.rule_id for rule in policy.rules]
        assert len(listed) == len(set(listed)), "a rule_id was listed more than once"
        assert set(listed) == {record.rule_id for record in records}, "a rule was lost or invented"

    def test_the_header_count_matches_the_rules_it_lists(self) -> None:
        # The denominator the client renders against. If it exceeds the distinct
        # rules under it, every card built from it is off by the duplication.
        policy = _one_policy(self._records_with_a_duplicate())

        assert policy.rule_count == len(policy.rules)
        assert policy.rule_count == len({rule.rule_id for rule in policy.rules})

    def test_each_passage_lists_a_rule_once(self) -> None:
        policy = _one_policy(self._records_with_a_duplicate())

        for passage in policy.passages:
            in_passage = [rule.rule_id for rule in passage.rules]
            assert len(in_passage) == len(set(in_passage)), f"{passage.key} drew a rule twice"

    def test_the_incumbent_reading_is_the_one_kept(self) -> None:
        # The representative choice, pinned: the earlier record's prose remains,
        # the later re-extraction's does not. Getting this wrong would show the
        # reviewer the unreviewed sentence while the count looked right.
        policy = _one_policy(self._records_with_a_duplicate())

        kept = [rule for rule in policy.rules if rule.rule_id == _SHARED_ID]
        assert len(kept) == 1
        assert kept[0].title == _INCUMBENT_TITLE

    def test_distinct_rules_are_left_whole(self) -> None:
        # CONTROL. The collapse must key on rule_id and nothing else: rules that
        # merely share a passage, a title shape or a route are still separate
        # rules and must all survive. An over-eager dedupe would pass the tests
        # above by dropping rules it should have kept.
        records = [
            _record("R-1", _ALPHA_PASSAGE, "first"),
            _record("R-2", _ALPHA_PASSAGE, "second"),
            _record("R-3", _SHARED_PASSAGE, "third"),
        ]
        policy = _one_policy(records)

        listed = [rule.rule_id for rule in policy.rules]
        assert len(listed) == len(records), "a distinct rule was dropped"
        assert set(listed) == {record.rule_id for record in records}
