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
import logging

import pytest

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
    DmnDecisionTable,
    DmnMappingStatus,
    DmnProjection,
    DmnRequirementCode,
    DmnTableInput,
    DmnTableOutput,
    DmnTableRule,
    PolicyFormulation,
)
from policy_platform.contracts.passage import PassageSource, PolicyPassage
from policy_platform.infrastructure.extraction.formulation_mapping import (
    formulation_to_candidate_rules,
    parse_feel_unary_test,
)
from policy_platform.infrastructure.extraction.policy_formulator import (
    PolicyFormulationError,
    PolicyFormulatorAgent,
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
    assert "dependencies" not in dumped


def test_enrichment_demands_are_kept_in_memory_but_never_served():
    """They say what someone would have to supply, not what the policy says.

    Across a whole document not one decision produced a table, and every record
    carried two or three of these codes — a standing demand attached to
    policies that are AI Ready rather than decided by arithmetic. Tooling
    that acts on them still reads the parsed object.
    """

    decision = DmnDecision(
        source_rule_indexes=[0],
        dmn_mapping_status=DmnMappingStatus.ENRICHMENT_REQUIRED,
        requirements=[DmnRequirementCode.FACT_MODEL_REQUIRED],
    )

    assert decision.requirements == [DmnRequirementCode.FACT_MODEL_REQUIRED]
    assert "requirements" not in decision.model_dump(mode="json")


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
    """Spec Section 106: not every policy is a decision — keep it, don't force it.

    `ambiguity_status` must be `non_blocking`, not `human_judgment_required`:
    the source text here is perfectly clear, it just has no derivable machine
    condition. Forcing HUMAN_JUDGMENT_REQUIRED purely from non-executability
    was the bug that made every rule in a config-less extraction run look
    equally "ambiguous" regardless of actual wording clarity.
    """

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
    assert rule.ambiguity_status.value == "none"
    assert rule.condition.type == "all" and rule.condition.all == []
    assert rule.rule_type.value == "obligation"
    assert rule.effect.type.value == "require_action"
    assert rule.effect.action == "evaluate the performance of employees they supervise"
    # The projection status stays on the projection. It describes DMN, not the
    # policy, so it no longer pollutes the description a reviewer reads.
    assert rule.description == rule.formulation.canonical.source_text.strip()
    assert "not_directly_mappable" not in rule.description
    assert rule.formulation.dmn_decisions[0].dmn_mapping_status.value == "not_directly_mappable"


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
    # The codes are technical notes to a configuration author, so they live on
    # the projection that raised them rather than in the reviewer's
    # description. What matters is that nothing was lost in moving them.
    assert rule.description == rule.formulation.canonical.source_text.strip()
    codes = [r.value for r in rule.formulation.dmn_decisions[0].requirements]
    assert codes == ["FACT_MODEL_REQUIRED", "VALUE_NORMALIZATION_REQUIRED"]
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


def test_definition_gets_informational_effect_not_a_false_allow():
    """Regression guard for the polarity-reversal defect (ai_quality.py's
    `_definition_effect_findings` docstring): a `definition` rule must not be
    forced into `allow`, and Stage 2's idiomatic `predicate=":"`
    term-separator must not leak a stray leading colon into `effect.action`.
    """

    rules, skipped = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": "Temporary Work: Work considered by its nature to end "
                        "within a limited period.",
                        "extraction_status": "complete",
                        "rule": {
                            "rule_type": "definition",
                            "subject": "Temporary Work",
                            "predicate": ":",
                            "object": "Work considered by its nature to end within a limited period.",
                        },
                    }
                ],
                [],
            )
        )
    )

    assert skipped == []
    (rule,) = rules
    assert rule.rule_type.value == "definition"
    assert rule.effect.type.value == "informational"
    assert rule.effect.action == "Work considered by its nature to end within a limited period."
    assert not rule.effect.action.startswith(":")
    assert rule.title == "Temporary Work Work considered by its nature to end within a limited period."


def test_classification_gets_informational_effect_too():
    rules, _ = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": "Workers are classified as either permanent or temporary.",
                        "extraction_status": "complete",
                        "rule": {
                            "rule_type": "classification",
                            "subject": "Workers",
                            "predicate": "classified as",
                            "object": "either permanent or temporary",
                        },
                    }
                ],
                [],
            )
        )
    )

    (rule,) = rules
    assert rule.rule_type.value == "definition"
    assert rule.effect.type.value == "informational"


def test_effect_action_is_not_silently_truncated():
    """Regression guard for the `data_integrity` defect the quality dashboard
    flagged: `_effect_action` used to hard-cut at 200 characters with no
    ellipsis, so a long definition's object lost its tail with no sign
    anything was missing. `effect.action` is evaluator-facing (the deny/allow
    combining algorithm returns it verbatim as the decision outcome), so it
    must carry the full text, unlike the display-only `title`.
    """

    long_object = (
        "The basic wage plus all other due increments decided for a worker for the effort "
        "he exerts at work or for risks he encounters in the course of performing his work, "
        "or those benefits stipulated in his employment contract or the firm's regulations."
    )
    assert len(long_object) > 200

    rules, skipped = _map(
        parse_formulation(
            _envelope(
                [
                    {
                        "source_text": f"Actual Wage: {long_object}",
                        "extraction_status": "complete",
                        "rule": {
                            "rule_type": "definition",
                            "subject": "Actual Wage",
                            "predicate": ":",
                            "object": long_object,
                        },
                    }
                ],
                [],
            )
        )
    )

    assert skipped == []
    (rule,) = rules
    assert rule.effect.action == long_object
    assert rule.effect.action.endswith("regulations.")


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
    # The ambiguity code is on the canonical record, which is where it was
    # raised. The description stays the policy as written.
    assert [a.value for a in rule.formulation.canonical.ambiguity] == ["AMBIGUOUS_THRESHOLD"]


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


# --------------------------------------------------------------------------
# Per-rule evidence scoping
#
# A batch commonly bundles Stage-1 passages copied from several unrelated
# clauses (a document is walked in fixed-size windows, not one topic at a
# time). Every rule the formulator drafts from that batch must cite only the
# clause(s) its own passage came from — never every clause anywhere in the
# batch, which would make an unrelated clause's wording appear to justify a
# rule it has nothing to do with. This is the same many-to-many
# rule-to-provision precision that document-interchange standards for
# normative text require, and applies to any source document type (statute,
# HR handbook, IT policy, procurement manual, ...).
# --------------------------------------------------------------------------


def _two_topic_formulation() -> PolicyFormulation:
    return parse_formulation(
        _envelope(
            [
                {
                    "source_text": "Seasonal workers are exempt from the notice period "
                    "requirement.",
                    "extraction_status": "complete",
                    "rule": {
                        "rule_type": "obligation",
                        "subject": "Seasonal workers",
                        "modality": "shall",
                        "predicate": "be exempt from",
                        "object": "the notice period requirement",
                    },
                },
                {
                    "source_text": "Any condition that conflicts with the provisions of this "
                    "Law shall be deemed null and void.",
                    "extraction_status": "complete",
                    "rule": {
                        "rule_type": "obligation",
                        "subject": "Any condition that conflicts with the provisions of this Law",
                        "modality": "shall",
                        "predicate": "be deemed",
                        "object": "null and void",
                    },
                },
            ],
            [],
        )
    )


def _two_topic_passages() -> list[PolicyPassage]:
    return [
        PolicyPassage(
            passage_id="p1",
            text="Seasonal workers are exempt from the notice period requirement.",
            source=PassageSource(clause_ref="p5-E000039", section="Article 6"),
        ),
        PolicyPassage(
            passage_id="p2",
            text="Any condition that conflicts with the provisions of this Law shall be "
            "deemed null and void.",
            source=PassageSource(clause_ref="p5-6-E000050", section="Article 8"),
        ),
    ]


def test_evidence_is_scoped_to_the_matching_passage_not_the_whole_batch():
    passages = _two_topic_passages()
    passage_clause_refs = [["p5-E000039"], ["p5-6-E000050"]]
    clause_evidence_by_ref = {
        "p5-E000039": {"document_version_id": "doc-1", "source_hash": "h", "clause_id": "c-39"},
        "p5-6-E000050": {"document_version_id": "doc-1", "source_hash": "h", "clause_id": "c-50"},
    }
    whole_batch_evidence = [
        clause_evidence_by_ref["p5-E000039"],
        clause_evidence_by_ref["p5-6-E000050"],
    ]

    rules, skipped = formulation_to_candidate_rules(
        _two_topic_formulation(),
        policy_set_id="ps-1",
        extraction_run_id="run-1",
        deployment_name="test-deployment",
        prompt_version="dmn-formulator-v1",
        parser_version="dmn-formulator-v1",
        evidence=whole_batch_evidence,
        passages=passages,
        passage_clause_refs=passage_clause_refs,
        clause_evidence_by_ref=clause_evidence_by_ref,
        source_note="p5-E000039; p5-6-E000050",
    )

    assert skipped == []
    seasonal_rule, null_and_void_rule = rules

    # The seasonal-worker rule must cite only its own clause...
    assert [ev.clause_id for ev in seasonal_rule.evidence] == ["c-39"]
    # ...and the null-and-void rule must cite only *its* clause, not the
    # unrelated seasonal-worker clause the old whole-batch evidence would
    # have attached.
    assert [ev.clause_id for ev in null_and_void_rule.evidence] == ["c-50"]
    assert "p5-6-E000050" in null_and_void_rule.lineage.source_elements
    assert "p5-E000039" not in null_and_void_rule.lineage.source_elements


def test_evidence_falls_back_to_whole_batch_when_no_passage_matches():
    """An unmatched policy keeps the coarse fallback rather than losing evidence.

    A missed match should degrade to the old (imprecise but non-empty)
    behavior, not to nothing — an admittedly coarse citation is still more
    useful to a reviewer than none.
    """

    passages = [
        PolicyPassage(
            passage_id="p1",
            text="Completely unrelated passage text that shares no wording.",
            source=PassageSource(clause_ref="p5-E000039"),
        )
    ]
    passage_clause_refs = [["p5-E000039"]]
    clause_evidence_by_ref = {
        "p5-E000039": {"document_version_id": "doc-1", "source_hash": "h", "clause_id": "c-39"},
    }
    fallback_evidence = [{"document_version_id": "doc-1", "source_hash": "h", "clause_id": "c-fallback"}]

    rules, _ = formulation_to_candidate_rules(
        _executable_expense_formulation(),
        policy_set_id="ps-1",
        extraction_run_id="run-1",
        deployment_name="test-deployment",
        prompt_version="dmn-formulator-v1",
        parser_version="dmn-formulator-v1",
        evidence=fallback_evidence,
        passages=passages,
        passage_clause_refs=passage_clause_refs,
        clause_evidence_by_ref=clause_evidence_by_ref,
        source_note="fallback-note",
    )

    (rule,) = rules
    assert [ev.clause_id for ev in rule.evidence] == ["c-fallback"]


# --------------------------------------------------------------------------
# Evidence precision, second level: narrowing a passage's clause span down to
# the clause(s) that actually carry the rule.
#
# Matching a rule to its passage is not sufficient on its own. One Stage-1
# passage routinely covers a contiguous block that ingestion split into several
# clauses — a definitions article, an eligibility section — so every rule
# formulated from that block inherits the block's whole span. Observed on the
# Saudi Labor Law corpus: 21 separate definition rules all cited the identical
# four clauses, which reads to a reviewer as the platform claiming each rule
# came from all four.
# --------------------------------------------------------------------------

_DEFINITIONS_BLOB = (
    "In this Law, the following terms shall have the meanings assigned thereto, "
    "unless the context requires otherwise: Ministry: Ministry of Labor. "
    "Minor: Any person of 15 and below 18 years of age. "
    "Service shall be deemed continuous if interrupted by the following:"
)
_CONTINUOUS_SERVICE_TEXT = (
    "Service shall be deemed continuous if interrupted by the following: "
    "1. Official holidays and vacations. "
    "2. Interruptions for sitting for examinations in accordance with the provisions of this Law."
)

_DEFINITIONS_CLAUSE_TEXTS = {
    "p3-E000016": _DEFINITIONS_BLOB,
    "p3-E000017": "1. Official holidays and vacations.",
    "p3-E000018": "2. Interruptions for sitting for examinations in accordance with the provisions of this Law.",
    "p4-E000019": "3. Worker's unpaid absences from work for intermittent periods not exceeding 20 days per work year.",
}

_DEFINITIONS_EVIDENCE = {
    ref: {"document_version_id": "doc-1", "source_hash": "h", "clause_id": f"c-{ref[-2:]}"}
    for ref in _DEFINITIONS_CLAUSE_TEXTS
}


def _definitions_block_formulation() -> PolicyFormulation:
    return parse_formulation(
        _envelope(
            [
                {
                    "source_text": "Minor: Any person of 15 and below 18 years of age.",
                    "extraction_status": "complete",
                    "rule": {
                        "rule_type": "definition",
                        "subject": "Minor",
                        "predicate": "means",
                        "object": "Any person of 15 and below 18 years of age",
                    },
                },
                {
                    "source_text": _CONTINUOUS_SERVICE_TEXT,
                    "extraction_status": "complete",
                    "rule": {
                        "rule_type": "definition",
                        "subject": "Continuous service",
                        "predicate": "includes",
                        "object": "listed interruptions",
                    },
                },
            ],
            [],
        )
    )


def _definitions_block_call(**overrides):
    """One Stage-1 passage spanning the whole four-clause definitions block."""

    passage = PolicyPassage(
        passage_id="p1",
        text=_DEFINITIONS_BLOB + " " + _CONTINUOUS_SERVICE_TEXT,
        source=PassageSource(
            clause_ref="p3-E000016", end_clause_ref="p4-E000019", section="Article 2"
        ),
    )
    kwargs = {
        "policy_set_id": "ps-1",
        "extraction_run_id": "run-1",
        "deployment_name": "test-deployment",
        "prompt_version": "dmn-formulator-v1",
        "parser_version": "dmn-formulator-v1",
        "evidence": list(_DEFINITIONS_EVIDENCE.values()),
        "passages": [passage],
        "passage_clause_refs": [list(_DEFINITIONS_CLAUSE_TEXTS)],
        "clause_evidence_by_ref": _DEFINITIONS_EVIDENCE,
        "source_note": "; ".join(_DEFINITIONS_CLAUSE_TEXTS),
    }
    kwargs.update(overrides)
    return formulation_to_candidate_rules(_definitions_block_formulation(), **kwargs)


def test_evidence_narrows_to_the_clause_that_actually_contains_the_rule():
    rules, skipped = _definitions_block_call(clause_texts_by_ref=_DEFINITIONS_CLAUSE_TEXTS)

    assert skipped == []
    minor_rule, continuous_service_rule = rules

    # "Minor" is defined inside the first clause only. Its three neighbours in
    # the same passage span are other provisions, not this rule's source.
    assert [ev.clause_id for ev in minor_rule.evidence] == ["c-16"]
    assert "p3-E000017" not in minor_rule.lineage.source_elements

    # The continuous-service rule legitimately spans the numbered items, so it
    # keeps exactly those — the converse containment direction — and does not
    # pick up the unrelated third item.
    assert [ev.clause_id for ev in continuous_service_rule.evidence] == ["c-17", "c-18"]


def test_evidence_keeps_the_full_span_when_clause_texts_are_not_supplied():
    """Narrowing is additive: callers that pass no clause text are unaffected."""

    rules, _ = _definitions_block_call()

    for rule in rules:
        assert [ev.clause_id for ev in rule.evidence] == ["c-16", "c-17", "c-18", "c-19"]


def test_evidence_falls_back_to_the_span_when_no_clause_matches():
    """A rule the mapper cannot pin to one clause keeps the coarser span.

    Same principle as the whole-batch fallback: an imprecise citation beats an
    empty one, so narrowing must never be able to delete a rule's evidence.
    """

    unrelated = {ref: "Text sharing no wording at all." for ref in _DEFINITIONS_CLAUSE_TEXTS}
    rules, _ = _definitions_block_call(clause_texts_by_ref=unrelated)

    for rule in rules:
        assert [ev.clause_id for ev in rule.evidence] == ["c-16", "c-17", "c-18", "c-19"]


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


class TestTrustedConfigShapeWarnings:
    """A wrong-shaped trusted config must not fail silently.

    A config the agent cannot use produces output identical to supplying none:
    well-formed, and still reporting FACT_MODEL_REQUIRED. The caller's only
    signal is the absence of an expected improvement, which is not a signal.
    """

    @staticmethod
    def _agent(config: dict) -> PolicyFormulatorAgent:
        return PolicyFormulatorAgent(
            client=object(),  # type: ignore[arg-type]
            settings=object(),  # type: ignore[arg-type]
            trusted_config=config,
        )

    def test_an_unknown_top_level_key_is_named(self, caplog) -> None:
        """`temporal_model` is a reasonable guess and is not in Section 83."""

        with caplog.at_level(logging.WARNING):
            self._agent({"temporal_model": {"a": 1}})

        assert "temporal_model" in caplog.text
        assert "Section 83" in caplog.text

    def test_a_valid_config_warns_about_nothing(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            self._agent(
                {
                    "fact_model": {
                        "age of the worker": {
                            "feel_expression": "worker.ageYears",
                            "type": "number",
                        }
                    },
                    "output_model": {
                        "outcome": {"feel_name": "outcome", "type": "string"}
                    },
                    "numeric_normalization": True,
                }
            )

        assert caplog.text == ""

    def test_keying_a_fact_by_its_feel_path_is_flagged(self, caplog) -> None:
        """The shape that silently costs a whole agent run to discover."""

        with caplog.at_level(logging.WARNING):
            self._agent({"fact_model": {"worker.ageYears": {"type": "number"}}})

        assert "worker.ageYears" in caplog.text
        assert "feel_expression" in caplog.text
        assert "SOURCE TERM" in caplog.text

    def test_output_model_is_checked_for_its_own_key(self, caplog) -> None:
        """`output_model` uses `feel_name`, not `feel_expression`."""

        with caplog.at_level(logging.WARNING):
            self._agent(
                {"output_model": {"approval route": {"feel_expression": "route"}}}
            )

        assert "approval route" in caplog.text
        assert "feel_name" in caplog.text

    def test_an_empty_config_is_silent(self, caplog) -> None:
        """Supplying nothing is a documented, valid operating mode."""

        with caplog.at_level(logging.WARNING):
            self._agent({})

        assert caplog.text == ""

