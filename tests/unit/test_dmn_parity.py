"""Tests for DMN compilation and canonical-versus-DMN parity.

The harness only means something if the two sides are genuinely independent: an
implementation that evaluated the table by reusing the parsing path would agree
with itself by construction, including when both were wrong. These tests
therefore include cases where a deliberately broken projection *must* be caught,
not only cases where a correct one passes.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.formulation import (
    DmnDecision,
    DmnDecisionTable,
    DmnMappingStatus,
    DmnTableInput,
    DmnTableOutput,
    DmnTableRule,
)
from policy_platform.infrastructure.projection.dmn_parity import (
    UnsupportedFeel,
    check_parity,
    compile_decision,
    evaluate_table_row,
    match_unary_test,
)


def _decision(
    rows: list[list[str]],
    inputs: list[tuple[str, str]] | None = None,
    status: DmnMappingStatus = DmnMappingStatus.EXECUTABLE,
    source_indexes: list[int] | None = None,
) -> DmnDecision:
    columns = inputs or [("expense.amount", "number")]
    return DmnDecision(
        dmn_mapping_status=status,
        source_rule_indexes=source_indexes if source_indexes is not None else list(range(len(rows))),
        decision_table=DmnDecisionTable(
            hit_policy="UNIQUE",
            inputs=[DmnTableInput(label=e, expression=e, type=t) for e, t in columns],
            outputs=[DmnTableOutput(label="Outcome", name="outcome", type="string")],
            rules=[
                DmnTableRule(input_entries=entries, output_entries=['"approved"'])
                for entries in rows
            ],
        ),
    )


class TestUnaryTestSemantics:
    @pytest.mark.parametrize(
        ("expression", "value", "expected"),
        [
            ("5", 5, True),
            ("5", 6, False),
            ("<5", 4, True),
            ("<5", 5, False),
            ("<=5", 5, True),
            (">5", 6, True),
            (">=5", 5, True),
            ("!=5", 6, True),
            ("!=5", 5, False),
            ('"gold"', "gold", True),
            ('"gold"', "silver", False),
            ("true", True, True),
            ("-", 999, True),
            ("", 999, True),
        ],
    )
    def test_scalar_forms(self, expression: str, value: object, expected: bool) -> None:
        assert match_unary_test(expression, value) is expected

    @pytest.mark.parametrize(
        ("expression", "value", "expected"),
        [
            ("[1..10]", 1, True),
            ("[1..10]", 10, True),
            ("[1..10]", 11, False),
            ("(1..10]", 1, False),
            ("[1..10)", 10, False),
            ("(1..10)", 1, False),
            ("(1..10)", 5, True),
        ],
    )
    def test_range_boundaries(self, expression: str, value: object, expected: bool) -> None:
        """Inclusive/exclusive errors are where policy thresholds go wrong."""

        assert match_unary_test(expression, value) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("gold", True), ("silver", True), ("bronze", False)],
    )
    def test_alternatives(self, value: str, expected: bool) -> None:
        assert match_unary_test('"gold","silver"', value) is expected

    @pytest.mark.parametrize(
        "expression",
        ["not(5)", "date(\"2026-01-01\")", "duration(\"P1D\")", "amount * 2", "sum(x)"],
    )
    def test_unsupported_constructs_refuse_rather_than_return_false(
        self, expression: str
    ) -> None:
        """A construct treated as false becomes a rule that never fires and
        never explains why."""

        with pytest.raises(UnsupportedFeel):
            match_unary_test(expression, 5)

    def test_incomparable_types_refuse(self) -> None:
        with pytest.raises(UnsupportedFeel):
            match_unary_test("<5", "gold")


class TestTableEvaluation:
    def test_all_columns_must_match(self) -> None:
        decision = _decision(
            [[">=100", '"gold"']],
            inputs=[("expense.amount", "number"), ("customer.tier", "string")],
        )
        table = decision.decision_table

        assert evaluate_table_row(table, 0, {"expense.amount": 150, "customer.tier": "gold"})
        assert not evaluate_table_row(table, 0, {"expense.amount": 150, "customer.tier": "silver"})

    def test_a_missing_fact_is_indeterminate_not_false(self) -> None:
        """A policy whose inputs are unknown has not been shown not to apply."""

        table = _decision([[">=100"]]).decision_table
        assert evaluate_table_row(table, 0, {}) is None

    def test_any_value_columns_impose_no_constraint(self) -> None:
        decision = _decision(
            [[">=100", "-"]],
            inputs=[("expense.amount", "number"), ("customer.tier", "string")],
        )
        assert evaluate_table_row(decision.decision_table, 0, {"expense.amount": 150})

    def test_entry_count_mismatch_refuses(self) -> None:
        table = _decision([[">=100"]]).decision_table
        table.inputs.append(DmnTableInput(label="x", expression="x", type="string"))

        with pytest.raises(UnsupportedFeel):
            evaluate_table_row(table, 0, {"expense.amount": 150})


class TestCompilation:
    def test_a_supported_table_compiles(self) -> None:
        report = compile_decision(_decision([[">=100"], ["[1..99]"]]))

        assert report.ok
        assert report.status == "compiled"
        assert report.entries_checked == 2
        assert report.errors == []

    def test_an_unsupported_construct_is_not_projectable(self) -> None:
        report = compile_decision(_decision([['date("2026-01-01")']]))

        assert not report.ok
        assert report.status == "not_projectable"
        assert report.errors

    def test_a_non_executable_decision_requires_review(self) -> None:
        """`executable` is the agent's assertion that facts came from source.

        Compiling without it validates the syntax of facts nobody vouched for.
        """

        report = compile_decision(
            _decision([[">=100"]], status=DmnMappingStatus.ENRICHMENT_REQUIRED)
        )

        assert report.status == "requires_review"
        assert not report.ok

    def test_an_executable_decision_without_a_table_is_not_projectable(self) -> None:
        decision = _decision([[">=100"]])
        decision.decision_table = None

        assert compile_decision(decision).status == "not_projectable"

    def test_a_column_without_a_fact_expression_is_reported(self) -> None:
        decision = _decision([[">=100"]])
        decision.decision_table.inputs[0].expression = None
        decision.decision_table.inputs[0].label = None

        assert compile_decision(decision).errors


class TestParity:
    def test_a_faithful_projection_agrees_on_every_scenario(self) -> None:
        report = check_parity(_decision([[">=100"]]))

        assert report.ok
        assert report.scenarios_run > 0

    def test_ranges_agree_at_their_boundaries(self) -> None:
        """Boundaries are where inclusive/exclusive mistakes live, and a
        hand-written fact bag is overwhelmingly likely to miss them."""

        report = check_parity(_decision([["[100..500]"]]))

        assert report.ok
        assert report.scenarios_run > 0

    def test_multi_column_rows_agree(self) -> None:
        decision = _decision(
            [[">=100", '"gold","silver"']],
            inputs=[("expense.amount", "number"), ("customer.tier", "string")],
        )
        report = check_parity(decision)

        assert report.ok, [m.describe() for m in report.mismatches]

    def test_missing_facts_are_indeterminate_on_both_sides(self) -> None:
        report = check_parity(_decision([[">=100"]]))

        assert report.ok
        assert not report.mismatches

    def test_the_harness_detects_a_broken_projection(self) -> None:
        """The test that proves the harness is worth running.

        The two implementations share no code, so injecting a disagreement into
        one side must be caught. If this passed silently, parity would be a
        tautology.
        """

        from policy_platform.infrastructure.projection import dmn_parity

        original = dmn_parity.match_unary_test

        def inverted(expression: str, value: object) -> bool:
            result = original(expression, value)
            return not result if expression.strip() not in ("", "-") else result

        dmn_parity.match_unary_test = inverted
        try:
            report = check_parity(_decision([[">=100"]]))
        finally:
            dmn_parity.match_unary_test = original

        assert not report.ok
        assert report.mismatches
        assert "canonical=" in report.mismatches[0].describe()

    def test_rules_without_a_derivable_condition_are_skipped_not_failed(self) -> None:
        """A non-executable decision is a review item, not a parity failure."""

        report = check_parity(
            _decision([[">=100"]], status=DmnMappingStatus.ENRICHMENT_REQUIRED)
        )

        assert report.ok
        assert report.skipped

    def test_a_vacuous_row_is_skipped(self) -> None:
        """Every column 'any value' imposes no test, so there is nothing to
        compare and nothing that should be called executable."""

        report = check_parity(_decision([["-"]]))

        assert report.ok
        assert report.skipped

    def test_mismatched_index_counts_are_skipped_not_guessed(self) -> None:
        """Guessing which row belongs to which rule misattributes policy."""

        decision = _decision([[">=100"], ["<100"]], source_indexes=[0])
        report = check_parity(decision)

        assert report.skipped
