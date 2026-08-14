"""Assembly puts rules back under the passage that stated them.

The defect these cover: a paragraph stating three obligations produced three
policy cards, so a reviewer met the same passage three times and could not see
that the three belonged together. The rules were right; the container was
missing. So every test here checks that assembly *adds* a grouping and takes
nothing away -- no rule dropped, no rule duplicated, no text composed, and no
rule's own route replaced by its policy's summary of it.
"""

from __future__ import annotations

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import (
    CanonicalRule,
    EvaluationMode,
    EvidenceReference,
    RequiredFact,
    RuleLineage,
)
from policy_platform.infrastructure.assembly.policy_assembly import (
    AssembledPolicy,
    assemble,
    policy_key,
)
from tests.fixtures.factories import make_rule

_TEST = FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS)


def _rule(rule_id: str, elements: str, *, deterministic: bool = False, title: str | None = None) -> CanonicalRule:
    """A stored rule with the provenance assembly groups on.

    `make_rule` exposes neither lineage nor required_facts, and the second is
    what decides the route, so both arrive by copy.
    """

    rule = make_rule(rule_id, _TEST)
    return rule.model_copy(
        update={
            "title": title or f"Rule {rule_id}",
            "lineage": RuleLineage(source_elements=elements),
            "required_facts": [RequiredFact(name="days", data_type="integer")] if deterministic else [],
        }
    )


class TestOnePassageIsOnePolicy:
    def test_rules_from_one_element_become_one_policy_carrying_all_of_them(self):
        """The whole point: three obligations of one paragraph, one card."""

        policies = assemble(
            [
                _rule("R1", "p23-E000165"),
                _rule("R2", "p23-E000165"),
                _rule("R3", "p23-E000165"),
            ]
        )

        assert len(policies) == 1
        assert policies[0].rule_count == 3
        assert [rule.rule_id for rule in policies[0].rules] == ["R1", "R2", "R3"]

    def test_a_policy_of_one_rule_is_built_the_same_way_as_any_other(self):
        """Most policies hold one rule. That is ordinary, not a special case.

        Asserted because the tempting shortcut -- returning lone rules
        unwrapped -- would give a client two shapes to render and would make
        the common case the exception.
        """

        policies = assemble([_rule("R1", "p4-E000012")])

        assert len(policies) == 1
        assert isinstance(policies[0], AssembledPolicy)
        assert policies[0].rule_count == 1

    def test_rules_from_different_elements_stay_apart(self):
        policies = assemble([_rule("R1", "p4-E000012"), _rule("R2", "p9-E000101")])

        assert [policy.rule_count for policy in policies] == [1, 1]

    def test_nine_rules_from_one_sentence_assemble_into_one_policy(self):
        """The worst real unit measured: GMU p23-E000165, one record per verb.

        Nine cards for one sentence of supervisor duties is the shape the owner
        complained about, and it is the shape that must collapse to one card
        holding nine rules -- not to one rule, which would lose eight duties.
        """

        policies = assemble([_rule(f"R{n}", "p23-E000165") for n in range(9)])

        assert len(policies) == 1
        assert policies[0].rule_count == 9


class TestAssemblyIsAPartition:
    def _corpus(self) -> list[CanonicalRule]:
        return [
            _rule("R1", "p4-E000012"),
            _rule("R2", "p23-E000165"),
            _rule("R3", "p23-E000165"),
            _rule("R4", ""),
            _rule("R5", "p9-E000101; p9-E000102"),
            _rule("R6", "p9-E000101"),
        ]

    def test_every_rule_that_goes_in_comes_out(self):
        rules = self._corpus()

        placed = [rule.rule_id for policy in assemble(rules) for rule in policy.rules]

        assert sorted(placed) == sorted(rule.rule_id for rule in rules)

    def test_no_rule_lands_in_two_policies(self):
        """A duplicated rule would show a reviewer one obligation twice, under
        two headings, which is worse than the fragmentation this fixes."""

        placed = [rule.rule_id for policy in assemble(self._corpus()) for rule in policy.rules]

        assert len(placed) == len(set(placed))

    def test_no_policy_is_empty(self):
        assert all(policy.rules for policy in assemble(self._corpus()))

    def test_assembling_nothing_yields_nothing(self):
        assert assemble([]) == []


class TestTheKey:
    def test_a_rule_citing_several_elements_anchors_to_the_first(self):
        """Where the subject is introduced. The later elements stay visible."""

        policies = assemble([_rule("R1", "p9-E000101; p9-E000102; p10-E000104")])

        assert policies[0].key == "p9-E000101"
        assert policies[0].source_elements == "p9-E000101; p9-E000102; p10-E000104"

    def test_a_rule_citing_a_span_groups_with_a_rule_citing_only_its_first_element(self):
        """34% of AIS rules cite more than one element and 3% of GMU rules do.

        If a span and a bare element did not meet, a passage would split by how
        widely each of its rules happened to be quoted.
        """

        policies = assemble([_rule("R1", "p9-E000101; p9-E000102"), _rule("R2", "p9-E000101")])

        assert len(policies) == 1

    def test_two_rules_with_no_provenance_do_not_become_one_policy(self):
        """Silence is not agreement.

        Two rules that each fail to say where they came from have not thereby
        said they came from the same place. Grouping them would assert a
        relationship the document never stated -- the one thing assembly is
        not allowed to do.
        """

        policies = assemble([_rule("R1", ""), _rule("R2", "")])

        assert len(policies) == 2
        assert {policy.rule_count for policy in policies} == {1}

    def test_a_blank_element_before_a_real_one_does_not_become_the_key(self):
        assert policy_key(_rule("R1", " ; p9-E000101")) == "p9-E000101"

    def test_the_key_is_the_element_not_the_rule_id(self):
        """So the same passage groups identically across two extraction runs."""

        first = policy_key(_rule("R1", "p9-E000101"))
        second = policy_key(_rule("R2", "p9-E000101"))

        assert first == second == "p9-E000101"


class TestRouteSurvivesAssembly:
    def test_a_policy_whose_rules_all_carry_a_computable_test_is_deterministic(self):
        policies = assemble(
            [_rule("R1", "p4-E000012", deterministic=True), _rule("R2", "p4-E000012", deterministic=True)]
        )

        assert policies[0].route == "deterministic"

    def test_a_policy_whose_rules_are_all_stated_in_words_is_ai_ready(self):
        policies = assemble([_rule("R1", "p4-E000012"), _rule("R2", "p4-E000012")])

        assert policies[0].route == "ai_ready"

    def test_a_policy_holding_both_kinds_of_rule_is_mixed(self):
        """"Thirty days annual leave" is a comparison and "subject to
        Immigration rules" is read by a judge, and one paragraph states both.
        Mixed is what a real policy looks like."""

        policies = assemble(
            [_rule("R1", "p4-E000012", deterministic=True), _rule("R2", "p4-E000012")]
        )

        assert policies[0].route == "mixed"

    def test_a_mixed_policy_keeps_both_of_its_rules_routed_as_they_were(self):
        """Routing is a property of the rule. The policy summarises its rules;
        it must never overwrite them, or the deterministic rule in a mixed
        policy would stop being served by the route that can decide it."""

        policies = assemble(
            [_rule("R1", "p4-E000012", deterministic=True), _rule("R2", "p4-E000012")]
        )

        modes = {rule.rule_id: rule.evaluation_mode for rule in policies[0].rules}
        assert modes == {"R1": EvaluationMode.DETERMINISTIC, "R2": EvaluationMode.AI_READY}

    def test_mixed_is_reported_as_a_route_and_carries_no_severity(self):
        """A policy is `deterministic`, `mixed` or `ai_ready` and nothing else.

        No count of what is "still" ai_ready, no flag, no grade. All three are
        routes to a decision; a policy is not worse for taking two of them.
        """

        policies = assemble(
            [_rule("R1", "p4-E000012", deterministic=True), _rule("R2", "p4-E000012")]
        )

        assert policies[0].route in {"deterministic", "mixed", "ai_ready"}
        assert not [
            name
            for name in dir(policies[0])
            if not name.startswith("_") and name in {"severity", "status", "score", "gap", "shortfall"}
        ]


class TestNothingIsInvented:
    def test_titles_come_out_verbatim(self):
        policies = assemble(
            [
                _rule("R1", "p4-E000012", title="Overtime is approved by HR"),
                _rule("R2", "p4-E000012", title="Overtime is controlled by senior management"),
            ]
        )

        assert [rule.title for rule in policies[0].rules] == [
            "Overtime is approved by HR",
            "Overtime is controlled by senior management",
        ]

    def test_a_policy_carries_no_composed_text_of_its_own(self):
        """Assembly groups; it does not write.

        A policy-level summary would be text no one in the document wrote, and
        the moment it existed a reviewer would start approving it instead of
        the rules. The only strings a policy carries are its provenance.
        """

        policies = assemble([_rule("R1", "p4-E000012"), _rule("R2", "p4-E000012")])

        assert set(vars(policies[0])) == {"key", "source_elements", "page", "rules"}


class TestOrderAndShape:
    def test_policies_come_back_in_document_order(self):
        policies = assemble(
            [_rule("R1", "p23-E000165"), _rule("R2", "p4-E000012"), _rule("R3", "p9-E000101")]
        )

        assert [policy.key for policy in policies] == ["p4-E000012", "p9-E000101", "p23-E000165"]

    def test_an_element_spanning_a_page_break_still_orders_by_its_element(self):
        """Ids look like `p5-6-E000050` when a passage crosses a page, so
        ordering reads the element number rather than the page prefix."""

        policies = assemble([_rule("R1", "p9-E000101"), _rule("R2", "p5-6-E000050")])

        assert [policy.key for policy in policies] == ["p5-6-E000050", "p9-E000101"]

    def test_the_page_is_taken_from_the_evidence_of_its_rules(self):
        rule = _rule("R1", "p4-E000012")
        rule = rule.model_copy(
            update={"evidence": [EvidenceReference(document_version_id="dv1", source_hash="h", page=4)]}
        )

        assert assemble([rule])[0].page == 4

    def test_a_policy_with_no_paged_evidence_reports_no_page(self):
        assert assemble([_rule("R1", "p4-E000012")])[0].page is None

    def test_the_shape_of_a_set_shows_the_tail_not_an_average(self):
        """A mean of 1.5 hides a paragraph that produced six.

        `rule_count` per policy is the shape, read off the assembled list --
        the owner's complaint is about the tail, so the tail has to survive
        into what a client can render.
        """

        policies = assemble(
            [_rule("R1", "p4-E000012")]
            + [_rule(f"R{n}", "p9-E000101") for n in range(2, 4)]
            + [_rule(f"R{n}", "p23-E000165") for n in range(4, 10)]
        )

        assert sorted(policy.rule_count for policy in policies) == [1, 2, 6]
