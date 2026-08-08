"""Tests for the policy formulator agent's parsing and deterministic mapping.

These cover the two places the pipeline can silently go wrong:

1. **Transport tolerance** — the agent's reply must survive the three shapes it
   realistically arrives in, and must fail loudly when nothing is recoverable.
   Where individual canonical policies are malformed, the valid ones beside
   them must survive: the batch is the parsing boundary but the policy is the
   unit of value, and one entry's shape variance is not evidence against its
   siblings.
2. **Refusal to guess** — the FEEL translator and the rule mapper must decline
   anything they do not fully understand, because a wrong condition is worse
   than an absent one.
"""
from __future__ import annotations

import json

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
    DmnDecisionTable,
    DmnMappingStatus,
    DmnProjection,
    DmnTableInput,
    DmnTableOutput,
    DmnTableRule,
    PolicyFormulation,
)
from policy_platform.infrastructure.formulation_mapping import (
    formulation_to_candidate_rules,
    parse_feel_unary_test,
)
from policy_platform.infrastructure.policy_formulator import (
    PolicyFormulationError,
    load_formulator_prompt,
    parse_formulation,
)

# --------------------------------------------------------------------------
# Serialization contract (spec Sections 22, 93, 94)
# --------------------------------------------------------------------------


def test_absent_canonical_fields_are_omitted_not_nulled():
    """Spec Section 22 forbids null / unknown / N/A for absent fields."""

    policy = CanonicalPolicy(
        source_text="Managers must approve travel.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject="Managers",
            modality="must",
            predicate="approve",
            object="travel",
        ),
    )
    dumped = policy.model_dump(mode="json")

    assert "evidence" not in dumped
    assert "ambiguity" not in dumped
    rule = dumped["rule"]
    assert "condition" not in rule and "threshold" not in rule and "currency" not in rule
    assert not any(value is None for value in rule.values())


def test_canonical_field_order_matches_spec_section_93():
    """Field order is part of the output contract, not cosmetic."""

    rule = CanonicalPolicyRule(
        rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
        subject="Expenses",
        predicate="require",
        object="approval",
        condition="above 5000",
        threshold="5000",
        currency="USD",
    )
    assert list(rule.model_dump(mode="json")) == [
        "rule_type",
        "subject",
        "predicate",
        "object",
        "condition",
        "threshold",
        "currency",
    ]


def test_dmn_decision_keeps_explicit_null_decision_table():
    """Section 94 exempts `decision_table` from the omit-absent rule."""

    decision = DmnDecision(
        source_rule_indexes=[0],
        dmn_mapping_status=DmnMappingStatus.NOT_DIRECTLY_MAPPABLE,
    )
    dumped = decision.model_dump(mode="json")

    assert dumped["decision_table"] is None
    assert dumped["requirements"] == []
    assert "dependencies" not in dumped


def test_projection_constants_state_the_representation_honestly():
    """Section 1 forbids presenting the IR as normative DMN 1.5 XML."""

    dumped = DmnProjection().model_dump(mode="json")
    assert dumped["standard"] == "OMG DMN 1.5"
    assert dumped["expression_language"] == "FEEL"
    assert dumped["representation"] == "DMN-compatible JSON IR"


# --------------------------------------------------------------------------
# Agent transport
# --------------------------------------------------------------------------


def _envelope(canonical: list[dict], decisions: list[dict]) -> str:
    return json.dumps(
        {
            "CANONICAL_JSON": {"canonical_policies": canonical},
            "DMN_JSON": {
                "dmn_projection": {
                    "standard": "OMG DMN 1.5",
                    "expression_language": "FEEL",
                    "representation": "DMN-compatible JSON IR",
                    "decisions": decisions,
                }
            },
        }
    )


_OBLIGATION = {
    "source_text": "An employee's immediate supervisor must evaluate the performance of "
    "employees they supervise",
    "extraction_status": "complete",
    "rule": {
        "rule_type": "obligation",
        "subject": "An employee's immediate supervisor",
        "modality": "must",
        "predicate": "evaluate",
        "object": "the performance of employees they supervise",
    },
}


def test_prompt_asset_is_the_specification_plus_transport_addendum():
    prompt = load_formulator_prompt()
    assert "ENTERPRISE POLICY EXTRACTION AND DECISION ENGINE" in prompt
    assert "# 104. FINAL OUTPUT CONTRACT" in prompt
    assert "# 106. OVERRIDING PRINCIPLES" in prompt
    assert "TRANSPORT ADDENDUM" in prompt


def test_parses_the_transport_envelope():
    formulation = parse_formulation(_envelope([_OBLIGATION], []))
    assert len(formulation.canonical_policies) == 1
    assert formulation.canonical_policies[0].rule.predicate == "evaluate"


def test_parses_a_flat_merged_object():
    """Some replies merge the two documents; that is recoverable, not fatal."""

    raw = json.dumps(
        {"canonical_policies": [_OBLIGATION], "dmn_projection": {"decisions": []}}
    )
    assert parse_formulation(raw).canonical_policies[0].extraction_status.value == "complete"


def test_parses_the_specs_literal_two_block_form():
    """Section 104's own format, in case JSON mode is ever turned off."""

    raw = (
        "CANONICAL_JSON\n```json\n"
        + json.dumps({"canonical_policies": [_OBLIGATION]})
        + "\n```\nDMN_JSON\n```json\n"
        + json.dumps({"dmn_projection": {"decisions": []}})
        + "\n```"
    )
    assert parse_formulation(raw).canonical_policies[0].rule.subject.startswith("An employee")


def test_strips_a_stray_code_fence():
    raw = "```json\n" + _envelope([_OBLIGATION], []) + "\n```"
    assert parse_formulation(raw).canonical_policies


@pytest.mark.parametrize("raw", ["", "   ", "sorry, I cannot help with that", "[1, 2, 3]"])
def test_unusable_replies_raise_rather_than_returning_partial_results(raw):
    with pytest.raises(PolicyFormulationError):
        parse_formulation(raw)


def test_unknown_mapping_status_is_rejected_not_coerced():
    """Section 45 defines exactly five statuses; a sixth means something broke."""

    raw = _envelope(
        [_OBLIGATION],
        [{"source_rule_indexes": [0], "dmn_mapping_status": "probably_fine"}],
    )
    with pytest.raises(PolicyFormulationError):
        parse_formulation(raw)


# --------------------------------------------------------------------------
# FEEL unary tests
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("-", []),
        ("", []),
        (">= 5000", [("greaterThanOrEqual", 5000)]),
        ("<= 5000", [("lessThanOrEqual", 5000)]),
        ("> 0", [("greaterThan", 0)]),
        ("< 10000", [("lessThan", 10000)]),
        ("!= 0", [("notEquals", 0)]),
        ("= 3", [("equals", 3)]),
        ("2.5", [("equals", 2.5)]),
        ("true", [("equals", True)]),
        ('"Director"', [("equals", "Director")]),
        ("[5000..10000]", [("greaterThanOrEqual", 5000), ("lessThanOrEqual", 10000)]),
        ("(5000..10000]", [("greaterThan", 5000), ("lessThanOrEqual", 10000)]),
        ("[5000..10000)", [("greaterThanOrEqual", 5000), ("lessThan", 10000)]),
        ('"A", "B"', [("in", ["A", "B"])]),
    ],
)
def test_supported_feel_unary_tests(expression, expected):
    leaves = parse_feel_unary_test("expense.amount", expression)
    assert leaves is not None
    assert [(leaf.operator.value, leaf.value) for leaf in leaves] == expected
    assert all(leaf.fact == "expense.amount" for leaf in leaves)


@pytest.mark.parametrize(
    "expression",
    [
        'not("Director")',
        'date("2024-01-01")',
        "sum(items)",
        "> amount * 2",
        "duration('P30D')",
        "?",
        "[a..b]",
    ],
)
def test_unsupported_feel_is_refused_rather_than_guessed(expression):
    """Refusing is the safe answer: a wrong condition evaluates confidently."""

    assert parse_feel_unary_test("expense.amount", expression) is None


# --------------------------------------------------------------------------
# Deterministic mapping to platform rules
# --------------------------------------------------------------------------


def _map(formulation: PolicyFormulation):
    return formulation_to_candidate_rules(
        formulation,
        policy_set_id="ps-1",
        extraction_run_id="run-1",
        deployment_name="test-deployment",
        prompt_version="dmn-formulator-v1",
        parser_version="dmn-formulator-v1",
        source_note="c-1",
        category="Finance",
    )


def _executable_expense_formulation() -> PolicyFormulation:
    return parse_formulation(
        _envelope(
            [
                {
                    "source_text": "Expenses of 5000 or more require Director approval.",
                    "extraction_status": "complete",
                    "rule": {
                        "rule_type": "conditional_outcome",
                        "subject": "Expenses",
                        "predicate": "require",
                        "object": "Director approval",
                        "threshold": "5000 or more",
                    },
                }
            ],
            [
                {
                    "source_rule_indexes": [0],
                    "dmn_mapping_status": "executable",
                    "requirements": [],
                    "decision_table": {
                        "hit_policy": "UNIQUE",
                        "inputs": [
                            {
                                "label": "expense amount",
                                "expression": "expense.amount",
                                "type": "number",
                            }
                        ],
                        "outputs": [
                            {
                                "label": "approval route",
                                "name": "approvalRoute",
                                "type": "string",
                            }
                        ],
                        "rules": [
                            {"input_entries": [">= 5000"], "output_entries": ['"Director"']}
                        ],
                    },
                }
            ],
        )
    )


def test_executable_decision_becomes_a_machine_executable_rule():
    rules, skipped = _map(_executable_expense_formulation())

    assert skipped == []
    (rule,) = rules
    assert rule.machine_executable is True
    assert rule.ambiguity_status.value == "none"
    assert rule.rule_type.value == "routing"
    assert rule.condition.type == "all"
    leaf = rule.condition.all[0]
    assert (leaf.fact, leaf.operator.value, leaf.value) == (
        "expense.amount",
        "greaterThanOrEqual",
        5000,
    )
    assert [(f.name, f.data_type) for f in rule.required_facts] == [
        ("expense.amount", "number")
    ]
    assert rule.category == "Finance"
    assert rule.review_status.value == "candidate"


def test_non_decision_obligation_stays_non_executable_but_is_kept():
    """Spec Section 106: not every policy is a decision — keep it, don't force it."""

    rules, skipped = _map(
        parse_formulation(
            _envelope(
                [_OBLIGATION],
                [
                    {
                        "source_rule_indexes": [0],
                        "dmn_mapping_status": "not_directly_mappable",
                        "requirements": [],
                        "semantic_projection": {
                            "rule_type": "obligation",
                            "subject": "An employee's immediate supervisor",
                            "predicate": "evaluate",
                            "object": "the performance of employees they supervise",
                        },
                        "decision_table": None,
                    }
                ],
            )
        )
    )

    assert skipped == []
    (rule,) = rules
    assert rule.machine_executable is False
    assert rule.ambiguity_status.value == "human_judgment_required"
    assert rule.condition.type == "all" and rule.condition.all == []
    assert rule.rule_type.value == "obligation"
    assert rule.effect.type.value == "require_action"
    assert rule.effect.action == "evaluate the performance of employees they supervise"
    assert "not_directly_mappable" in rule.description


def test_enrichment_required_surfaces_its_requirement_codes_to_reviewers():
    rules, _ = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": "Employees with 10 years of service receive 10K.",
                        "extraction_status": "complete",
                        "rule": {
                            "rule_type": "entitlement",
                            "subject": "Employees",
                            "predicate": "receive",
                            "object": "10K",
                        },
                    }
                ],
                [
                    {
                        "source_rule_indexes": [0],
                        "dmn_mapping_status": "enrichment_required",
                        "requirements": [
                            "FACT_MODEL_REQUIRED",
                            "VALUE_NORMALIZATION_REQUIRED",
                        ],
                        "decision_table": None,
                    }
                ],
            )
        )
    )

    (rule,) = rules
    assert rule.machine_executable is False
    assert "FACT_MODEL_REQUIRED" in rule.description
    assert "VALUE_NORMALIZATION_REQUIRED" in rule.description
    # Section 66: an entitlement must not be promoted to an obligation.
    assert rule.rule_type.value == "permission"
    assert rule.formulation.canonical.rule.rule_type.value == "entitlement"


def test_non_normative_text_is_skipped_instead_of_becoming_a_rule():
    rules, skipped = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": "This handbook describes our culture.",
                        "extraction_status": "complete",
                        "rule": {"rule_type": "non_normative"},
                    }
                ],
                [],
            )
        )
    )

    assert rules == []
    assert len(skipped) == 1 and "non_normative" in skipped[0]["reason"]


def test_ambiguous_extraction_forces_human_judgment():
    rules, _ = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": "Long-serving staff may receive a suitable award.",
                        "extraction_status": "ambiguous",
                        "rule": {
                            "rule_type": "ambiguous",
                            "subject": "Long-serving staff",
                            "predicate": "receive",
                            "object": "a suitable award",
                        },
                        "ambiguity": ["AMBIGUOUS_THRESHOLD"],
                    }
                ],
                [],
            )
        )
    )

    (rule,) = rules
    assert rule.rule_type.value == "human_judgment_requirement"
    assert rule.ambiguity_status.value == "human_judgment_required"
    assert "AMBIGUOUS_THRESHOLD" in rule.description


def test_shared_decision_table_maps_each_row_to_its_own_rule():
    """Spec Section 91: several canonical rules may share one decision table."""

    band = lambda text, low: {  # noqa: E731
        "source_text": text,
        "extraction_status": "complete",
        "rule": {
            "rule_type": "conditional_outcome",
            "subject": "Expenses",
            "predicate": "route to",
            "object": "an approver",
            "threshold": low,
        },
    }
    formulation = parse_formulation(
        _envelope(
            [band("Under 5000 goes to a Manager.", "5000"), band("5000 or more goes to a Director.", "5000")],
            [
                {
                    "source_rule_indexes": [0, 1],
                    "dmn_mapping_status": "executable",
                    "requirements": [],
                    "decision_table": {
                        "hit_policy": "UNIQUE",
                        "inputs": [
                            {"label": "amount", "expression": "expense.amount", "type": "number"}
                        ],
                        "outputs": [
                            {"label": "route", "name": "approvalRoute", "type": "string"}
                        ],
                        "rules": [
                            {"input_entries": ["< 5000"], "output_entries": ['"Manager"']},
                            {"input_entries": [">= 5000"], "output_entries": ['"Director"']},
                        ],
                    },
                }
            ],
        )
    )

    rules, skipped = _map(formulation)

    assert skipped == []
    assert len(rules) == 2
    first, second = rules
    assert first.condition.all[0].operator.value == "lessThan"
    assert second.condition.all[0].operator.value == "greaterThanOrEqual"
    # Traceability survives slicing: shared indexes are preserved verbatim.
    assert first.formulation.source_index == 0
    assert second.formulation.source_index == 1
    assert second.formulation.dmn_decisions[0].source_rule_indexes == [0, 1]


def test_row_count_mismatch_refuses_to_guess_which_row_belongs_to_which_rule():
    formulation = _executable_expense_formulation()
    # Two source rules, one table row: the pairing is no longer determinable.
    formulation.dmn_projection.decisions[0].source_rule_indexes = [0, 1]

    rules, _ = _map(formulation)

    assert rules[0].machine_executable is False


def test_unexecutable_status_never_yields_a_condition_even_with_a_table():
    """`executable` is the agent's assertion that no fact was invented."""

    formulation = _executable_expense_formulation()
    formulation.dmn_projection.decisions[0].dmn_mapping_status = (
        DmnMappingStatus.ENRICHMENT_REQUIRED
    )

    rules, _ = _map(formulation)

    assert rules[0].machine_executable is False
    assert rules[0].condition.all == []


def test_all_any_value_row_is_not_treated_as_an_executable_condition():
    formulation = PolicyFormulation(
        canonical_policies=[
            CanonicalPolicy(
                source_text="Everyone follows the code of conduct.",
                rule=CanonicalPolicyRule(
                    rule_type=CanonicalRuleType.OBLIGATION,
                    subject="Everyone",
                    predicate="follow",
                    object="the code of conduct",
                ),
            )
        ],
        dmn_projection=DmnProjection(
            decisions=[
                DmnDecision(
                    source_rule_indexes=[0],
                    dmn_mapping_status=DmnMappingStatus.EXECUTABLE,
                    decision_table=DmnDecisionTable(
                        hit_policy="UNIQUE",
                        inputs=[DmnTableInput(expression="employee.id", type="string")],
                        outputs=[DmnTableOutput(name="applies", type="boolean")],
                        rules=[DmnTableRule(input_entries=["-"], output_entries=["true"])],
                    ),
                )
            ]
        ),
    )

    rules, _ = _map(formulation)

    assert rules[0].machine_executable is False


def test_rule_carries_its_formulation_for_audit():
    rules, _ = _map(_executable_expense_formulation())
    (rule,) = rules

    assert rule.formulation is not None
    assert rule.formulation.canonical.source_text.startswith("Expenses of 5000")
    assert rule.formulation.dmn_decisions[0].dmn_mapping_status.value == "executable"
    assert rule.lineage.prompt_version == "dmn-formulator-v1"
    # The whole rule must stay round-trippable, since it is persisted as JSONB.
    assert json.loads(json.dumps(rule.model_dump(mode="json")))["formulation"]["source_index"] == 0


class TestPartialBatchRecovery:
    """A malformed canonical policy must not take its valid siblings with it.

    Observed in production: a 30-policy extraction window was discarded whole
    because three entries wrapped `ambiguity` in an object instead of a list.
    """

    @staticmethod
    def _policy(text: str, ambiguity: object = None) -> dict:
        entry: dict = {
            "source_text": text,
            "extraction_status": "complete",
            "rule": {
                "rule_type": "obligation",
                "subject": "employer",
                "modality": "must",
                "predicate": "pay wages",
            },
        }
        if ambiguity is not None:
            entry["ambiguity"] = ambiguity
        return entry

    def _reply(self, policies: list[dict], decisions: list[dict] | None = None) -> str:
        return json.dumps(
            {
                "CANONICAL_JSON": {"canonical_policies": policies},
                "DMN_JSON": {"dmn_projection": {"decisions": decisions or []}},
            }
        )

    def test_valid_policies_survive_a_malformed_sibling(self) -> None:
        raw = self._reply(
            [
                self._policy("first"),
                self._policy("second", ambiguity=12345),
                self._policy("third"),
            ]
        )

        result = parse_formulation(raw)

        assert [p.source_text for p in result.canonical_policies] == ["first", "third"]

    def test_decision_indexes_follow_the_surviving_policies(self) -> None:
        """The bug that would replace the one being fixed.

        `source_rule_indexes` are positional, so compacting the list without
        remapping re-points a decision at a different rule than the agent
        named — a silent mislink, worse than the loud loss it replaced.
        """

        raw = self._reply(
            [
                self._policy("first"),
                self._policy("second", ambiguity=12345),
                self._policy("third"),
            ],
            decisions=[
                {"source_rule_indexes": [0], "dmn_mapping_status": "not_applicable"},
                {"source_rule_indexes": [2], "dmn_mapping_status": "not_applicable"},
            ],
        )

        result = parse_formulation(raw)

        assert result.decisions_for(0)
        assert result.decisions_for(1)
        assert [d.source_rule_indexes for d in result.dmn_projection.decisions] == [[0], [1]]

    def test_a_decision_left_with_no_source_rule_is_dropped(self) -> None:
        """Section 86 traceability: a decision that cannot name where it came
        from is not evidence a reviewer should be shown."""

        raw = self._reply(
            [self._policy("kept"), self._policy("bad", ambiguity=12345)],
            decisions=[
                {"source_rule_indexes": [1], "dmn_mapping_status": "not_applicable"}
            ],
        )

        result = parse_formulation(raw)

        assert len(result.canonical_policies) == 1
        assert result.dmn_projection.decisions == []


    def test_a_bad_projection_stays_loud_even_when_a_policy_was_salvaged(self) -> None:
        """Recovery must not widen what counts as an acceptable projection.

        Whether a sibling policy was malformed says nothing about whether the
        projection is valid, so an unknown `dmn_mapping_status` (Section 45)
        has to raise on this path exactly as it does on the ordinary one.
        """

        raw = self._reply(
            [self._policy("good"), self._policy("bad", ambiguity=12345)],
            decisions=[
                {"source_rule_indexes": [0], "dmn_mapping_status": "probably_fine"}
            ],
        )

        with pytest.raises(PolicyFormulationError):
            parse_formulation(raw)

    def test_a_wholly_malformed_batch_still_fails_loudly(self) -> None:
        """Recovery must not turn a total agent failure into an empty success."""

        raw = self._reply([self._policy("only", ambiguity=12345)])

        with pytest.raises(PolicyFormulationError):
            parse_formulation(raw)

    def test_a_well_formed_batch_is_untouched_by_recovery(self) -> None:
        raw = self._reply([self._policy("a"), self._policy("b")])

        result = parse_formulation(raw)

        assert len(result.canonical_policies) == 2


class TestAmbiguityCollectionShape:
    """The exact shape that lost a production window."""

    def test_an_object_wrapping_the_codes_list_is_unwrapped(self) -> None:
        policy = CanonicalPolicy.model_validate(
            {
                "source_text": "Such contract",
                "ambiguity": {
                    "codes": ["AMBIGUOUS_REFERENCE"],
                    "evidence": "the following:",
                },
            }
        )

        assert [code.value for code in policy.ambiguity] == ["AMBIGUOUS_REFERENCE"]

    def test_a_plain_list_of_codes_is_unaffected(self) -> None:
        policy = CanonicalPolicy.model_validate(
            {"source_text": "x", "ambiguity": ["AMBIGUOUS_REFERENCE"]}
        )

        assert [code.value for code in policy.ambiguity] == ["AMBIGUOUS_REFERENCE"]


class TestSemanticProjectionShapeVariance:
    """A list-shaped projection field must not cost the batch it arrived in.

    Observed in production: an MHRSD extraction window was discarded whole
    because one decision carried `object: ["modest", "loose", "opaque"]` where
    the source listed three adjectives and the agent kept them apart. Unlike a
    malformed canonical policy, which `_salvage_valid_policies` limits to
    costing itself, a projection failure re-raises for the entire batch.
    """

    @staticmethod
    def _reply(projection_field: str, value: object) -> str:
        return json.dumps(
            {
                "CANONICAL_JSON": {
                    "canonical_policies": [
                        {
                            "source_text": "clothing must be modest, loose and opaque",
                            "extraction_status": "complete",
                            "rule": {"rule_type": "obligation", "subject": "worker"},
                        }
                    ]
                },
                "DMN_JSON": {
                    "dmn_projection": {
                        "decisions": [
                            {
                                "source_rule_indexes": [0],
                                "dmn_mapping_status": "not_directly_mappable",
                                "semantic_projection": {projection_field: value},
                            }
                        ]
                    }
                },
            }
        )

    @pytest.mark.parametrize("field", ["subject", "predicate", "object"])
    def test_a_list_valued_triple_field_is_joined_not_fatal(self, field: str) -> None:
        raw = self._reply(field, ["modest", "loose", "opaque"])

        result = parse_formulation(raw)

        assert len(result.canonical_policies) == 1
        decision = result.dmn_projection.decisions[0]
        assert decision.semantic_projection is not None
        assert getattr(decision.semantic_projection, field) == "modest | loose | opaque"

    def test_a_scalar_field_is_left_untouched(self) -> None:
        """Coercion must not reshape the shape the contract already expects."""

        raw = self._reply("object", "modest clothing")

        result = parse_formulation(raw)

        projection = result.dmn_projection.decisions[0].semantic_projection
        assert projection is not None
        assert projection.object == "modest clothing"

    def test_an_unknown_mapping_status_still_fails_loudly(self) -> None:
        """The re-raise this coercion sits beside must keep its teeth.

        Section 45 makes an unrecognized `dmn_mapping_status` a genuine break,
        not a shape variance, so recovering from the latter must not quietly
        widen what counts as an acceptable projection.
        """

        raw = json.dumps(
            {
                "CANONICAL_JSON": {
                    "canonical_policies": [
                        {
                            "source_text": "text",
                            "extraction_status": "complete",
                            "rule": {"rule_type": "obligation"},
                        }
                    ]
                },
                "DMN_JSON": {
                    "dmn_projection": {
                        "decisions": [
                            {
                                "source_rule_indexes": [0],
                                "dmn_mapping_status": "invented_status",
                            }
                        ]
                    }
                },
            }
        )

        with pytest.raises(PolicyFormulationError):
            parse_formulation(raw)
