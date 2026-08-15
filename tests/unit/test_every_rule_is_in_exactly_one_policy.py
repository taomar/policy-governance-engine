"""A policy holds every rule its section states, each of them once.

TWO DIRECTIONS, BECAUSE ONE PASSES ON THE WRONG ANSWER

"Every rule is in a policy" passes on an assembly that put every rule in every
policy. "No rule is in two policies" passes on an assembly that produced no
policies at all. Neither is worth anything alone, and the failure the owner
reported four times -- one paragraph arriving as three cards -- is a
*duplication* of the container, which only the pair catches.

THE OBLIGATION THIS ENCODES

    A policy with fourteen rules holds fourteen rules and shows all fourteen.

Not thirteen with the fourteenth "rolled up", not fourteen with one repeated,
and not fourteen behind a control a reviewer has to find. The count on the card
and the rules under it are the same number, and both are the number the
document states.

WHY THE ELEMENT PARTITION IS ASSERTED HERE TOO

A rule can only be in exactly one policy if the elements it cites are. So the
partition over elements is checked directly rather than inferred: if two
provisions ever claimed the same element, this fails at the level where the
cause is, instead of much later as a duplicated rule with no obvious source.
"""
from __future__ import annotations

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import (
    CanonicalRule,
    EvidenceReference,
    RuleLineage,
)
from policy_platform.contracts.provision_grouping import group_into_provisions
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.infrastructure.assembly.policy_assembly import (
    ProvisionGrouping,
    assemble,
)
from tests.fixtures.factories import make_rule

RELEASE = "release-under-test"


def _element(
    element_id: str,
    text: str,
    element_type: str = "paragraph",
    order: int = 0,
    page: int = 1,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=page, start_offset=0, end_offset=len(text), text=text)
        ],
    )


def _provisions(elements: list[CanonicalElement]):
    document = CanonicalDocument(
        document_id="DOC",
        page_count=max({f.page for e in elements for f in e.source_fragments}, default=1),
        pages=[
            CanonicalPage(page=page, raw_text="")
            for page in sorted({f.page for e in elements for f in e.source_fragments})
        ],
        elements=elements,
        parser="docling",
    )
    return group_into_provisions(
        document, build_structural_graph(document), source_release=RELEASE
    )


def _handbook() -> list[CanonicalElement]:
    return [
        _element("H1", "1. Employment", "heading", 0),
        _element("E2", "Contracts begin at the start of the academic year.", "paragraph", 1),
        _element("E3", "A temporary contract is issued otherwise.", "paragraph", 2),
        _element("H4", "1.1 Probation", "heading", 3),
        _element("E5", "Probation lasts ninety days.", "paragraph", 4),
        _element("H6", "2. Leave", "heading", 5),
        _element("E7", "Annual leave is thirty days.", "paragraph", 6),
    ]


class TestEveryElementIsInExactlyOneProvision:
    def test_no_element_is_left_out(self) -> None:
        elements = _handbook()
        placed = {eid for p in _provisions(elements) for eid in p.element_ids}

        assert placed == {element.element_id for element in elements}

    def test_no_element_is_claimed_twice(self) -> None:
        seen = [eid for p in _provisions(_handbook()) for eid in p.element_ids]

        assert len(seen) == len(set(seen))

    def test_a_heading_belongs_to_the_section_it_introduces(self) -> None:
        # Not to the one above it. A heading filed with the preceding section
        # is the cut this grouping exists to prevent, applied to the one
        # element whose whole purpose is to say what comes next.
        by_key = {p.provision_key: p for p in _provisions(_handbook())}
        holding_h4 = [p for p in by_key.values() if "H4" in p.element_ids]

        assert len(holding_h4) == 1
        assert holding_h4[0].heading_path[-1] == "1.1 Probation"
        assert "E5" in holding_h4[0].element_ids


def _rule(rule_id: str, elements: str, *, page: int | None = 1) -> CanonicalRule:
    """A stored rule with the provenance assembly groups on.

    Mirrors the helper in `test_policy_assembly.py`: `make_rule` exposes
    neither lineage nor evidence, and both are what the assembly reads.
    """

    rule = make_rule(rule_id, FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS))
    return rule.model_copy(
        update={
            "title": f"Rule {rule_id}",
            "lineage": RuleLineage(source_elements=elements),
            "evidence": [
                EvidenceReference(document_version_id="dv1", source_hash="h", page=page)
            ],
        }
    )


class TestEveryRuleIsInExactlyOnePolicy:
    """The owner's complaint, as an invariant over the assembly."""

    def _assembled(self, rules, provisions=None):
        return assemble(rules, provisions=provisions)

    def test_two_sentences_of_one_section_make_one_policy(self) -> None:
        # `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES SPONSORSHIP`, in its
        # general form: two consecutive elements, one about a medical test and
        # one about sponsorship cost, previously two cards with one name.
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("7.2. WORK PERMIT",))
        policies = self._assembled(
            [_rule("medical", "p9-E000074"), _rule("sponsorship", "p9-E000075")],
            provisions={"medical": grouping, "sponsorship": grouping},
        )

        assert len(policies) == 1
        assert policies[0].rule_count == 2
        assert {rule.rule_id for rule in policies[0].rules} == {"medical", "sponsorship"}

    def test_every_rule_lands_in_a_policy(self) -> None:
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("1. Employment",))
        other = ProvisionGrouping(
            key="prov-b", provision_id="id-prov-b", heading_path=("2. Leave",))
        rules = [_rule(f"r{i}", f"E{i}") for i in range(6)]
        policies = self._assembled(
            rules,
            provisions={
                rule.rule_id: (grouping if index < 4 else other)
                for index, rule in enumerate(rules)
            },
        )

        placed = {rule.rule_id for policy in policies for rule in policy.rules}
        assert placed == {rule.rule_id for rule in rules}

    def test_no_rule_lands_in_two_policies(self) -> None:
        # CONTROL for the test above, which an assembly that copied every rule
        # into every policy would also pass.
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("1. Employment",))
        other = ProvisionGrouping(
            key="prov-b", provision_id="id-prov-b", heading_path=("2. Leave",))
        rules = [_rule(f"r{i}", f"E{i}") for i in range(6)]
        policies = self._assembled(
            rules,
            provisions={
                rule.rule_id: (grouping if index < 4 else other)
                for index, rule in enumerate(rules)
            },
        )

        placed = [rule.rule_id for policy in policies for rule in policy.rules]
        assert len(placed) == len(set(placed))

    def test_a_policy_of_fourteen_holds_fourteen(self) -> None:
        # "Nothing is lost", stated as the count the card will print beside the
        # rules it will draw. The two are the same number or the card is lying.
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("10. Conduct",))
        rules = [_rule(f"r{i}", f"E{i}") for i in range(14)]
        policies = self._assembled(
            rules, provisions={rule.rule_id: grouping for rule in rules}
        )

        assert len(policies) == 1
        assert policies[0].rule_count == 14
        assert len(policies[0].rules) == 14
        assert sum(len(p.rules) for p in policies[0].passages) == 14

    def test_a_policy_of_one_rule_is_an_ordinary_policy(self) -> None:
        # CONTROL. The ordinary case must go through the same path and come out
        # as a policy, not as a container with one thing in it or as an
        # exception the assembly routes around.
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("3. Dress code",))
        policies = self._assembled([_rule("only", "E1")], provisions={"only": grouping})

        assert len(policies) == 1
        assert policies[0].rule_count == 1
        assert policies[0].rules[0].rule_id == "only"

    def test_a_rule_with_no_provision_still_reaches_a_policy(self) -> None:
        # A document whose structure defeats grouping must still extract and
        # still render. Dropping the rule would be the one unrecoverable
        # outcome: a rule the document states that no reviewer ever sees.
        policies = self._assembled([_rule("orphan", "E1")], provisions={})

        placed = {rule.rule_id for policy in policies for rule in policy.rules}
        assert placed == {"orphan"}

    def test_a_mixed_run_places_grouped_and_ungrouped_rules_alike(self) -> None:
        grouping = ProvisionGrouping(
            key="prov-a", provision_id="id-prov-a", heading_path=("1. Employment",))
        policies = self._assembled(
            [_rule("grouped", "E1"), _rule("loose", "E9")],
            provisions={"grouped": grouping},
        )

        placed = [rule.rule_id for policy in policies for rule in policy.rules]
        assert sorted(placed) == ["grouped", "loose"]
        assert len(placed) == len(set(placed))
