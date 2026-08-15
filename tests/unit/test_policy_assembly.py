"""Assembly puts rules back under the section that stated them.

The defect these cover, at two levels. First: a paragraph stating three
obligations produced three policy cards, so a reviewer met the same passage
three times and could not see that the three belonged together. Then, one level
up: two consecutive sentences of one section produced two cards bearing the same
name, because the key was the passage and a policy stated across several
sentences can never be joined by it.

So the key is the heading, and every test here checks that assembly *adds* a
grouping and takes nothing away -- no rule dropped, no rule duplicated, no text
composed, no rule's own route replaced by its policy's summary of it, and no
passage boundary dissolved on the way in.
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
    ProvisionGrouping,
    assemble,
    passage_key,
    policy_key,
)
from tests.fixtures.factories import make_rule

_TEST = FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS)


def _rule(
    rule_id: str,
    elements: str,
    *,
    section: str | None = None,
    page: int | None = None,
    deterministic: bool = False,
    title: str | None = None,
) -> CanonicalRule:
    """A stored rule with the provenance assembly groups on.

    `make_rule` exposes neither lineage nor required_facts, and the second is
    what decides the route, so both arrive by copy. The section arrives on the
    evidence, which is where the extraction records it.
    """

    rule = make_rule(rule_id, _TEST)
    evidence = []
    if section is not None or page is not None:
        evidence = [
            EvidenceReference(
                document_version_id="dv1", source_hash="h", section=section, page=page
            )
        ]
    return rule.model_copy(
        update={
            "title": title or f"Rule {rule_id}",
            "lineage": RuleLineage(source_elements=elements),
            "evidence": evidence,
            "required_facts": [RequiredFact(name="days", data_type="integer")] if deterministic else [],
        }
    )


class TestOneSectionIsOnePolicy:
    def test_two_sentences_of_one_section_become_one_policy(self):
        """The owner's case, stated four times.

        `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES SPONSORSHIP` says a
        medical test is needed and that the employee pays half the transfer
        cost. Two elements, two sentences, one policy about work permits. The
        old key grouped on the element and so could never join them; it
        produced two cards with the same name, which is what "you keep breaking
        them into pieces" was about.
        """

        section = "7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES SPONSORSHIP"
        policies = assemble(
            [
                _rule("R1", "p9-E000074", section=section),
                _rule("R2", "p9-E000075", section=section),
            ]
        )

        assert len(policies) == 1
        assert policies[0].key == section
        assert policies[0].rule_count == 2

    def test_rules_from_one_element_still_become_one_policy(self):
        """The level below, which must keep working: three obligations of one
        paragraph, one card."""

        policies = assemble(
            [
                _rule("R1", "p23-E000165", section="8.2. WORK BEHAVIOUR"),
                _rule("R2", "p23-E000165", section="8.2. WORK BEHAVIOUR"),
                _rule("R3", "p23-E000165", section="8.2. WORK BEHAVIOUR"),
            ]
        )

        assert len(policies) == 1
        assert policies[0].rule_count == 3
        assert [rule.rule_id for rule in policies[0].rules] == ["R1", "R2", "R3"]

    def test_a_policy_of_one_rule_is_built_the_same_way_as_any_other(self):
        """Most sections state one rule. That is ordinary, not a special case.

        Asserted because the tempting shortcut -- returning lone rules
        unwrapped -- would give a client two shapes to render and would make
        the common case the exception.
        """

        policies = assemble([_rule("R1", "p4-E000012", section="1. WELCOME")])

        assert len(policies) == 1
        assert isinstance(policies[0], AssembledPolicy)
        assert policies[0].rule_count == 1
        assert policies[0].passage_count == 1

    def test_rules_under_different_headings_stay_apart(self):
        policies = assemble(
            [
                _rule("R1", "p4-E000012", section="1. WELCOME"),
                _rule("R2", "p9-E000101", section="7.1. THE EMPLOYMENT CONTRACT"),
            ]
        )

        assert [policy.rule_count for policy in policies] == [1, 1]

    def test_a_section_with_fifty_passages_is_one_policy_holding_all_of_them(self):
        """`Table of Violations and Penalties`: 72 rules across 50 passages.

        Checked before assuming it was a defect, and it is not one -- it is a
        disciplinary schedule with a row per offence, which is one policy. The
        card gets long; the rules do not get fewer.
        """

        policies = assemble(
            [
                _rule(f"R{n}", f"p{20 + n // 3}-E{160 + n:06d}", section="Table of Violations and Penalties")
                for n in range(72)
            ]
        )

        assert len(policies) == 1
        assert policies[0].rule_count == 72

    def test_two_documents_sharing_a_heading_do_not_share_a_policy(self):
        """"Introduction" in two handbooks is two introductions."""

        first = _rule("R1", "p1-E000001", section="Introduction")
        second = _rule("R2", "p1-E000002", section="Introduction").model_copy(
            update={
                "evidence": [
                    EvidenceReference(
                        document_version_id="dv2", source_hash="h", section="Introduction"
                    )
                ]
            }
        )

        assert len(assemble([first, second])) == 2


class TestThePassageBoundarySurvives:
    def test_a_policy_keeps_its_rules_grouped_by_the_sentence_that_stated_them(self):
        """A reviewer reading a long card has to see which words each rule came
        from. Flattening fourteen rules into one list answers the complaint by
        making a smaller version of it.
        """

        section = "7.1. THE EMPLOYMENT CONTRACT"
        policies = assemble(
            [
                _rule("R1", "p9-E000071", section=section),
                _rule("R2", "p9-E000071", section=section),
                _rule("R3", "p9-E000072", section=section),
            ]
        )

        assert policies[0].passage_count == 2
        assert [passage.key for passage in policies[0].passages] == ["p9-E000071", "p9-E000072"]
        assert [passage.rule_count for passage in policies[0].passages] == [2, 1]

    def test_passages_come_back_in_document_order(self):
        section = "9. APARTMENTS"
        policies = assemble(
            [
                _rule("R1", "p30-E000210", section=section),
                _rule("R2", "p29-E000201", section=section),
            ]
        )

        assert [passage.key for passage in policies[0].passages] == ["p29-E000201", "p30-E000210"]

    def test_the_flat_rule_list_reads_in_passage_order(self):
        section = "9. APARTMENTS"
        policies = assemble(
            [
                _rule("R2", "p30-E000210", section=section),
                _rule("R1", "p29-E000201", section=section),
            ]
        )

        assert [rule.rule_id for rule in policies[0].rules] == ["R1", "R2"]

    def test_a_passage_keeps_its_own_full_attribution(self):
        section = "7.1. THE EMPLOYMENT CONTRACT"
        policies = assemble([_rule("R1", "p9-E000101; p9-E000102", section=section)])

        assert policies[0].passages[0].key == "p9-E000101"
        assert policies[0].passages[0].source_elements == "p9-E000101; p9-E000102"


class TestAssemblyIsAPartition:
    def _corpus(self) -> list[CanonicalRule]:
        return [
            _rule("R1", "p4-E000012", section="1. WELCOME"),
            _rule("R2", "p23-E000165", section="8.2. WORK BEHAVIOUR"),
            _rule("R3", "p23-E000165", section="8.2. WORK BEHAVIOUR"),
            _rule("R4", ""),
            _rule("R5", "p9-E000101; p9-E000102", section="7.1. THE CONTRACT"),
            _rule("R6", "p9-E000101", section="7.1. THE CONTRACT"),
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

    def test_no_rule_lands_in_two_passages_of_one_policy(self):
        placed = [
            rule.rule_id
            for policy in assemble(self._corpus())
            for passage in policy.passages
            for rule in passage.rules
        ]

        assert len(placed) == len(set(placed))

    def test_no_policy_is_empty(self):
        assert all(policy.passages for policy in assemble(self._corpus()))

    def test_no_passage_is_empty(self):
        assert all(
            passage.rules for policy in assemble(self._corpus()) for passage in policy.passages
        )

    def test_assembling_nothing_yields_nothing(self):
        assert assemble([]) == []


class TestTheKey:
    def test_the_key_is_the_heading_the_document_wrote(self):
        policies = assemble([_rule("R1", "p9-E000101", section="7.1. THE EMPLOYMENT CONTRACT")])

        assert policies[0].key == "7.1. THE EMPLOYMENT CONTRACT"

    def test_the_key_is_the_heading_not_the_rule_id(self):
        """So the same section groups identically across two extraction runs."""

        first = policy_key(_rule("R1", "p9-E000101", section="7.8. WORKING HOURS"))
        second = policy_key(_rule("R2", "p9-E000109", section="7.8. WORKING HOURS"))

        assert first == second == "7.8. WORKING HOURS"

    def test_a_rule_with_no_heading_falls_back_to_its_own_passage(self):
        """No stored rule in the corpus takes this path, and it is still not
        allowed to invent a bucket."""

        assert policy_key(_rule("R1", "p9-E000101")) == "p9-E000101"

    def test_two_rules_with_no_provenance_at_all_do_not_become_one_policy(self):
        """Silence is not agreement.

        Two rules that each fail to say where they came from have not thereby
        said they came from the same place. Grouping them would assert a
        relationship the document never stated -- the one thing assembly is
        not allowed to do.
        """

        policies = assemble([_rule("R1", ""), _rule("R2", "")])

        assert len(policies) == 2
        assert {policy.rule_count for policy in policies} == {1}

    def test_a_blank_element_before_a_real_one_does_not_become_the_passage(self):
        assert passage_key(_rule("R1", " ; p9-E000101")) == "p9-E000101"

    def test_a_span_and_a_bare_element_meet_in_one_passage(self):
        """34% of AIS rules cite more than one element and 3% of GMU rules do.

        If a span and a bare element did not meet, a passage would split by how
        widely each of its rules happened to be quoted.
        """

        section = "7.1. THE CONTRACT"
        policies = assemble(
            [
                _rule("R1", "p9-E000101; p9-E000102", section=section),
                _rule("R2", "p9-E000101", section=section),
            ]
        )

        assert policies[0].passage_count == 1


class TestRouteSurvivesAssembly:
    def test_a_policy_whose_rules_all_carry_a_computable_test_is_deterministic(self):
        policies = assemble(
            [
                _rule("R1", "p4-E000012", section="S", deterministic=True),
                _rule("R2", "p4-E000012", section="S", deterministic=True),
            ]
        )

        assert policies[0].route == "deterministic"

    def test_a_policy_whose_rules_are_all_stated_in_words_is_ai_ready(self):
        policies = assemble(
            [_rule("R1", "p4-E000012", section="S"), _rule("R2", "p4-E000012", section="S")]
        )

        assert policies[0].route == "ai_ready"

    def test_a_policy_holding_both_kinds_of_rule_is_mixed(self):
        """"Thirty days annual leave" is a comparison and "subject to
        Immigration rules" is read by a judge, and one section states both.
        Mixed is what a real policy looks like."""

        policies = assemble(
            [
                _rule("R1", "p4-E000012", section="S", deterministic=True),
                _rule("R2", "p4-E000012", section="S"),
            ]
        )

        assert policies[0].route == "mixed"

    def test_a_mixed_policy_keeps_both_of_its_rules_routed_as_they_were(self):
        """Routing is a property of the rule. The policy summarises its rules;
        it must never overwrite them, or the deterministic rule in a mixed
        policy would stop being served by the route that can decide it."""

        policies = assemble(
            [
                _rule("R1", "p4-E000012", section="S", deterministic=True),
                _rule("R2", "p4-E000012", section="S"),
            ]
        )

        modes = {rule.rule_id: rule.evaluation_mode for rule in policies[0].rules}
        assert modes == {"R1": EvaluationMode.DETERMINISTIC, "R2": EvaluationMode.AI_READY}

    def test_a_rule_keeps_its_route_across_a_passage_boundary(self):
        """Grouping two sentences together must not average their routes."""

        policies = assemble(
            [
                _rule("R1", "p9-E000074", section="7.2. IQAMA", deterministic=True),
                _rule("R2", "p9-E000075", section="7.2. IQAMA"),
            ]
        )

        modes = {rule.rule_id: rule.evaluation_mode for rule in policies[0].rules}
        assert modes == {"R1": EvaluationMode.DETERMINISTIC, "R2": EvaluationMode.AI_READY}
        assert policies[0].route == "mixed"

    def test_mixed_is_reported_as_a_route_and_carries_no_severity(self):
        """A policy is `deterministic`, `mixed` or `ai_ready` and nothing else.

        No count of what is "still" ai_ready, no flag, no grade. All three are
        routes to a decision; a policy is not worse for taking two of them.
        """

        policies = assemble(
            [
                _rule("R1", "p4-E000012", section="S", deterministic=True),
                _rule("R2", "p4-E000012", section="S"),
            ]
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
                _rule("R1", "p4-E000012", section="S", title="Overtime is approved by HR"),
                _rule("R2", "p4-E000012", section="S", title="Overtime is controlled by senior management"),
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
        the rules. The only strings a policy carries are its provenance -- its
        key, the identity of the persisted row it is, and the heading chain
        copied verbatim from the document, which is why those can be shown as
        the policy's name. An identity is admissible here for the same reason a
        key is: it names *which* policy this is and says nothing about what the
        policy holds, so there is nothing in it for a reviewer to approve.

        Asserted as an exact field set rather than a check for known-bad names,
        so a summary column added later fails here on the day it is added
        rather than on the day someone notices a reviewer approving it.
        """

        policies = assemble(
            [_rule("R1", "p4-E000012", section="S"), _rule("R2", "p4-E000012", section="S")]
        )

        assert set(vars(policies[0])) == {
            "key",
            "document_version_id",
            "page",
            "passages",
            "heading_path",
            "persisted",
            "provision_id",
        }

    def test_a_policy_is_named_by_the_heading_its_provision_recorded(self):
        """The card is the section, so the section's heading names it.

        Verbatim and whole: the innermost heading exactly as the document wrote
        it, never a sentence lifted out of one of the passages beneath it. That
        naming was right while a card was a passage -- a passage's own opening
        statement is unique to it -- and reverses here, where taking one of
        fourteen sentences would present it as the name of all fourteen.
        """

        grouping = ProvisionGrouping(
            key="ab12", provision_id="id-ab12", heading_path=("7. EMPLOYMENT", "7.2. WORK PERMIT (IQAMA)")
        )
        policies = assemble(
            [_rule("R1", "p9-E000074", section="S"), _rule("R2", "p9-E000075", section="S")],
            provisions={"R1": grouping, "R2": grouping},
        )

        assert len(policies) == 1
        assert policies[0].key == "ab12"
        assert policies[0].heading == "7.2. WORK PERMIT (IQAMA)"
        assert policies[0].heading_path == ("7. EMPLOYMENT", "7.2. WORK PERMIT (IQAMA)")
        assert policies[0].persisted is True

    def test_a_policy_without_a_provision_is_still_named_by_its_heading(self):
        """The fallback still has to name its cards.

        A rule extracted before provisions existed carries no link, and the
        heading its evidence records is the only name available. It claims one
        heading rather than a chain, because one is all it read. Reported as
        `persisted=False` rather than passed off as the same thing, because a
        stored boundary and an inferred one are different claims and a reviewer
        approving a policy is entitled to know which they are looking at.
        """

        policies = assemble([_rule("R1", "p4-E000012", section="1. WELCOME")])

        assert policies[0].heading == "1. WELCOME"
        assert policies[0].heading_path == ("1. WELCOME",)
        assert policies[0].persisted is False

    def test_a_policy_with_no_heading_anywhere_is_left_unnamed(self):
        """Silence is reported as silence, not as an element id.

        A rule whose evidence records no section is keyed by its own passage,
        and that key is `p9-E000074`. Returning it as the policy's heading would
        hand a client a string the document never wrote, and the client would
        print it in the place a reviewer reads the policy's name. Empty says
        what happened and leaves the client to say so too.
        """

        policies = assemble([_rule("R1", "p9-E000074")])

        assert policies[0].key == "p9-E000074"
        assert policies[0].heading == ""
        assert policies[0].heading_path == ()


class TestOrderAndShape:
    def test_policies_come_back_in_document_order(self):
        policies = assemble(
            [
                _rule("R1", "p23-E000165", section="8.2. BEHAVIOUR"),
                _rule("R2", "p4-E000012", section="1. WELCOME"),
                _rule("R3", "p9-E000101", section="7.1. CONTRACT"),
            ]
        )

        assert [policy.key for policy in policies] == ["1. WELCOME", "7.1. CONTRACT", "8.2. BEHAVIOUR"]

    def test_a_section_orders_by_where_the_document_first_states_it(self):
        """Not alphabetically, and not by the heading's number -- by the
        element, which is allocated as the document reads."""

        policies = assemble(
            [
                _rule("R1", "p30-E000210", section="10. LAST"),
                _rule("R2", "p5-6-E000050", section="2. FIRST"),
            ]
        )

        assert [policy.key for policy in policies] == ["2. FIRST", "10. LAST"]

    def test_the_page_is_the_first_page_the_policy_appears_on(self):
        policies = assemble(
            [
                _rule("R1", "p10-E000101", section="S", page=10),
                _rule("R2", "p9-E000100", section="S", page=9),
            ]
        )

        assert policies[0].page == 9

    def test_a_policy_with_no_paged_evidence_reports_no_page(self):
        assert assemble([_rule("R1", "p4-E000012", section="S")])[0].page is None

    def test_the_shape_of_a_set_shows_the_tail_not_an_average(self):
        """A mean of 1.5 hides a section that produced seventy-two.

        `rule_count` per policy is the shape, read off the assembled list --
        the owner's complaint is about the tail, so the tail has to survive
        into what a client can render.
        """

        policies = assemble(
            [_rule("R1", "p4-E000012", section="A")]
            + [_rule(f"R{n}", "p9-E000101", section="B") for n in range(2, 4)]
            + [_rule(f"R{n}", "p23-E000165", section="C") for n in range(4, 10)]
        )

        assert sorted(policy.rule_count for policy in policies) == [1, 2, 6]

    def test_the_source_elements_of_a_policy_list_its_passages(self):
        section = "7.1. THE CONTRACT"
        policies = assemble(
            [
                _rule("R1", "p9-E000071", section=section),
                _rule("R2", "p9-E000072", section=section),
            ]
        )

        assert policies[0].source_elements == "p9-E000071; p9-E000072"
