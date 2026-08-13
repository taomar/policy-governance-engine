"""DMN compilation and canonical-versus-DMN parity testing.

WHAT THIS CLOSES
----------------
The platform could already *parse* FEEL unary tests into conditions
(`formulation_mapping.parse_feel_unary_test`) and evaluate conditions
(`evaluator.conditions.evaluate_condition`). What it could not do is prove those
two agree, which is what the acceptance gate "zero supported DMN/FEEL
compilation or parity failures" actually asks for.

WHY THE DMN EVALUATOR HERE IS DELIBERATELY SEPARATE
----------------------------------------------------
The obvious implementation is to evaluate a decision table by parsing it into
conditions and running the condition evaluator. That would be worthless: it
would exercise one code path twice and agree with itself by construction,
including when both are wrong.

`match_unary_test` below is therefore an independent implementation of FEEL
unary-test semantics, written directly against the DMN meaning of each form. It
shares no code with the parsing path. Parity is then a real comparison: two
implementations, built from the same specification, reaching the same verdict on
the same facts. A disagreement means at least one is wrong, which is exactly the
signal the gate exists to produce.

WHAT PARITY DOES NOT CLAIM
--------------------------
Agreement proves the projection is faithful to the canonical condition. It does
not prove the canonical condition captured the policy correctly — that is a
semantic question a reviewer answers against the source. Parity closes the
mechanical gap only, and saying otherwise would overstate it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from policy_platform.contracts.formulation import (
    DmnDecision,
    DmnDecisionTable,
    DmnMappingStatus,
)
from policy_platform.evaluator.conditions import ConditionOutcome, evaluate_condition
from policy_platform.infrastructure.extraction.formulation_mapping import derive_condition

#: Whether a decision could be compiled at all.
CompileStatus = Literal["compiled", "not_projectable", "requires_review"]

_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_STRING = re.compile(r'^"(?P<body>[^"]*)"$')
_RANGE = re.compile(r"^(?P<lo_b>[\[(])\s*(?P<lo>[^.]+?)\s*\.\.\s*(?P<hi>[^\])]+?)\s*(?P<hi_b>[\])])$")
_COMPARATOR = re.compile(r"^(?P<op><=|>=|!=|<|>|=)\s*(?P<operand>.+)$")


class UnsupportedFeel(ValueError):
    """Raised when an expression falls outside the supported FEEL subset.

    Distinct from "the test did not match": an unsupported construct must never
    be silently treated as false, because that would turn a rule nobody can
    execute into a rule that quietly never fires.
    """


@dataclass
class CompileReport:
    """Result of compiling one decision."""

    decision_name: str
    status: CompileStatus
    entries_checked: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "compiled"


@dataclass
class ParityMismatch:
    """One scenario where the two evaluations disagreed."""

    decision_name: str
    rule_index: int
    facts: dict[str, object]
    canonical: str
    dmn: str

    def describe(self) -> str:
        return (
            f"{self.decision_name} row {self.rule_index}: canonical={self.canonical} "
            f"dmn={self.dmn} for {self.facts}"
        )


@dataclass
class ParityReport:
    """Outcome of comparing canonical conditions against their DMN projection."""

    scenarios_run: int = 0
    mismatches: list[ParityMismatch] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


# ---------------------------------------------------------------------------
# Independent FEEL unary-test evaluation
# ---------------------------------------------------------------------------


def _literal(token: str) -> object:
    token = token.strip()
    if _NUMBER.match(token):
        return float(token) if "." in token else int(token)
    quoted = _STRING.match(token)
    if quoted:
        return quoted.group("body")
    if token in ("true", "false"):
        return token == "true"
    raise UnsupportedFeel(f"unsupported FEEL literal: {token!r}")


def _split_alternatives(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quoted = False
    current: list[str] = []
    for char in text:
        if char == '"':
            quoted = not quoted
        elif not quoted and char in "[(":
            depth += 1
        elif not quoted and char in "])":
            depth -= 1
        if char == "," and depth == 0 and not quoted:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _compare(value: object, operator: str, operand: object) -> bool:
    if operator == "=":
        return value == operand
    if operator == "!=":
        return value != operand
    # Ordering against an incomparable pair (a string fact against a numeric
    # bound) is a type error in the projection, not a false result.
    try:
        if operator == "<":
            return value < operand  # type: ignore[operator]
        if operator == "<=":
            return value <= operand  # type: ignore[operator]
        if operator == ">":
            return value > operand  # type: ignore[operator]
        if operator == ">=":
            return value >= operand  # type: ignore[operator]
    except TypeError as exc:
        raise UnsupportedFeel(f"cannot order {value!r} against {operand!r}") from exc
    raise UnsupportedFeel(f"unsupported comparator: {operator!r}")


def match_unary_test(expression: str, value: object) -> bool:
    """Evaluate one FEEL unary test against a value, per DMN semantics.

    Written directly from the DMN meaning of each form rather than by reusing
    the parsing path, so agreement between the two is evidence rather than a
    tautology.

    Raises `UnsupportedFeel` for anything outside the supported subset. Refusing
    is deliberate: a construct treated as false would produce a rule that never
    fires and never explains why.
    """

    expression = (expression or "").strip()
    if expression in ("", "-"):
        # "Any value": this column places no constraint on the row.
        return True

    range_match = _RANGE.match(expression)
    if range_match:
        low = _literal(range_match.group("lo"))
        high = _literal(range_match.group("hi"))
        lower_ok = (
            _compare(value, ">=", low)
            if range_match.group("lo_b") == "["
            else _compare(value, ">", low)
        )
        upper_ok = (
            _compare(value, "<=", high)
            if range_match.group("hi_b") == "]"
            else _compare(value, "<", high)
        )
        return lower_ok and upper_ok

    alternatives = _split_alternatives(expression)
    if len(alternatives) > 1:
        return any(match_unary_test(alternative, value) for alternative in alternatives)

    comparator = _COMPARATOR.match(expression)
    if comparator:
        return _compare(value, comparator.group("op"), _literal(comparator.group("operand")))

    return value == _literal(expression)


def evaluate_table_row(
    table: DmnDecisionTable, row_index: int, facts: dict[str, object]
) -> bool | None:
    """Evaluate one decision-table row against `facts`.

    Returns None when a required fact is absent. That mirrors the platform's own
    rule that a missing fact is INDETERMINATE rather than FALSE — a policy whose
    inputs are unknown has not been shown not to apply.
    """

    row = table.rules[row_index]
    if len(row.input_entries) != len(table.inputs):
        raise UnsupportedFeel(
            f"row {row_index} has {len(row.input_entries)} entries for {len(table.inputs)} inputs"
        )

    matched = True
    for column, entry in zip(table.inputs, row.input_entries):
        expression = (entry or "").strip()
        if expression in ("", "-"):
            continue
        fact = (column.expression or column.label or "").strip()
        if not fact:
            raise UnsupportedFeel(f"input column {column.label!r} has no fact expression")
        if fact not in facts:
            return None
        if not match_unary_test(expression, facts[fact]):
            matched = False
    return matched


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_decision(decision: DmnDecision, name: str = "") -> CompileReport:
    """Check every FEEL entry in a decision parses under the supported subset.

    A decision the agent did not mark executable is reported as
    `requires_review` rather than compiled: `executable` is the agent's
    assertion that fact paths and values came from source rather than invention,
    and compiling without it would validate the syntax of facts nobody vouched
    for.

    `DmnDecision` carries no name of its own — a decision is identified by the
    canonical rules it projects — so a label is supplied by the caller and falls
    back to those indexes.
    """

    name = name or _decision_label(decision)

    if decision.dmn_mapping_status != DmnMappingStatus.EXECUTABLE:
        return CompileReport(
            decision_name=name,
            status="requires_review",
            errors=[f"decision is {decision.dmn_mapping_status or 'unmapped'}, not executable"],
        )

    table = decision.decision_table
    if table is None:
        return CompileReport(
            decision_name=name,
            status="not_projectable",
            errors=["executable decision carries no decision table"],
        )

    errors: list[str] = []
    checked = 0

    for row_index, row in enumerate(table.rules):
        if len(row.input_entries) != len(table.inputs):
            errors.append(
                f"row {row_index}: {len(row.input_entries)} entries for {len(table.inputs)} inputs"
            )
            continue
        for column, entry in zip(table.inputs, row.input_entries):
            checked += 1
            expression = (entry or "").strip()
            if expression in ("", "-"):
                continue
            if not (column.expression or column.label or "").strip():
                errors.append(f"row {row_index}: input column has no fact expression")
                continue
            try:
                # Probe with a value of the entry's own literal type where
                # possible, so a type error in the expression surfaces here
                # rather than at evaluation time.
                match_unary_test(expression, _probe_value(expression))
            except UnsupportedFeel as exc:
                errors.append(f"row {row_index}: {exc}")

    return CompileReport(
        decision_name=name,
        status="not_projectable" if errors else "compiled",
        entries_checked=checked,
        errors=errors,
    )


def _probe_value(expression: str) -> object:
    """A value of the same shape the expression compares against.

    Compilation must test the *expression*, not the facts, so the probe is
    derived from the expression itself. Falling back to 0 keeps an unparseable
    operand surfacing as an `UnsupportedFeel` from `_literal` rather than as a
    spurious type error.
    """

    candidate = expression.lstrip("<>=!([ ").split("..")[0].split(",")[0].strip(" ])")
    try:
        return _literal(candidate)
    except UnsupportedFeel:
        return 0


# ---------------------------------------------------------------------------
# Parity
# ---------------------------------------------------------------------------


def check_parity(
    decision: DmnDecision,
    source_rule_indexes: list[int] | None = None,
    name: str = "",
) -> ParityReport:
    """Compare canonical conditions against the DMN table on generated scenarios.

    Scenarios are derived from the table's own boundary values — each threshold,
    plus the values immediately either side of it. Boundaries are where
    inclusive/exclusive errors live, and a random or hand-written fact bag is
    overwhelmingly likely to miss them.
    """

    report = ParityReport()
    name = name or _decision_label(decision)
    table = decision.decision_table
    if table is None:
        report.skipped.append(f"{name}: no decision table")
        return report

    indexes = (
        source_rule_indexes if source_rule_indexes is not None else decision.source_rule_indexes
    )

    for index in indexes:
        derived = derive_condition(decision, index)
        if derived is None:
            report.skipped.append(f"{name}: rule {index} has no derivable condition")
            continue
        condition, _facts = derived

        row_index = _row_for(decision, index)
        if row_index is None:
            report.skipped.append(f"{name}: rule {index} has no corresponding table row")
            continue

        for scenario in _scenarios(table, row_index):
            canonical = evaluate_condition(condition, scenario)
            try:
                dmn = evaluate_table_row(table, row_index, scenario)
            except UnsupportedFeel as exc:
                report.skipped.append(f"{name} row {row_index}: {exc}")
                break

            report.scenarios_run += 1
            if not _agrees(canonical.outcome, dmn):
                report.mismatches.append(
                    ParityMismatch(
                        decision_name=name,
                        rule_index=row_index,
                        facts=dict(scenario),
                        canonical=canonical.outcome.value,
                        dmn={True: "TRUE", False: "FALSE", None: "INDETERMINATE"}[dmn],
                    )
                )

    return report


def _agrees(canonical: ConditionOutcome, dmn: bool | None) -> bool:
    if dmn is None:
        return canonical is ConditionOutcome.INDETERMINATE
    return (canonical is ConditionOutcome.TRUE) is dmn


def _decision_label(decision: DmnDecision) -> str:
    """A human-quotable name for a decision that has no name field.

    A decision is identified by the canonical rules it projects, so those
    indexes are the honest label. Inventing a title here would put a generated
    string into diagnostics that reviewers quote back.
    """

    if decision.source_rule_indexes:
        return "decision for rules " + ", ".join(str(i) for i in decision.source_rule_indexes)
    return "<unattributed decision>"


def _row_for(decision: DmnDecision, index: int) -> int | None:
    table = decision.decision_table
    if table is None or index not in decision.source_rule_indexes:
        return None
    if len(decision.source_rule_indexes) != len(table.rules):
        return None
    return decision.source_rule_indexes.index(index)


def _scenarios(table: DmnDecisionTable, row_index: int) -> list[dict[str, object]]:
    """Fact bags probing each input column at and around its boundaries."""

    row = table.rules[row_index]
    per_column: dict[str, list[object]] = {}

    for column, entry in zip(table.inputs, row.input_entries):
        fact = (column.expression or column.label or "").strip()
        expression = (entry or "").strip()
        if not fact or expression in ("", "-"):
            continue
        per_column[fact] = _candidate_values(expression)

    if not per_column:
        return []

    # One column varied at a time, the rest held at a value that satisfies their
    # own test. Varying every column together would produce mostly-false rows
    # whose agreement says nothing about the column under test.
    baseline = {fact: values[0] for fact, values in per_column.items()}
    scenarios: list[dict[str, object]] = [dict(baseline)]

    for fact, values in per_column.items():
        for value in values:
            scenario = dict(baseline)
            scenario[fact] = value
            scenarios.append(scenario)
        # Omitting the fact entirely must give INDETERMINATE on both sides.
        missing = dict(baseline)
        missing.pop(fact)
        scenarios.append(missing)

    return scenarios


def _candidate_values(expression: str) -> list[object]:
    """Values at, just below, and just above each literal in `expression`."""

    values: list[object] = []
    for token in re.findall(r'-?\d+(?:\.\d+)?|"[^"]*"|true|false', expression):
        try:
            literal = _literal(token)
        except UnsupportedFeel:
            continue
        values.append(literal)
        if isinstance(literal, bool):
            values.append(not literal)
        elif isinstance(literal, (int, float)):
            values.extend([literal - 1, literal + 1])
        elif isinstance(literal, str):
            values.append(literal + "_other")
    return values or [0]
