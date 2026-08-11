"""Why a decision failed to compile — measured against real agent output.

Every payload below was captured verbatim from the formulator agent running
against AD-103 clauses 3.2.1 and 3.2.3 with a trusted fact model installed.
That matters: before these tests existed, six of six `executable` decisions
produced by live runs compiled to nothing, and every one of them reported the
same bare `None` as an ordinary non-executable rule. The platform therefore
told reviewers to "supply the missing mapping" for rules whose mapping was
already complete.

These tests pin the distinction that was missing, not the compiler's coverage.
Extending coverage is a separate, larger change (it needs the condition
contract and the evaluator to represent fact-relative comparison); until then
the gap must at least be visible and correctly attributed.
"""
from __future__ import annotations

import json

import pytest

from policy_platform.contracts.formulation import (
    AmbiguityCode,
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    DmnDecision,
)
from policy_platform.contracts.policy import AmbiguityStatus
from policy_platform.infrastructure.formulation_mapping import (
    ConditionDerivationReason,
    _ambiguity_for,
    condition_provenance,
    derive_condition,
    derive_condition_outcome,
)

# --------------------------------------------------------------------------
# Verbatim agent output
# --------------------------------------------------------------------------

#: AD-103 clause 3.2.1, emitted on 3 of 3 trials once the fact model named the
#: clause's terms. A complete, grounded FEEL expression — and the shape the
#: compiler never reads.
LITERAL_EXPRESSION_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "literal_expression": {
        "output": {"name": "annual_increase_permitted", "type": "boolean"},
        "feel": (
            "employee.compensation.proposed_annual_increase <= "
            "employee.compensation.current_basic_salary * 0.10"
        ),
    },
}

#: AD-103 clause 3.2.3. A decision *table* comparing against a percentage of
#: another fact. This is now compiled (see `test_fact_relative_table_compiles`);
#: it is kept here as the record of what drove the condition-contract change.
FACT_RELATIVE_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [
            {
                "label": "inflation increase",
                "expression": "employee.compensation.proposed_inflation_increase",
                "type": "number",
            },
            {
                "label": "approval of the Board of Trustees",
                "expression": "approval.board_of_trustees_approved",
                "type": "boolean",
            },
        ],
        "outputs": [
            {
                "label": "inflation increase permitted",
                "name": "inflation_increase_permitted",
                "type": "boolean",
            }
        ],
        "rules": [
            {
                "input_entries": [
                    "<= employee.compensation.basic_salary * 0.05",
                    "true",
                ],
                "output_entries": ["true"],
            }
        ],
    },
}

#: The shape the compiler *does* support, kept as the control: without it, a
#: test asserting "these do not compile" would pass even if nothing compiled.
SUPPORTED_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [{"label": "expense amount", "expression": "expense.amount", "type": "number"}],
        "outputs": [{"label": "route", "name": "approvalRoute", "type": "string"}],
        "rules": [{"input_entries": [">= 5000"], "output_entries": ['"executive"']}],
    },
}


#: Genuinely outside the supported subset: a function call. Kept so
#: `UNSUPPORTED_UNARY_TEST` still has a real example after fact-relative
#: arithmetic became supported — without one, the reason code would be
#: asserted by no test at all.
UNPARSEABLE_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [
            {"label": "start", "expression": "employee.start_date", "type": "date"}
        ],
        "outputs": [{"label": "ok", "name": "ok", "type": "boolean"}],
        "rules": [
            {
                "input_entries": ["< date(employee.start_date) + duration(\"P1Y\")"],
                "output_entries": ["true"],
            }
        ],
    },
}


#: Verbatim from a live trial: one source rule, three rows, a boolean outcome.
#: Ordinary DMN — a single obligation enumerated as the combinations that
#: satisfy it. The compiler used to refuse this because it required one row
#: per source rule, which is why 2 of 3 live trials produced nothing.
BOOLEAN_OUTCOME_TABLE_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "decision_table": {
        "hit_policy": "UNIQUE",
        "inputs": [
            {
                "label": "increase",
                "expression": "employee.compensation.proposed_inflation_increase",
                "type": "number",
            },
            {
                "label": "approval",
                "expression": "approval.board_of_trustees_approved",
                "type": "boolean",
            },
        ],
        "outputs": [
            {"label": "permitted", "name": "inflation_increase_permitted", "type": "boolean"}
        ],
        "rules": [
            {
                "input_entries": ["<= employee.compensation.basic_salary * 0.05", "true"],
                "output_entries": ["true"],
            },
            {
                "input_entries": ["> employee.compensation.basic_salary * 0.05", "-"],
                "output_entries": ["false"],
            },
            {
                "input_entries": ["<= employee.compensation.basic_salary * 0.05", "false"],
                "output_entries": ["false"],
            },
        ],
    },
}


#: A literal expression still outside the grammar: `or` mixed with `and` needs
#: precedence handling the parser deliberately does not do.
UNSUPPORTED_LITERAL_DECISION = {
    "source_rule_indexes": [0],
    "dmn_mapping_status": "executable",
    "requirements": [],
    "literal_expression": {
        "output": {"name": "annual_increase_permitted", "type": "boolean"},
        "feel": (
            "employee.compensation.proposed_annual_increase <= "
            "employee.compensation.current_basic_salary * 0.10 "
            "or employee.performance.appraisal_rating = \"outstanding\""
        ),
    },
}


def _decision(payload: dict) -> DmnDecision:
    return DmnDecision.model_validate(payload)


def _policy(condition: str | None) -> CanonicalPolicy:
    rule = CanonicalPolicyRule(
        rule_type=CanonicalRuleType.OBLIGATION,
        subject="the University",
        predicate="grant",
        object="the annual increase",
        condition=condition,
    )
    return CanonicalPolicy(source_text="The University shall grant the annual increase.", rule=rule)


# --------------------------------------------------------------------------
# The control: the compiler still works where it always worked
# --------------------------------------------------------------------------


def test_supported_table_still_compiles():
    """Guards the tests below: they only mean something if compilation works."""

    outcome = derive_condition_outcome(_decision(SUPPORTED_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert outcome.derived is True
    assert outcome.platform_limited is False
    assert [f.name for f in outcome.facts] == ["expense.amount"]


def test_wrapper_agrees_with_outcome_on_success():
    """The tuple API and the outcome API are one implementation, not two."""

    decision = _decision(SUPPORTED_TABLE_DECISION)
    outcome = derive_condition_outcome(decision, 0)
    wrapped = derive_condition(decision, 0)

    assert wrapped is not None
    condition, facts = wrapped
    assert condition == outcome.condition
    assert facts == list(outcome.facts)


# --------------------------------------------------------------------------
# The two real failures, each named rather than collapsed to None
# --------------------------------------------------------------------------


def test_literal_expression_is_reported_not_silently_dropped():
    outcome = derive_condition_outcome(_decision(UNSUPPORTED_LITERAL_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.LITERAL_EXPRESSION_UNSUPPORTED
    assert outcome.derived is False
    assert outcome.platform_limited is True
    # The reviewer sees exactly what the agent produced, not a paraphrase.
    assert outcome.unsupported_expression.startswith(
        "employee.compensation.proposed_annual_increase <="
    )
    assert " or " in outcome.unsupported_expression


def test_fact_relative_table_compiles():
    """The clause that motivated extending the condition contract.

    This decision used to fail with `UNSUPPORTED_UNARY_TEST`. It now compiles,
    and the fact it compares *against* — which is not a table column — must
    appear in `required_facts`, or the rule blocks at evaluation time on an
    input no caller was told to supply.
    """

    outcome = derive_condition_outcome(_decision(FACT_RELATIVE_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert [f.name for f in outcome.facts] == [
        "employee.compensation.proposed_inflation_increase",
        "employee.compensation.basic_salary",
        "approval.board_of_trustees_approved",
    ]


def test_a_genuinely_unsupported_test_is_still_refused():
    """Widening the parser must not turn it into a guesser."""

    outcome = derive_condition_outcome(_decision(UNPARSEABLE_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.UNSUPPORTED_UNARY_TEST
    assert outcome.platform_limited is True
    assert "duration" in outcome.unsupported_expression


# --------------------------------------------------------------------------
# A boolean-outcome table: many rows, one rule
# --------------------------------------------------------------------------


def test_a_boolean_outcome_table_compiles_to_its_satisfying_rows():
    """The rule's condition is the combination that yields true."""

    outcome = derive_condition_outcome(_decision(BOOLEAN_OUTCOME_TABLE_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert [f.name for f in outcome.facts] == [
        "employee.compensation.proposed_inflation_increase",
        "employee.compensation.basic_salary",
        "approval.board_of_trustees_approved",
    ]


def test_the_false_rows_do_not_leak_into_the_condition():
    """Only the satisfying row contributes.

    Reading a "false" row as a condition would invert the rule — the single
    worst output this system can produce.
    """

    outcome = derive_condition_outcome(_decision(BOOLEAN_OUTCOME_TABLE_DECISION), 0)
    tree = outcome.condition.model_dump(mode="json")

    # One satisfying row, so the tree is that row's AND, not an OR of three.
    assert tree["type"] == "all"
    operators = [leaf["operator"] for leaf in tree["all"]]
    assert operators == ["lessThanOrEqual", "equals"]
    assert "greaterThan" not in operators


def test_two_satisfying_rows_become_an_or():
    payload = json.loads(json.dumps(BOOLEAN_OUTCOME_TABLE_DECISION))
    payload["decision_table"]["rules"][2]["output_entries"] = ["true"]

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert outcome.condition.model_dump(mode="json")["type"] == "any"


def test_a_table_that_never_yields_true_is_refused_not_asserted():
    """"Never satisfiable" is a stronger claim than "could not compile"."""

    payload = json.loads(json.dumps(BOOLEAN_OUTCOME_TABLE_DECISION))
    payload["decision_table"]["rules"][0]["output_entries"] = ["false"]

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.NO_SATISFYING_ROW
    assert outcome.condition is None


def test_an_unconditionally_satisfied_row_is_vacuous_not_executable():
    payload = json.loads(json.dumps(BOOLEAN_OUTCOME_TABLE_DECISION))
    payload["decision_table"]["rules"][0]["input_entries"] = ["-", "-"]

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.VACUOUS
    assert outcome.condition is None


def test_a_non_boolean_multi_row_table_is_still_refused():
    """The OR reading only makes sense for a true/false outcome.

    A table whose rows select among several outcomes carries no single
    "condition under which the rule applies", so guessing one would invent a
    meaning the table never expressed.
    """

    payload = json.loads(json.dumps(BOOLEAN_OUTCOME_TABLE_DECISION))
    payload["decision_table"]["outputs"] = [
        {"label": "route", "name": "approvalRoute", "type": "string"}
    ]
    for i, entry in enumerate(['"board"', '"none"', '"manager"']):
        payload["decision_table"]["rules"][i]["output_entries"] = [entry]

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.NO_TABLE_ROW
    assert outcome.condition is None


def test_the_positional_reading_still_wins_when_it_applies():
    """One row per source rule keeps its existing meaning.

    Both readings can be legal for the same table shape, so the order matters:
    a two-rule/two-row table must stay positional rather than being re-read as
    an OR that merges two distinct rules into one.
    """

    payload = {
        "source_rule_indexes": [0, 1],
        "dmn_mapping_status": "executable",
        "requirements": [],
        "decision_table": {
            "hit_policy": "UNIQUE",
            "inputs": [
                {"label": "amount", "expression": "expense.amount", "type": "number"}
            ],
            "outputs": [{"label": "ok", "name": "ok", "type": "boolean"}],
            "rules": [
                {"input_entries": [">= 5000"], "output_entries": ["true"]},
                {"input_entries": ["< 100"], "output_entries": ["true"]},
            ],
        },
    }

    first = derive_condition_outcome(_decision(payload), 0)
    second = derive_condition_outcome(_decision(payload), 1)

    assert first.condition.model_dump(mode="json")["all"][0]["operator"] == (
        "greaterThanOrEqual"
    )
    assert second.condition.model_dump(mode="json")["all"][0]["operator"] == "lessThan"


# --------------------------------------------------------------------------
# Literal expressions
# --------------------------------------------------------------------------


def test_the_real_literal_expression_compiles():
    """The shape the formulator uses most often for compensation limits."""

    outcome = derive_condition_outcome(_decision(LITERAL_EXPRESSION_DECISION), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    assert [(f.name, f.data_type) for f in outcome.facts] == [
        ("employee.compensation.proposed_annual_increase", "number"),
        ("employee.compensation.current_basic_salary", "number"),
    ]


def test_a_conjunction_with_a_boolean_gate_compiles():
    """AD-103 3.2.3 as a literal: a proportional limit AND an approval."""

    payload = {
        "source_rule_indexes": [0],
        "dmn_mapping_status": "executable",
        "requirements": [],
        "literal_expression": {
            "output": {"name": "inflation_increase_permitted", "type": "boolean"},
            "feel": (
                "employee.compensation.proposed_inflation_increase <= "
                "employee.compensation.basic_salary * 0.05 "
                "and approval.board_of_trustees_approved"
            ),
        },
    }

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.DERIVED
    # The bare boolean fact is typed from what the agent wrote, not guessed.
    assert ("approval.board_of_trustees_approved", "boolean") in [
        (f.name, f.data_type) for f in outcome.facts
    ]


@pytest.mark.parametrize(
    "feel",
    [
        "a.b > 1 or a.c < 2",
        "a.b > 1 and (a.c < 2)",
        "if a.b then 1 else 2",
        "count(a.b) > 1",
        "not a.b",
        "a.b + a.c > 5",
        "sum(x.y)",
        "",
        "a.b >",
        "salary <= 100",
    ],
)
def test_literal_expressions_outside_the_grammar_are_refused(feel):
    """Widening this parser must not make it a guesser either.

    `or` is refused despite `AnyCondition` existing: mixing it with `and`
    needs precedence handling this parser does not do, and getting that wrong
    inverts rules silently.
    """

    payload = {
        "source_rule_indexes": [0],
        "dmn_mapping_status": "executable",
        "literal_expression": {"output": {"name": "o", "type": "boolean"}, "feel": feel},
    }

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.reason is ConditionDerivationReason.LITERAL_EXPRESSION_UNSUPPORTED
    assert outcome.condition is None


def test_a_refused_literal_still_reports_what_it_could_not_read():
    payload = {
        "source_rule_indexes": [0],
        "dmn_mapping_status": "executable",
        "literal_expression": {
            "output": {"name": "o", "type": "boolean"},
            "feel": "a.b > 1 or a.c < 2",
        },
    }

    outcome = derive_condition_outcome(_decision(payload), 0)

    assert outcome.platform_limited is True
    assert outcome.unsupported_expression == "a.b > 1 or a.c < 2"


def test_ordinary_non_executable_is_not_mistaken_for_a_platform_limit():
    """The common case must stay distinguishable from the two above."""

    outcome = derive_condition_outcome(
        _decision(
            {
                "source_rule_indexes": [0],
                "dmn_mapping_status": "enrichment_required",
                "requirements": ["FACT_MODEL_REQUIRED"],
            }
        ),
        0,
    )

    assert outcome.reason is ConditionDerivationReason.NOT_DECLARED_EXECUTABLE
    assert outcome.platform_limited is False


@pytest.mark.parametrize(
    "payload",
    [UNSUPPORTED_LITERAL_DECISION, UNPARSEABLE_TABLE_DECISION],
    ids=["unsupported_literal", "unparseable_table"],
)
def test_grounded_but_uncompilable_never_becomes_executable(payload):
    """Naming the failure must not soften the gate.

    The whole point of the `executable` gate is that an uncompilable decision
    stays non-executable. Reporting *why* must not become a way to let one
    through.
    """

    assert derive_condition(_decision(payload), 0) is None


# --------------------------------------------------------------------------
# The reviewer-facing consequence
# --------------------------------------------------------------------------


def test_platform_limit_does_not_blame_the_fact_model():
    """The defect this whole module exists to prevent.

    The old message said "a reviewer must supply the missing mapping" for a
    rule whose mapping was already supplied and correct — sending a human to
    edit a fact model that was not the problem.
    """

    outcome = derive_condition_outcome(_decision(UNSUPPORTED_LITERAL_DECISION), 0)
    provenance = condition_provenance(
        _policy("annual increase not exceeding 10% of current basic salary"),
        None,
        outcome,
    )

    assert provenance.code == "conditions_not_representable"
    assert provenance.is_platform_limitation is True
    # It must not *instruct* a reviewer to go and supply a mapping; saying
    # "not a missing mapping" is exactly the correction being asserted.
    assert "supply the missing mapping" not in provenance.message
    assert "not a missing mapping" in provenance.message
    assert "platform limitation" in provenance.message
    # The agent's actual expression is quoted, so the gap is auditable.
    assert "proposed_annual_increase" in provenance.message
    assert "proposed_annual_increase" in provenance.unsupported_expression


def test_missing_mapping_message_survives_for_the_case_it_describes():
    """The old message is still right when the agent never grounded anything."""

    outcome = derive_condition_outcome(
        _decision({"source_rule_indexes": [0], "dmn_mapping_status": "enrichment_required"}),
        0,
    )
    provenance = condition_provenance(_policy("only for P1 incidents"), None, outcome)

    assert provenance.code == "conditions_not_projected"
    assert provenance.is_platform_limitation is False
    assert "supply the missing mapping" in provenance.message


def test_provenance_without_an_outcome_is_unchanged():
    """Existing callers that pass no outcome keep their previous behaviour."""

    assert condition_provenance(_policy("only for P1 incidents"), None).code == (
        "conditions_not_projected"
    )
    assert condition_provenance(_policy(None), None).code == "no_scope_derived"
    assert condition_provenance(_policy("anything"), object()).code == "derived"


# --------------------------------------------------------------------------
# The safety gate must not weaken as a side effect of naming the cause
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    ["conditions_not_projected", "conditions_not_representable", "no_scope_derived", "derived"],
)
def test_ambiguity_ignores_the_projection_entirely(code):
    """Whether a rule compiles says nothing about whether the document is clear.

    These two were once folded together, so a plainly worded rule carried the
    same alarm as a genuinely vague one purely because no fact model covered
    its terms — which was true of nearly every rule, leaving the flag with no
    signal while still demanding attention on every row.
    """

    assert _ambiguity_for(_policy("only for the stated cases"), False, code) is (
        AmbiguityStatus.NONE
    )


def test_ambiguity_still_reports_ambiguity_the_extractor_found():
    """The one thing the flag is for: the source's own wording was unclear."""

    policy = _policy("only for the stated cases")
    policy.ambiguity = [AmbiguityCode.AMBIGUOUS_THRESHOLD]

    assert _ambiguity_for(policy, False, "derived") is AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
