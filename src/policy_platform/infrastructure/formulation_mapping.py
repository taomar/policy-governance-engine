"""Deterministic derivation: formulator output -> this platform's executable rules.

Spec Section 82 is explicit that identifier generation, precedence assignment
and compilation are *deterministic application responsibilities*, not model
responsibilities. This module is that boundary. The formulator agent decides
what the source means; everything here is ordinary Python that a reviewer can
read, step through, and unit-test — no model call, no randomness, no I/O.

Two translations happen:

**Canonical rule type -> platform `RuleType`/`EffectType`.** The two
vocabularies are not the same size. The specification's Section 9 list is
deontic/decision-shaped (entitlement, eligibility, recommendation…), while
`contracts.policy.RuleType` describes *evaluator* semantics (routing,
escalation, retention…). The mapping below is therefore lossy in one
direction, which is exactly why the untouched formulation is retained on every
rule: the platform's classification is a projection, and the canonical record
stays the source of truth (spec Section 106).

**FEEL unary tests -> the platform condition AST.** Only when the agent
reported `executable` — meaning a trusted fact model supplied every fact path,
so nothing was invented. The parser is deliberately strict: any expression it
does not fully understand yields no condition at all rather than a plausible
guess. A wrong condition is far more dangerous than an absent one, because an
absent one is visibly non-executable and blocks on human review, whereas a
wrong one silently returns confident decisions.

That strictness preserves the platform's existing invariant: an AI-drafted rule
can never become machine-executable without either a trusted fact model or a
human formalizing the condition.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from policy_platform.contracts.conditions import (
    AllCondition,
    AnyCondition,
    ConditionNode,
    ConditionOperator,
    FactComparisonCondition,
    FactOperand,
    FactRelativeComparisonCondition,
)
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalRuleType,
    DmnDecision,
    DmnMappingStatus,
    DmnTableInput,
    ExtractionStatus,
    PolicyFormulation,
    RuleFormulation,
)
from policy_platform.contracts.passage import PolicyPassage
from policy_platform.infrastructure.passage_extractor import _normalize
from policy_platform.contracts.policy import (
    AmbiguityStatus,
    CanonicalRule,
    ConditionProvenance,
    DecisionReadiness,
    Effect,
    EffectType,
    PartyRoleName,
    PolicyAuthority,
    PolicyFact,
    PolicyScope,
    RequiredAttributeRef,
    RequiredFact,
    ReviewStatus,
    RuleException,
    RuleLineage,
    RulePartyRef,
    RuleType,
    attributes_for,
    evaluation_mode_from,
)
from policy_platform.infrastructure.evaluability import assess_policy
from policy_platform.infrastructure.policy_facts import (
    _slugify,
    facts_for,
    parse_proportion,
)

#: Canonical rule type -> (platform rule type, effect). Every entry is a
#: judgement call about the closest *evaluator* semantic, documented here
#: rather than buried in branches:
#:
#: - obligation/prohibition/permission map exactly; the vocabularies agree.
#: - `entitlement` becomes PERMISSION/allow, not OBLIGATION: spec Section 66
#:   forbids converting an entitlement into an obligation ("the employee gets
#:   X" is not "someone must do X").
#: - `ineligibility` reuses ELIGIBILITY with a DENY effect rather than
#:   inventing a type — the eligibility question is the same, the answer is
#:   negative.
#: - `conditional_outcome` becomes ROUTING: the platform has no exact
#:   equivalent, and ROUTING ("the condition selects which outcome applies")
#:   is the closest evaluator semantic. This is the loosest entry in the table.
#: - `recommendation` becomes HUMAN_JUDGMENT_REQUIREMENT: spec Section 67
#:   forbids promoting advisory language to an obligation, and the platform has
#:   no advisory type, so the honest projection is "a human decides".
#: - `ambiguous` likewise defers to human judgement.
#:
#: `non_normative` is absent on purpose — see `_SKIPPED_RULE_TYPES`.
#:
#: `classification`/`definition`/`calculation` map to `EffectType.INFORMATIONAL`,
#: not `ALLOW` or `REQUIRE_ACTION`: none of them authorizes, forbids, or
#: obliges anyone to act, so any other effect was a dishonest projection — most
#: visibly when the source is phrased negatively ("shall NOT be included...")
#: and the forced `ALLOW` asserts the literal inverse of the rule's own text.
#:
#: `calculation` was the last of the three to be corrected, and its tell was the
#: same. "The housing allowance is calculated as twice the monthly basic salary
#: up to a maximum of..." became an Obligation whose `action` was the sentence
#: fragment "is calculated as twice the monthly basic salary up to a maximum
#: of" — an instruction no decision point can carry out, because the rule states
#: how a *value* is derived rather than something to be done. Under XACML §7.18
#: an Obligation is work a PEP must discharge; a derived amount is not work.
#:
#: See `ai_quality._definition_effect_findings` for the defect this closes and
#: `_apply_combining_algorithm` for why an informational effect never competes
#: on the allow/deny axis.
_RULE_TYPE_MAP: dict[CanonicalRuleType, tuple[RuleType, EffectType]] = {
    CanonicalRuleType.OBLIGATION: (RuleType.OBLIGATION, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.PROHIBITION: (RuleType.PROHIBITION, EffectType.DENY),
    CanonicalRuleType.PERMISSION: (RuleType.PERMISSION, EffectType.ALLOW),
    CanonicalRuleType.ENTITLEMENT: (RuleType.PERMISSION, EffectType.ALLOW),
    CanonicalRuleType.ELIGIBILITY: (RuleType.ELIGIBILITY, EffectType.ALLOW),
    CanonicalRuleType.INELIGIBILITY: (RuleType.ELIGIBILITY, EffectType.DENY),
    CanonicalRuleType.CONDITIONAL_OUTCOME: (RuleType.ROUTING, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.CALCULATION: (RuleType.CALCULATION, EffectType.INFORMATIONAL),
    CanonicalRuleType.CLASSIFICATION: (RuleType.DEFINITION, EffectType.INFORMATIONAL),
    CanonicalRuleType.RECOMMENDATION: (RuleType.HUMAN_JUDGMENT_REQUIREMENT, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.DEFINITION: (RuleType.DEFINITION, EffectType.INFORMATIONAL),
    CanonicalRuleType.AMBIGUOUS: (RuleType.HUMAN_JUDGMENT_REQUIREMENT, EffectType.REQUIRE_ACTION),
}

#: Subjects that name the document itself rather than anyone it governs.
#:
#: A policy statement's subject is an actor or thing in the world the document
#: regulates ("An employee", "The Foundation", "Security incidents"). When the
#: subject is the document, the statement is *about the document*: what it is,
#: who it was written for, how to read it, where its conventions apply. "This
#: template is provided as a tool for community foundations to develop
#: policies" governs nobody and decides nothing.
#:
#: Left as a closed, domain-neutral list of determiner + document noun. It
#: matches on grammatical subject only, never on topic or wording elsewhere in
#: the sentence, so it cannot quietly grow into a content classifier.
_DOCUMENT_NOUNS = (
    "policy",
    "policies",
    "template",
    "document",
    "manual",
    "handbook",
    "guide",
    "guideline",
    "guidelines",
    "agreement",
    "procedure",
    "procedures",
    "section",
    "chapter",
    "appendix",
)

_DOCUMENT_SUBJECT_RE = re.compile(
    r"^\s*(this|these|those|the\s+present|the\s+following)\s+("
    + "|".join(_DOCUMENT_NOUNS)
    # The document noun must end the subject, so the match is the document
    # itself and not something the document merely qualifies. "This policy" is
    # the document; "This policy owner" is a person, and enforcing rules about
    # people is the whole job.
    + r")\s*$",
    re.IGNORECASE,
)

#: Tag applied to statements about the document. Presentational and reviewable:
#: it never removes the rule, because deciding that a sentence carries no policy
#: is a judgement the reviewer makes, not one extraction should make silently.
DOCUMENT_GUIDANCE_TAG = "document_guidance"


def is_document_guidance(canonical_rule: CanonicalPolicyRule | None) -> bool:
    """True when a statement's subject is the document rather than an actor.

    Grammatical, not semantic. It asks "what is this sentence about?" and
    answers from the subject the formulator already isolated — it does not
    read the predicate, weigh topic similarity, or judge whether the content
    sounds administrative. That keeps the signal explainable to a reviewer in
    one sentence and keeps its failure mode small: a false positive costs one
    glance, because the rule is flagged rather than dropped.
    """

    if canonical_rule is None:
        return False
    return bool(_DOCUMENT_SUBJECT_RE.match(canonical_rule.subject or ""))


#: `non_normative` means the agent judged the text to carry no rule at all
#: (preamble, headings, narrative). Manufacturing a rule from it would pollute
#: the review queue with noise that a reviewer must reject one by one, so these
#: are dropped with an explicit reason instead.
_SKIPPED_RULE_TYPES = frozenset({CanonicalRuleType.NON_NORMATIVE})

#: A condition that is trivially true. Used when no safe machine condition can
#: be derived, paired with `machine_executable=False` so the rule cannot be
#: evaluated as though the placeholder were a real test.
_VACUOUS_CONDITION = AllCondition(all=[])

_COMPARATORS: list[tuple[str, ConditionOperator]] = [
    (">=", ConditionOperator.GREATER_THAN_OR_EQUAL),
    ("<=", ConditionOperator.LESS_THAN_OR_EQUAL),
    ("!=", ConditionOperator.NOT_EQUALS),
    (">", ConditionOperator.GREATER_THAN),
    ("<", ConditionOperator.LESS_THAN),
    ("=", ConditionOperator.EQUALS),
]

_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_STRING_RE = re.compile(r'^"(?P<body>[^"]*)"$')
_RANGE_RE = re.compile(r"^(?P<lo_b>[\[\(])\s*(?P<lo>[^.]+?)\s*\.\.\s*(?P<hi>[^.]+?)\s*(?P<hi_b>[\]\)])$")


def _parse_feel_literal(token: str) -> object | None:
    """Parse a FEEL literal. Returns None when the token is not a plain literal.

    Only the literal forms DMN decision tables actually use are accepted:
    numbers, double-quoted strings, and booleans. Dates, durations, ranges,
    function calls and contexts deliberately fall through so the caller
    refuses the whole expression.
    """

    token = token.strip()
    if not token:
        return None
    if _NUMBER_RE.match(token):
        return float(token) if "." in token else int(token)
    quoted = _STRING_RE.match(token)
    if quoted:
        return quoted.group("body")
    if token in ("true", "false"):
        return token == "true"
    return None


def _split_top_level_commas(text: str) -> list[str]:
    """Split on commas that are not inside quotes or brackets."""

    parts: list[str] = []
    depth = 0
    in_quotes = False
    current: list[str] = []
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
        elif not in_quotes and char in "[(":
            depth += 1
        elif not in_quotes and char in "])":
            depth -= 1
        if char == "," and depth == 0 and not in_quotes:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


#: A fact-relative right-hand side: a dotted fact path optionally scaled by a
#: numeric factor, in either order (`salary * 0.10` or `0.10 * salary`).
#:
#: Deliberately narrow. It matches a single path and at most one multiplier —
#: no addition, no parentheses, no second fact, no function call. Everything
#: outside that still returns None, because the value of this parser is that
#: what it does not fully understand it refuses, rather than half-reading.
_FACT_PATH = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
_FACT_RELATIVE_RE = re.compile(
    rf"""^\s*(?:
        (?P<path1>{_FACT_PATH})\s*(?:\*\s*(?P<factor1>-?\d+(?:\.\d+)?)\s*)?
      | (?P<factor2>-?\d+(?:\.\d+)?)\s*\*\s*(?P<path2>{_FACT_PATH})
    )\s*$""",
    re.VERBOSE,
)


def parse_fact_relative_operand(expression: str) -> FactOperand | None:
    """Read `basic_salary * 0.05` (or `0.05 * basic_salary`) as an operand.

    Returns None for anything that is not exactly one dotted fact path with at
    most one numeric multiplier. A bare number is not an operand here — that is
    a literal, and belongs to `_parse_feel_literal`.
    """

    match = _FACT_RELATIVE_RE.match(expression or "")
    if not match:
        return None
    path = match.group("path1") or match.group("path2")
    raw_factor = match.group("factor1") or match.group("factor2")
    return FactOperand(fact=path, factor=float(raw_factor) if raw_factor else 1.0)


def parse_feel_unary_test(fact: str, expression: str) -> list[ConditionNode] | None:
    """Translate one FEEL unary test into condition leaves for `fact`.

    Returns:
        - ``[]`` for the "any value" tests (``-`` or empty), meaning this
          input places no constraint on the rule;
        - a list of leaves for a test that was fully understood;
        - ``None`` when the expression uses anything outside the supported
          subset, which the caller must treat as "not executable".

    Supported: ``-``, bare literals, ``= < <= > >= !=`` comparisons,
    ``[a..b]``/``(a..b]`` style ranges with inclusive/exclusive bounds,
    comma-separated literal lists (rendered as ``in``), and a comparison
    against another fact optionally scaled by a constant
    (``<= employee.compensation.basic_salary * 0.05``).

    That last form is why this parser exists in its current shape: measured
    against live AD-103 output it was the *only* comparison the formulator
    produced for compensation limits, and rejecting it meant a complete fact
    model still yielded no executable rule.

    Everything else — ``not(...)``, function calls, general arithmetic, date and
    duration literals, nested contexts — returns None *by design*. Guessing at
    a partially-understood expression is how an evaluator ends up confidently
    returning the wrong decision.
    """

    expression = (expression or "").strip()
    if expression in ("", "-"):
        return []

    range_match = _RANGE_RE.match(expression)
    if range_match:
        low = _parse_feel_literal(range_match.group("lo"))
        high = _parse_feel_literal(range_match.group("hi"))
        if low is None or high is None:
            return None
        low_op = (
            ConditionOperator.GREATER_THAN_OR_EQUAL
            if range_match.group("lo_b") == "["
            else ConditionOperator.GREATER_THAN
        )
        high_op = (
            ConditionOperator.LESS_THAN_OR_EQUAL
            if range_match.group("hi_b") == "]"
            else ConditionOperator.LESS_THAN
        )
        return [
            FactComparisonCondition(fact=fact, operator=low_op, value=low),
            FactComparisonCondition(fact=fact, operator=high_op, value=high),
        ]

    alternatives = _split_top_level_commas(expression)
    if len(alternatives) > 1:
        values = [_parse_feel_literal(a) for a in alternatives]
        if any(v is None for v in values):
            return None
        return [FactComparisonCondition(fact=fact, operator=ConditionOperator.IN, value=values)]

    for symbol, operator in _COMPARATORS:
        if expression.startswith(symbol):
            remainder = expression[len(symbol):]
            value = _parse_feel_literal(remainder)
            if value is not None:
                return [FactComparisonCondition(fact=fact, operator=operator, value=value)]
            # Not a literal — it may still be a reference to another fact.
            # Tried second so a plain numeric bound keeps its existing,
            # cheaper representation and nothing already working changes shape.
            operand = parse_fact_relative_operand(remainder)
            if operand is None:
                return None
            return [
                FactRelativeComparisonCondition(
                    fact=fact, operator=operator, reference=operand
                )
            ]

    literal = _parse_feel_literal(expression)
    if literal is None:
        return None
    return [FactComparisonCondition(fact=fact, operator=ConditionOperator.EQUALS, value=literal)]


def _row_for_index(decision: DmnDecision, index: int) -> int | None:
    """Which decision-table row corresponds to canonical policy `index`.

    Spec Section 86 pairs a decision's `source_rule_indexes` with its table
    positionally, so row *n* belongs to the *n*-th listed source index. The
    correspondence is only trusted when the counts match exactly; a mismatch
    means the agent grouped rules in some other way and guessing would
    misattribute a row to the wrong rule.
    """

    table = decision.decision_table
    if table is None or index not in decision.source_rule_indexes:
        return None
    if len(decision.source_rule_indexes) != len(table.rules):
        return None
    return decision.source_rule_indexes.index(index)


def _fact_name(column: DmnTableInput) -> str:
    """The platform fact name for a table input column.

    Uses the FEEL `expression`, which under a trusted fact model is already a
    dotted fact path (`expense.amount`) — the same shape the platform's own
    facts use (`subject.persona`). Falls back to the human label only when no
    expression was supplied.
    """

    return (column.expression or column.label or "").strip()


class ConditionDerivationReason(str, Enum):
    """Why `derive_condition` did or did not produce an executable tree.

    Every value below previously collapsed into a bare `None`. That conflation
    is what hid a platform limitation behind a message telling reviewers to fix
    their fact model: measured against live AD-103 output, five of six
    decisions the agent declared `executable` were expressed as a FEEL
    *literal expression*, which this module never reads, and the sixth was a
    decision table whose unary tests compared a fact against a percentage of
    another fact, which `parse_feel_unary_test` cannot represent. All six
    returned the same `None` as an ordinary non-executable rule.
    """

    DERIVED = "derived"
    #: The agent did not declare the decision executable. Expected and common.
    NOT_DECLARED_EXECUTABLE = "not_declared_executable"
    #: Executable, but no decision-table row maps to this canonical policy.
    NO_TABLE_ROW = "no_table_row"
    #: Executable via `literal_expression`. A legal shape (prompt Section 87)
    #: that this module does not implement — see `_LITERAL_EXPRESSION_NOTE`.
    LITERAL_EXPRESSION_UNSUPPORTED = "literal_expression_unsupported"
    #: Executable, but neither a decision table nor a literal expression.
    NO_EXECUTABLE_BODY = "no_executable_body"
    #: Row width does not match the table's declared inputs.
    TABLE_SHAPE_MISMATCH = "table_shape_mismatch"
    #: An input column carried neither an expression nor a label.
    NO_FACT_FOR_COLUMN = "no_fact_for_column"
    #: A unary test this parser does not understand (e.g. fact-relative
    #: arithmetic such as `<= employee.compensation.basic_salary * 0.05`).
    UNSUPPORTED_UNARY_TEST = "unsupported_unary_test"
    #: Every column was "any value", so the row imposes no test at all.
    VACUOUS = "vacuous"
    #: A boolean-outcome table in which no row yields true, so the rule could
    #: never be satisfied. Refused rather than asserted.
    NO_SATISFYING_ROW = "no_satisfying_row"


#: Reasons that mean "the agent produced grounded, executable logic that this
#: platform could not represent" — as opposed to "there was nothing to compile".
#: Kept as an explicit set because the distinction drives the reviewer's remedy:
#: these need a platform change, not a fact-model change.
PLATFORM_LIMITED_REASONS = frozenset(
    {
        ConditionDerivationReason.LITERAL_EXPRESSION_UNSUPPORTED,
        ConditionDerivationReason.UNSUPPORTED_UNARY_TEST,
    }
)


@dataclass(frozen=True)
class ConditionDerivation:
    """The outcome of one attempt to compile a decision into a condition tree."""

    reason: ConditionDerivationReason
    condition: ConditionNode | None = None
    facts: tuple[RequiredFact, ...] = ()
    #: The exact agent text that could not be compiled, when there was one.
    #: Recorded verbatim so a reviewer sees what the agent actually produced
    #: rather than a paraphrase of it.
    unsupported_expression: str = ""

    @property
    def derived(self) -> bool:
        return self.condition is not None

    @property
    def platform_limited(self) -> bool:
        return self.reason in PLATFORM_LIMITED_REASONS


#: One conjunct of a FEEL boolean expression: `fact.path <op> <right-hand side>`.
_COMPARISON_RE = re.compile(rf"^\s*(?P<path>{_FACT_PATH})\s*(?P<op><=|>=|!=|<|>|=)\s*(?P<rhs>.+?)\s*$")

#: A bare fact path used as a boolean, e.g. `approval.board_of_trustees_approved`.
_BARE_FACT_RE = re.compile(rf"^\s*(?P<path>{_FACT_PATH})\s*$")

#: FEEL constructs that put an expression outside the supported subset.
#:
#: Checked before parsing rather than after, so a partially-recognised
#: expression can never contribute half its meaning to a condition. `or` is
#: excluded not because disjunction is unrepresentable — `AnyCondition` exists —
#: but because mixing it with `and` needs precedence handling this parser does
#: not do, and getting that wrong inverts rules silently.
_UNSUPPORTED_FEEL = (
    "(", ")", "[", "]", "{", "}", " or ", "not ", " if ", "then ", "else ", "..", "@",
)


def parse_feel_boolean_expression(feel: str) -> list[ConditionNode] | None:
    """Read a conjunctive FEEL boolean expression into condition leaves.

    Supports a deliberately small grammar: comparisons joined by `and`, where
    each side is a dotted fact path, a literal, or a fact path scaled by a
    constant; plus a bare fact path used as a boolean.

        employee.compensation.proposed_increase <= employee.compensation.basic_salary * 0.05
            and approval.board_of_trustees_approved

    That is the shape the formulator actually produces for compensation limits:
    measured across ten live AD-103 runs, six of the seven decisions it
    declared executable were literal expressions of exactly this form, and all
    six were being discarded.

    Returns None for anything outside the grammar. The parser refuses rather
    than approximates, for the same reason `parse_feel_unary_test` does: a
    half-understood condition produces confident wrong decisions, which is
    worse than no condition at all.
    """

    text = (feel or "").strip()
    if not text:
        return None
    padded = f" {text} "
    if any(token in padded for token in _UNSUPPORTED_FEEL):
        return None

    leaves: list[ConditionNode] = []
    for conjunct in re.split(r"\s+and\s+", text):
        conjunct = conjunct.strip()
        if not conjunct:
            return None

        comparison = _COMPARISON_RE.match(conjunct)
        if comparison:
            symbol = comparison.group("op")
            # `=` is FEEL equality; the unary-test parser spells it `=` too.
            parsed = parse_feel_unary_test(
                comparison.group("path"), f"{symbol}{comparison.group('rhs')}"
            )
            if not parsed:
                return None
            leaves.extend(parsed)
            continue

        bare = _BARE_FACT_RE.match(conjunct)
        if bare:
            leaves.append(
                FactComparisonCondition(
                    fact=bare.group("path"), operator=ConditionOperator.EQUALS, value=True
                )
            )
            continue

        return None

    return leaves or None


def _inferred_data_type(leaf: ConditionNode) -> str:
    """The declared type of the fact a leaf tests.

    Read from what the agent wrote rather than assumed: a literal expression
    carries no type column, but comparing against `0.05` or `true` states the
    type as plainly as a column would.
    """

    if isinstance(leaf, FactRelativeComparisonCondition):
        return "number"
    value = getattr(leaf, "value", None)
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _is_boolean_outcome_table(table: DmnDecisionTable) -> bool:
    """True when every row decides a single true/false outcome.

    Inferred from the entries rather than the declared output type, because
    the type is optional in the contract and the entries are what the reading
    below actually depends on.
    """

    if len(table.outputs) != 1 or not table.rules:
        return False
    for row in table.rules:
        if len(row.output_entries) != 1:
            return False
        if row.output_entries[0].strip().strip('"').lower() not in ("true", "false"):
            return False
    return True


def _row_is_satisfying(row: DmnTableRule) -> bool:
    return row.output_entries[0].strip().strip('"').lower() == "true"


def derive_condition_outcome(decision: DmnDecision, index: int) -> ConditionDerivation:
    """Compile canonical policy `index` of `decision`, reporting *why* on failure.

    `derive_condition` is the tuple-or-None wrapper over this function; this is
    the single implementation, so the two can never disagree about whether a
    decision compiles.

    The `executable` gate matters: it is the agent's assertion that every fact
    path, type and value came from source or trusted configuration rather than
    from invention (spec Sections 42-44). Without it, any condition built here
    would rest on facts nobody vouched for.

    Two table readings are supported, and which one applies is decided by the
    table's own shape:

    *Positional* — one row per listed source rule (spec Section 86). Row *n*
    belongs to the *n*-th source index, and the rule's condition is the AND of
    that row's input tests.

    *Boolean outcome* — one source rule, many rows, each deciding true or
    false. This is ordinary DMN: a single obligation is expressed as a table
    enumerating the combinations that satisfy it. The rule's condition is then
    the OR of the rows that yield true. Measured against live AD-103 output
    this was the majority shape, and refusing it left a correctly-modelled
    table uncompiled.

    A decision with no table at all is read from its `literal_expression`
    (prompt Section 87), which is the form the formulator uses most often.
    """

    if decision.dmn_mapping_status != DmnMappingStatus.EXECUTABLE:
        return ConditionDerivation(ConditionDerivationReason.NOT_DECLARED_EXECUTABLE)

    table = decision.decision_table
    facts: list[RequiredFact] = []
    seen_facts: set[str] = set()

    def _require(name: str, data_type: str) -> None:
        """Record a fact the tree depends on, once."""

        if name and name not in seen_facts:
            seen_facts.add(name)
            facts.append(RequiredFact(name=name, data_type=data_type))

    def _require_from(leaf: ConditionNode, data_type: str) -> None:
        _require(getattr(leaf, "fact", ""), data_type)
        # A fact-relative test depends on the fact it compares *against* just
        # as much as the one it compares. Omitting it would leave the rule
        # blocking at evaluation time on an input no caller was ever told to
        # supply, which reads as a runtime fault rather than a known
        # requirement.
        if isinstance(leaf, FactRelativeComparisonCondition):
            _require(leaf.reference.fact, "number")

    if table is None:
        literal = decision.literal_expression
        if literal is None:
            return ConditionDerivation(ConditionDerivationReason.NO_EXECUTABLE_BODY)
        feel = (literal.feel or "").strip()
        parsed = parse_feel_boolean_expression(feel)
        if parsed is None:
            return ConditionDerivation(
                ConditionDerivationReason.LITERAL_EXPRESSION_UNSUPPORTED,
                unsupported_expression=feel,
            )
        for leaf in parsed:
            _require_from(leaf, _inferred_data_type(leaf))
        return ConditionDerivation(
            ConditionDerivationReason.DERIVED,
            condition=AllCondition(all=parsed),
            facts=tuple(facts),
        )

    def _compile_row(row: DmnTableRule) -> list[ConditionNode] | ConditionDerivation:
        """The AND-ed tests of one row, or the reason it could not be read."""

        if len(row.input_entries) != len(table.inputs):
            return ConditionDerivation(ConditionDerivationReason.TABLE_SHAPE_MISMATCH)
        leaves: list[ConditionNode] = []
        for column, entry in zip(table.inputs, row.input_entries):
            fact = _fact_name(column)
            if not fact:
                return ConditionDerivation(ConditionDerivationReason.NO_FACT_FOR_COLUMN)
            parsed_entry = parse_feel_unary_test(fact, entry)
            if parsed_entry is None:
                return ConditionDerivation(
                    ConditionDerivationReason.UNSUPPORTED_UNARY_TEST,
                    unsupported_expression=f"{fact} {entry}".strip(),
                )
            if not parsed_entry:
                continue
            leaves.extend(parsed_entry)
            _require(fact, column.type or "string")
            for leaf in parsed_entry:
                if isinstance(leaf, FactRelativeComparisonCondition):
                    _require(leaf.reference.fact, "number")
        return leaves

    row_index = _row_for_index(decision, index)
    if row_index is not None:
        compiled = _compile_row(table.rules[row_index])
        if isinstance(compiled, ConditionDerivation):
            return compiled
        if not compiled:
            # Every column was "any value": the row imposes no test at all, so
            # it is not a condition — treat it as non-derivable rather than
            # emitting a vacuously-true rule that claims to be executable.
            return ConditionDerivation(ConditionDerivationReason.VACUOUS)
        return ConditionDerivation(
            ConditionDerivationReason.DERIVED,
            condition=AllCondition(all=compiled),
            facts=tuple(facts),
        )

    if index not in decision.source_rule_indexes:
        return ConditionDerivation(ConditionDerivationReason.NO_TABLE_ROW)
    if len(decision.source_rule_indexes) != 1 or not _is_boolean_outcome_table(table):
        return ConditionDerivation(ConditionDerivationReason.NO_TABLE_ROW)

    branches: list[ConditionNode] = []
    for row in table.rules:
        if not _row_is_satisfying(row):
            continue
        compiled = _compile_row(row)
        if isinstance(compiled, ConditionDerivation):
            return compiled
        if not compiled:
            # This row is satisfied unconditionally, so the OR over rows is
            # true for every input. Same reasoning as the vacuous single row:
            # an always-true tree that calls itself executable is worse than
            # no tree at all.
            return ConditionDerivation(ConditionDerivationReason.VACUOUS)
        branches.append(AllCondition(all=compiled))

    if not branches:
        # No combination of inputs satisfies the rule. That is a far stronger
        # claim than "we could not compile it" — it would deny every request —
        # so it is refused rather than asserted from a table that may simply
        # have been modelled the other way round.
        return ConditionDerivation(ConditionDerivationReason.NO_SATISFYING_ROW)

    condition: ConditionNode = branches[0] if len(branches) == 1 else AnyCondition(any=branches)
    return ConditionDerivation(
        ConditionDerivationReason.DERIVED, condition=condition, facts=tuple(facts)
    )


def derive_condition(
    decision: DmnDecision, index: int
) -> tuple[ConditionNode, list[RequiredFact]] | None:
    """Derive an executable condition for canonical policy `index`, or None.

    Thin wrapper over `derive_condition_outcome` for callers that only need to
    know whether a condition was produced. Prefer the outcome function where
    the *reason* matters, since a bare `None` cannot distinguish "nothing to
    compile" from "grounded logic this platform cannot yet represent".
    """

    outcome = derive_condition_outcome(decision, index)
    if outcome.condition is None:
        return None
    return outcome.condition, list(outcome.facts)


def _is_separator_predicate(predicate: str) -> bool:
    """True when `predicate` is punctuation-only (e.g. bare `":"` or `"-"`).

    Stage 2 uses subject/predicate/object as a generic triple for every rule
    type, but has no dedicated guidance for `definition`/`classification`
    (spec sections 10-19 cover only the other ten types). For those, the
    model idiomatically emits the dictionary "Term: Definition" separator as
    a literal `predicate=":"` rather than a verb — reasonable given the
    prompt gives it no better convention, but naive `predicate + object`
    concatenation then produces a stray leading punctuation mark ahead of
    the actual definition text (e.g. `": Work considered..."`).
    """

    return bool(predicate) and not any(c.isalnum() for c in predicate)


#: Explains the platform limitation behind `LITERAL_EXPRESSION_UNSUPPORTED` and
#: `UNSUPPORTED_UNARY_TEST` in the reviewer's own terms.
#:
#: Both mean the same thing operationally: the trusted configuration did its
#: job, the agent grounded every fact path in it, and the compiler is what
#: fell short. Saying "supply the missing mapping" here would send a reviewer
#: to edit a fact model that is already complete.
_PLATFORM_LIMIT_NOTE = (
    "This is a platform limitation, not a missing mapping: the condition tree "
    "compares one fact against a literal value, and cannot yet represent a "
    "comparison against an expression over another fact (for example a "
    "proportion of some other quantity). Extending it requires a change to the "
    "condition contract and the evaluator, not to the trusted configuration."
)


#: Comparative predicates that state which side of a bound the rule is about,
#: with the operator each implies when asserted and when negated.
#:
#: Keyed on the predicate because the predicate names the comparison. The
#: modality then decides direction: "shall not exceed X" forbids exceeding, so
#: the rule's own test is that the value stays within the bound.
_BOUND_PREDICATES: tuple[tuple[re.Pattern[str], ConditionOperator, ConditionOperator], ...] = (
    (
        re.compile(r"\bexceed", re.IGNORECASE),
        ConditionOperator.GREATER_THAN,
        ConditionOperator.LESS_THAN_OR_EQUAL,
    ),
    (
        re.compile(
            r"\blimited\s+to\b|\bup\s+to\s+a\s+maximum\s+of\b|\bat\s+most\b|\bno\s+more\s+than\b",
            re.IGNORECASE,
        ),
        ConditionOperator.LESS_THAN_OR_EQUAL,
        ConditionOperator.GREATER_THAN,
    ),
    (
        re.compile(r"\bat\s+least\b|\bno\s+less\s+than\b|\bminimum\s+of\b", re.IGNORECASE),
        ConditionOperator.GREATER_THAN_OR_EQUAL,
        ConditionOperator.LESS_THAN,
    ),
)

#: Negation written into the predicate rather than the modal word. Source text
#: puts it in either place — "shall not exceed" and "not exceeding" state the
#: same bound — and reading only the modality inverted the second one.
_NEGATED_PREDICATE_RE = re.compile(r"^\s*(?:not|never)\b", re.IGNORECASE)


def condition_from_stated_bound(
    rule: CanonicalPolicyRule | None,
) -> tuple[ConditionNode, list[RequiredFact]] | None:
    """Compile a proportional bound that the sentence states in full.

    "The annual increase shall not exceed 10% of the current basic salary"
    names both quantities and the comparison between them. Nothing outside the
    document is needed to express that, so it compiles without a trusted fact
    model: the fact *names* come from the sentence, and a consumer supplies
    values for them as they would for any other named input.

    That is a different claim from inventing a fact path. A path asserts some
    system holds a field at an address, which the document never said. These
    names assert only that the policy talks about these two things, which it
    demonstrably does.

    Returns None unless every part is stated — a subject to measure, a
    comparative predicate, and a threshold expressed as a proportion — because
    the alternative is guessing which comparison the document meant.
    """

    if rule is None:
        return None
    subject = (rule.subject or "").strip()
    predicate = (rule.predicate or "").strip()
    threshold = (rule.threshold or "").strip() or (rule.object or "").strip()
    if not subject or not predicate or not threshold:
        return None

    proportion = parse_proportion(threshold)
    if proportion is None:
        return None
    factor, base_phrase = proportion

    negated = is_negative_modality(rule.modality) or bool(_NEGATED_PREDICATE_RE.match(predicate))
    for pattern, asserted, when_negated in _BOUND_PREDICATES:
        if not pattern.search(predicate):
            continue
        subject_fact = _slugify(subject)
        base_fact = _slugify(base_phrase)
        if not subject_fact or not base_fact or subject_fact == base_fact:
            return None
        condition = FactRelativeComparisonCondition(
            fact=subject_fact,
            operator=when_negated if negated else asserted,
            reference=FactOperand(fact=base_fact, factor=factor),
        )
        return condition, [
            RequiredFact(name=subject_fact, data_type="number"),
            RequiredFact(name=base_fact, data_type="number"),
        ]
    return None


def _reconciled_facts(
    facts: list[PolicyFact], required: list[RequiredFact]
) -> list[PolicyFact]:
    """Fill a fact's type from the comparison the rule makes about it.

    `facts_for` reads a type only where the phrase writes one, which is right:
    "Annual increase" contains no digits and asserting a type from the words
    alone would be a guess. But once the rule compiles a numeric comparison
    over that fact, the sentence *has* said it is a quantity, and leaving the
    published type blank made `fact_model` and `required_facts` disagree about
    the same name — a consumer reading either one alone got a different answer.

    Only fills a gap. A type the phrase states is never overwritten, because
    the phrase is the stronger evidence: it says money or duration where a
    compiled comparison can only say "a number".
    """

    if not required:
        return facts
    declared = {item.name: item.data_type for item in required if item.data_type}
    return [
        fact.model_copy(update={"data_type": declared[fact.name]})
        if fact.data_type is None and fact.name in declared
        else fact
        for fact in facts
    ]


def condition_provenance(
    policy: CanonicalPolicy,
    derived: object | None,
    outcome: "ConditionDerivation | None" = None,
    from_stated_bound: bool = False,
) -> ConditionProvenance:
    """Explain *why* a rule's condition tree looks the way it does.

    Both an unconditional rule and a rule whose conditions could not be
    projected end up with an empty `all: []` tree, and until this existed they
    were indistinguishable. That conflation is the dangerous one: "this rule
    genuinely applies always" and "this rule has conditions we failed to
    encode" demand opposite responses from a reviewer, and reading the second
    as the first turns a narrow permission into an open one.

    `outcome`, when supplied, separates a third case that used to hide inside
    the second: the agent produced complete, configuration-grounded executable
    logic that this platform cannot represent. That one needs an engineering
    change, so reporting it as a missing mapping wastes a reviewer's time on a
    fact model that is already correct.

    An empty tree is never repaired here by inventing a placeholder condition.
    A synthesised always-false node would be a constraint the document never
    stated — the same fabrication the pointer-only design exists to prevent.
    The honest move is to say which case it is and route it to a human.

    `from_stated_bound` marks a fifth case, and is kept distinct from `derived`
    on purpose. A derived tree comes from a decision the formulator declared; a
    stated bound comes from reading the sentence's own comparison. Both are
    executable, but a reviewer checks them differently — the second is checked
    against one sentence — so collapsing them would hide which check applies.

    Returns a code and nothing else. Each case used to carry a sentence saying
    what a reviewer should do next; that is workflow guidance rather than a
    property of the policy, and it does not belong in a record whose consumer
    is a search API and a judge. The interface that shows a code to a human is
    where the wording for a human lives.
    """

    stated = (getattr(policy.rule, "condition", None) or "").strip() if policy.rule else ""

    if derived is not None:
        return ConditionProvenance(code="derived")

    if from_stated_bound:
        return ConditionProvenance(code="derived_from_stated_bound")

    if outcome is not None and outcome.platform_limited:
        return ConditionProvenance(
            code="conditions_not_representable",
            unsupported_expression=outcome.unsupported_expression,
        )

    if stated:
        return ConditionProvenance(code="conditions_not_projected")
    return ConditionProvenance(code="no_scope_derived")


def condition_provenance_for(formulation: "RuleFormulation | None") -> ConditionProvenance | None:
    """Re-derive a stored rule's condition provenance from its formulation.

    The read-path counterpart to what `formulation_to_candidate_rules` computes
    at extraction time, and the same reasoning as `_decision_readiness_for`: it
    is a pure function of `formulation`, which is persisted, so a stored second
    copy could only ever disagree with the record it came from — and correcting
    a message would leave every already-published rule carrying the old one.

    `source_index` is what makes this exact rather than approximate. A DMN
    decision may span several canonical rules (spec Section 91), so the
    provenance depends on *which* row belongs to this rule, and that is the
    field retained to answer it.
    """

    if formulation is None or formulation.canonical is None:
        return None
    index = formulation.source_index
    outcomes = [derive_condition_outcome(d, index) for d in formulation.dmn_decisions]
    derived = next((o for o in outcomes if o.derived), None)
    blocking = next(
        (o for o in outcomes if o.platform_limited),
        outcomes[0] if outcomes else None,
    )
    return condition_provenance(formulation.canonical, derived, blocking)


#: Modalities that forbid rather than require.
#:
#: The canonical record keeps the source's own modal word ("shall", "shall not",
#: "may"), and the effect derived from a rule type alone loses the negation
#: entirely. That produced a rule whose stated action was "exceed 10% of the
#: employee's current basic salary" from a source reading "shall NOT exceed 10%
#: …" — an instruction to do the forbidden thing, which is the worst output this
#: system can produce, because it is confidently the inverse of the policy.
#:
#: Matched on the modal word only, never on the predicate or object: "no" inside
#: a noun phrase ("no-fault termination") is not a negation of the rule, and
#: reading further would start inferring meaning from wording.
_NEGATIVE_MODALITY_RE = re.compile(
    r"^\s*(?:shall|must|may|can|will|should|does|do|is|are)?\s*(?:not|never)\b|^\s*cannot\b|^\s*no\b",
    re.IGNORECASE,
)

#: "no less than", "no more than", "no later than" — a bound, not a ban. The
#: bare `no` in `_NEGATIVE_MODALITY_RE` would otherwise read a floor as a
#: prohibition and invert the rule it describes.
_COMPARATIVE_NO_RE = re.compile(
    r"^\s*no\s+(?:less|more|fewer|greater|later|earlier|sooner)\b", re.IGNORECASE
)


def is_negative_modality(modality: str | None) -> bool:
    """True when the source's modal word forbids rather than requires."""

    return bool(_NEGATIVE_MODALITY_RE.match(modality or ""))


def states_a_negation(rule: CanonicalPolicyRule | None) -> bool:
    """True when the sentence forbids, wherever it wrote the negation.

    Source text puts it in either slot and means the same thing: "shall not
    exceed 10% of the base" and "not exceeding 5% of the base" are both bounds.
    Reading only `modality` classified the first as a prohibition and the
    second as an obligation, so two sentences of identical force were badged
    "Prohibits" and "Requires" in the same list — and the second told a
    decision point to carry out the thing the document limits.

    A comparative "no" is excluded. "no less than three months" sets a floor
    and obliges; it does not forbid, and reading its "no" as a prohibition
    would invert a requirement into a ban. Measured over the corpus, the rule
    change flips exactly one record and it is the one written "not exceeding".
    """

    if rule is None:
        return False
    if is_negative_modality(rule.modality):
        return True
    predicate = (rule.predicate or "").strip()
    if _COMPARATIVE_NO_RE.match(predicate):
        return False
    return is_negative_modality(predicate)


def _exceptions_for(canonical_rule: CanonicalPolicyRule | None) -> list[RuleException]:
    """Carry the source's stated exception into the rule's exception list.

    The formulator captures carve-out language in the canonical `exception`
    field — "Unless otherwise stipulated in the employment contract" on
    AI-c3e9ccec25, for one — and that text was then dropped here. Across the
    whole AD-103 corpus no rule carried a single `RuleException`, while the
    canonical records held the exception text all along.

    Only the description is populated. `condition` and `effect_override` stay
    None because the source states what the exception *is*, not what it tests
    or what it changes the outcome to; deriving either would manufacture policy.
    `RuleException` allows exactly that shape — a prose carve-out with no
    machine-readable condition — so nothing has to be invented to record it.

    A stable `exception_id` derives from the text rather than a UUID, so
    re-extracting an unchanged document produces an identical rule and the
    delta comparison does not report a change that did not happen.
    """

    if canonical_rule is None:
        return []
    text = (canonical_rule.exception or "").strip()
    if not text:
        return []
    digest = hashlib.sha256(" ".join(text.split()).casefold().encode("utf-8")).hexdigest()[:10]
    return [RuleException(exception_id=f"EXC-{digest}", description=text)]


def _decision_readiness_for(policy: CanonicalPolicy) -> DecisionReadiness:
    """Whether an LLM can decide this rule, and what it needs to do so.

    Deliberately *not* written into the stored payload. It is a pure function
    of `formulation.canonical`, which is persisted, so the read paths derive it
    and the two can never disagree.

    That is not a style preference — it was learned. An earlier version stored
    it at extraction time, and when the assessment was corrected (a
    `classification` carrying a 5% threshold was being reported as stating no
    decision) every already-extracted rule kept the stale verdict, because the
    stored copy shadowed the fix. Re-extracting a document to pick up a change
    in a derivation over data already on disk is the wrong price to pay.

    Everything in it is quoted from the canonical record. Nothing is inferred
    from wording similarity, and no fact path or org-model identifier is
    invented — `policy_parties` and `evaluability` own those guarantees.
    """

    assessment = assess_policy(policy)
    return DecisionReadiness(
        evaluability=assessment.evaluability.value,
        required_attributes=[
            RequiredAttributeRef(phrase=attribute.phrase, role=attribute.role)
            for attribute in assessment.attributes_referenced
        ],
        parties=[
            RulePartyRef(
                name=party.name,
                role=PartyRoleName(party.role.value),
                source=party.source_field,
            )
            for party in assessment.parties
        ],
    )


def _title_for(policy: CanonicalPolicy) -> str:
    """A readable title from the canonical decomposition, falling back to source."""

    rule = policy.rule
    parts: list[str] = []
    if rule is not None:
        predicate = rule.predicate or ""
        if _is_separator_predicate(predicate):
            parts = [p for p in (rule.subject, rule.object) if p]
        else:
            parts = [p for p in (rule.subject, rule.modality, rule.predicate, rule.object) if p]
    text = " ".join(parts) if parts else policy.source_text
    text = " ".join(text.split())
    return (text[:197] + "...") if len(text) > 200 else (text or "Untitled formulated rule")


def _effect_action(policy: CanonicalPolicy) -> str:
    """The action a PEP must carry out, taken from the source's own words.

    Deliberately unbounded in length (unlike the sibling `_title_for`, which
    truncates for compact display). This is the evaluator-facing payload:
    `_apply_combining_algorithm` (engine.py) returns it verbatim as the
    decision `outcome` and puts it straight into `required_actions`/
    `denied_actions`, so a caller relies on its literal text. A prior version
    silently hard-cut this at 200 characters with no ellipsis marker (unlike
    `_title_for`'s truncation, which at least appends "..."), which for a
    `definition`/`classification` rule — where the "action" is the whole
    definition body, not a short imperative phrase (see
    `correlation_agent.py`'s `_signals_for`: real extracted corpora routinely
    put "a whole clause" here) — silently dropped the tail of the sentence.
    The quality dashboard's `data_integrity` check exists to catch exactly
    this class of defect; nothing downstream (evaluator, frontend, or
    `ai_quality`'s own conflicting-effect grouping) assumes a bounded length,
    so removing the cap is correct rather than merely raising it.
    """

    rule = policy.rule
    if rule is None:
        return ""
    predicate = rule.predicate or ""
    obj = rule.object or ""
    parts = [obj] if _is_separator_predicate(predicate) else [p for p in (predicate, obj) if p]
    return " ".join(" ".join(parts).split())


#: Provenance codes whose stored condition tree *understates* the source.
#:
#: In each of these the tree ends up empty — reading as "always applies" —
#: while the document states conditions that do apply. The danger is identical
#: regardless of why projection failed, and it is the dangerous direction:
#: a narrow permission read as an open one. Membership is therefore decided by
#: that shared consequence, not by the cause, which is recorded separately in
#: the provenance note.
_TREE_UNDERSTATES_SOURCE = frozenset({"conditions_not_projected", "conditions_not_representable"})


def _ambiguity_for(
    policy: CanonicalPolicy, executable: bool, condition_code: str = "derived"
) -> AmbiguityStatus:
    """Whether the *document's own wording* is unclear. Nothing else.

    This answers one question: did the extractor find the source text itself
    ambiguous? It is a property of the policy, reported by the agent that read
    it, and a reader deciding whether to trust a record needs it.

    It deliberately no longer reflects anything about the DMN projection.
    Whether a rule compiles is a question about this platform's configuration
    and its condition format; it says nothing about whether the document is
    clear. Folding the two together made the flag fire on most of the corpus —
    a plainly worded definition carrying the same alarm as a genuinely vague
    clause — which left it carrying no signal at all while still demanding
    attention on every row.

    `executable` and `condition_code` are retained in the signature because
    callers pass them and because keeping the parameters makes the omission
    explicit rather than something a later reader has to infer.
    """

    if policy.ambiguity or policy.extraction_status == ExtractionStatus.AMBIGUOUS:
        return AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    if policy.extraction_status == ExtractionStatus.INCOMPLETE or policy.missing_components:
        return AmbiguityStatus.NON_BLOCKING
    return AmbiguityStatus.NONE


def _description_for(policy: CanonicalPolicy, decisions: list[DmnDecision], source_note: str) -> str:
    """The policy as written. Nothing else.

    This used to append five machine annotations to every description — the
    formulating agent and source element, the DMN mapping status, any
    enrichment requirement codes, ambiguity codes, and missing components —
    followed by a sixth from the caller explaining the condition tree. A
    reviewer opening a rule met its sentence and then a paragraph of brackets:

        "The recommendations of the director on allowances and benefits are
         subject to the approval of the President. [Formulated by policy agent
         — source: p1-E000008] [DMN mapping: not_directly_mappable]
         [Conditions: no_scope_derived — No conditions were found in the
         source. …]"

    Every one of those facts is already carried structurally, and was even
    then: the source element on `lineage`, the mapping status and requirement
    codes on `formulation.dmn_decisions`, ambiguity and missing components on
    `formulation.canonical`, and the condition reason on
    `condition_provenance`. The annotations were a second copy in prose of
    data the record already held.

    The duplication was not merely untidy. `policy_faithfulness` had to stop
    reading `description` altogether, because the appended note quotes the very
    condition it reports as lost — which made a check for lost conditions
    incapable of failing, and it reported zero findings across 47 rules while
    three housing-allowance rules had each dropped the staff category that
    distinguished them.

    `decisions` and `source_note` are retained in the signature: callers pass
    them, and the projection status is deliberately *not* part of the
    description because it describes the projection rather than the policy.
    """

    return policy.source_text.strip()


def _passage_matches_for_policy(source_text: str, passages: list[PolicyPassage]) -> list[int]:
    """Find which Stage-1 passage(s) a canonical policy's `source_text` came from.

    Stage 2 is instructed to preserve `source_text` verbatim from the passage
    it read (spec Section 7), so in the overwhelmingly common case exactly one
    passage's text will contain — or be contained by — the policy's
    `source_text` once formatting noise (whitespace, quote-mark style) is
    normalized. Checking containment in both directions also covers the
    legitimate case where Stage 2 merges two consecutive passages into one
    canonical policy (spec Section 91's "several provisions contribute to one
    rule" case — the same N:M rule-to-provision relationship LegalRuleML
    models explicitly, and true regardless of whether the provisions are
    statute articles, HR-handbook clauses, or IT-policy line items).

    Returns the indexes of every passage that matches, in passage order. An
    empty list means no passage could be matched with confidence, and the
    caller must fall back to coarser evidence rather than guessing — silently
    attributing a rule to the wrong clause is worse than admitting the match
    is unclear.
    """

    needle = _normalize(source_text)
    if not needle:
        return []

    matches = []
    for i, passage in enumerate(passages):
        hay = _normalize(passage.text)
        if not hay:
            continue
        if needle in hay or hay in needle:
            matches.append(i)
    return matches


#: Minimum normalized clause length before a clause may be attributed to a rule
#: on the strength of the clause being contained *in* the rule's source text.
#: Short fragments ("1.", "Wages", a stray heading) appear inside almost any
#: longer text by accident, so attributing on that basis alone re-creates the
#: over-citation this narrowing exists to remove.
_MIN_CONTAINED_CLAUSE_CHARS = 16


def _narrow_refs_to_policy(
    source_text: str,
    refs: list[str],
    clause_texts_by_ref: dict[str, str] | None,
) -> list[str]:
    """Narrow a passage's clause span to the clause(s) that carry *this* policy.

    `_passage_matches_for_policy` resolves a rule to the Stage-1 passage it was
    formulated from, but a passage's span is only as fine-grained as the passage
    itself. One passage routinely covers a whole contiguous block — a statute's
    definitions article, an HR handbook's eligibility section — that ingestion
    split into several clauses. Every rule formulated from that block then
    inherits the block's *entire* clause span, so a rule defining one term cites
    the clauses of its neighbours too. Reviewers reasonably read that as the
    platform claiming the rule came from all of them.

    Clause text is available and the policy's `source_text` is verbatim, so the
    attribution can be checked directly instead of inherited: keep a clause when
    the policy's text is found inside it (the usual case — one clause holds the
    provision), or when the clause's own text is found inside the policy's (the
    converse case — one provision was split across several small clauses, such
    as a lead-in followed by numbered items).

    Falls back to the unnarrowed span whenever narrowing would produce nothing,
    on the same principle as the coarse batch fallback: an imprecise citation is
    more useful to a reviewer than none, and silently dropping evidence would be
    worse than keeping it broad.
    """

    if not clause_texts_by_ref or len(refs) < 2:
        return refs
    needle = _normalize(source_text)
    if not needle:
        return refs

    narrowed: list[str] = []
    for ref in refs:
        hay = _normalize(clause_texts_by_ref.get(ref, ""))
        if not hay:
            continue
        if needle in hay:
            narrowed.append(ref)
        elif len(hay) >= _MIN_CONTAINED_CLAUSE_CHARS and hay in needle:
            narrowed.append(ref)
    return narrowed or refs


def _topic_key(subject: str, predicate: str) -> str:
    """Identity of a policy topic: its subject and its predicate.

    Sole definition of the label a shared decision table is named by, so the
    string a reviewer reads is built in one place.

    Note what this is *not*: matching subjects and predicates do not establish
    that two statements are related. That is an inference about wording, and
    `PolicyRelationshipType` deliberately admits only relations a reader of the
    source could point at. An earlier attempt to link statements on this key
    alone is recorded in `relationship_discovery` as the lexical detector, which
    emits `candidate` edges for review — never `related_rule_ids`.
    """

    return " ".join(f"{subject} {predicate}".split())[:120]


def _group_labels(formulation: PolicyFormulation) -> dict[int, str]:
    """Cluster canonical policies that a single DMN decision covers.

    `group_label` exists to present variations of one policy topic together
    (approval bands, leave scenarios) instead of as unrelated rows. Sharing a
    decision table is exactly that relationship, stated by the agent itself
    under spec Section 91 ("multiple canonical rules may contribute to one DMN
    decision table") — so it is derived evidence, not a guess about topic
    similarity.

    Deliberately NOT derived from the canonical `relationships` field: the
    specification names that field in Section 93 but never defines its shape or
    vocabulary, so reading meaning into it would be invention.
    """

    labels: dict[int, str] = {}
    for decision in formulation.dmn_projection.decisions:
        indexes = decision.source_rule_indexes
        if len(indexes) < 2:
            continue
        anchor = formulation.canonical_policies[indexes[0]] if indexes[0] < len(
            formulation.canonical_policies
        ) else None
        subject = (anchor.rule.subject if anchor and anchor.rule else "") or ""
        predicate = (anchor.rule.predicate if anchor and anchor.rule else "") or ""
        label = _topic_key(subject, predicate)
        if not label:
            continue
        for index in indexes:
            labels.setdefault(index, label)
    return labels


def formulation_to_candidate_rules(
    formulation: PolicyFormulation,
    *,
    policy_set_id: str,
    extraction_run_id: str,
    deployment_name: str,
    prompt_version: str,
    parser_version: str,
    evidence: list[dict] | None = None,
    passages: list[PolicyPassage] | None = None,
    passage_clause_refs: list[list[str]] | None = None,
    clause_evidence_by_ref: dict[str, dict] | None = None,
    clause_texts_by_ref: dict[str, str] | None = None,
    source_note: str = "unspecified",
    category: str = "",
) -> tuple[list[CanonicalRule], list[dict]]:
    """Convert one formulation into draft `CanonicalRule`s ready for review.

    `evidence`/`source_note` are the coarse, whole-batch fallback. When
    `passages` and `passage_clause_refs` (parallel lists — index *i* of each
    describes the same Stage-1 passage) and `clause_evidence_by_ref` are also
    supplied, each canonical policy's `source_text` is matched back to the
    *specific* passage(s) it was formulated from (see
    `_passage_matches_for_policy`), and only those passages' clauses are used
    as that one rule's evidence and source note. A batch commonly spans
    several unrelated clauses (a document is walked in fixed-size windows, not
    one-topic-at-a-time), so without this, every rule drafted from a batch
    would cite every clause any passage in the batch came from — including
    clauses about a completely different topic than the rule itself. This
    applies to any source document type (statute, HR handbook, IT policy,
    procurement manual, ...), not just legal text.

    Supplying `clause_texts_by_ref` narrows that result one level further, from
    the passage's whole clause span down to the clause(s) whose text actually
    carries this policy (see `_narrow_refs_to_policy`). Passage granularity
    alone still over-cites whenever one passage covers a contiguous block that
    ingestion split into several clauses — a definitions article, an
    eligibility section — because every rule from that block inherits the whole
    block's span.

    A policy whose `source_text` cannot be matched to any passage keeps the
    coarse fallback rather than being left without evidence — an admittedly
    imprecise citation is still more useful to a reviewer than none, and the
    fallback is the same whole-batch evidence this function used before
    per-passage matching existed.

    Returns `(rules, skipped)`, where `skipped` entries carry a machine-readable
    reason so nothing disappears silently from an extraction run's summary.
    """

    rules: list[CanonicalRule] = []
    skipped: list[dict] = []
    group_labels = _group_labels(formulation)
    rule_ids_by_group: dict[str, list[str]] = {}
    default_evidence = evidence or []

    for index, policy in enumerate(formulation.canonical_policies):
        canonical_rule = policy.rule
        if canonical_rule is None:
            skipped.append(
                {"item": policy.source_text[:200], "reason": "canonical policy carried no rule"}
            )
            continue
        if canonical_rule.rule_type in _SKIPPED_RULE_TYPES:
            skipped.append(
                {
                    "item": policy.source_text[:200],
                    "reason": f"rule_type '{canonical_rule.rule_type.value}' carries no policy rule",
                }
            )
            continue

        mapped = _RULE_TYPE_MAP.get(canonical_rule.rule_type)
        if mapped is None:
            skipped.append(
                {
                    "item": policy.source_text[:200],
                    "reason": f"no platform mapping for rule_type '{canonical_rule.rule_type.value}'",
                }
            )
            continue
        rule_type, effect_type = mapped

        # A statement about the document is not a rule the platform should
        # enforce. "Those policies will be so noted at the beginning of each
        # policy" mapped to a routing rule with REQUIRE_ACTION, which tells a
        # decision point to carry out a document-drafting convention.
        #
        # Projected to INFORMATIONAL for the same reason classification and
        # definition are (see `_RULE_TYPE_MAP`): it neither authorizes nor
        # forbids, so any other effect asserts something the sentence does not.
        # The rule is kept and tagged rather than skipped — whether a sentence
        # carries policy is the reviewer's call, and `_SKIPPED_RULE_TYPES`
        # removes it from their view entirely.
        guidance = is_document_guidance(canonical_rule)
        if guidance:
            rule_type, effect_type = RuleType.DEFINITION, EffectType.INFORMATIONAL

        # A negated sentence forbids; it never obliges or permits.
        #
        # The rule type alone does not carry the negation — "shall not exceed
        # 10%" and "shall exceed 10%" are both `conditional_outcome` — so an
        # effect derived from the type inverted the policy and told a decision
        # point to do the forbidden thing. The negation is in the canonical
        # record, read from the source, so honouring it asserts nothing new.
        #
        # Read from the modal word *and* the predicate, because source text
        # uses both: "shall not exceed" and "not exceeding" state the same
        # bound, and reading only the first badged them "Prohibits" and
        # "Requires" in the same list.
        elif effect_type in (
            EffectType.REQUIRE_ACTION,
            EffectType.ALLOW,
        ) and states_a_negation(canonical_rule):
            rule_type, effect_type = RuleType.PROHIBITION, EffectType.DENY

        decisions = formulation.decisions_for(index)
        outcomes = [derive_condition_outcome(dec, index) for dec in decisions]
        derived = next((o for o in outcomes if o.derived), None)
        # When nothing compiled, report the most actionable failure rather than
        # the first. A decision the agent grounded but we could not represent
        # tells a reviewer something an ordinary non-executable one does not,
        # and it must not be masked by a sibling that was simply never
        # declared executable.
        blocking = next(
            (o for o in outcomes if o.platform_limited),
            outcomes[0] if outcomes else None,
        )
        stated_bound: tuple[ConditionNode, list[RequiredFact]] | None = None
        if derived is None:
            condition: ConditionNode = _VACUOUS_CONDITION
            required_facts: list[RequiredFact] = []
            machine_executable = False
        else:
            condition = derived.condition  # type: ignore[assignment]
            required_facts = list(derived.facts)
            machine_executable = True

        # A bound the sentence states in full needs no table behind it. The DMN
        # path derives from a decision the formulator declared; where it
        # declared none, the sentence may still have said everything required —
        # "shall not exceed 10% of the base" names both quantities and the
        # comparison between them. Read only as a fallback, so a declared
        # decision always wins where one exists.

        if derived is None:
            stated_bound = condition_from_stated_bound(canonical_rule)
            if stated_bound is not None:
                condition, required_facts = stated_bound
                machine_executable = True

        # Why the tree is empty, when it is. Recorded rather than inferred later
        # from the tree's shape, because the shape cannot distinguish "no
        # conditions exist" from "conditions exist but were not projected".
        provenance = condition_provenance(
            policy, derived, blocking, from_stated_bound=stated_bound is not None
        )

        # The facts this policy names, and the attribute table that pairs each
        # extracted attribute with the document's words and the fact a case
        # supplies for it. Computed once and used for both, so the two cannot
        # describe the same record differently.
        rule_facts = _reconciled_facts(facts_for(canonical_rule), required_facts)

        # Scope evidence to the clause(s) this specific policy was actually
        # formulated from, when the caller supplied enough to do that. See the
        # function docstring — this is what stops one rule from a multi-topic
        # batch citing clauses that belong to an unrelated rule from the same
        # batch.
        rule_evidence = default_evidence
        rule_source_note = source_note
        if passages and passage_clause_refs and clause_evidence_by_ref:
            matched_refs: list[str] = []
            seen_refs: set[str] = set()
            for passage_index in _passage_matches_for_policy(policy.source_text, passages):
                if passage_index >= len(passage_clause_refs):
                    continue
                for ref in passage_clause_refs[passage_index]:
                    if ref not in seen_refs:
                        seen_refs.add(ref)
                        matched_refs.append(ref)
            # A passage's span is coarser than the rule: narrow it to the
            # clause(s) whose text actually carries this policy, so sibling
            # provisions in the same block are not cited as this rule's source.
            matched_refs = _narrow_refs_to_policy(
                policy.source_text, matched_refs, clause_texts_by_ref
            )
            matched_evidence = [
                clause_evidence_by_ref[ref] for ref in matched_refs if ref in clause_evidence_by_ref
            ]
            if matched_evidence:
                rule_evidence = matched_evidence
                rule_source_note = "; ".join(matched_refs)

        rules.append(
            CanonicalRule(
                policy_set_id=policy_set_id,
                policy_version_id="draft",
                rule_id=f"AI-{uuid.uuid4().hex[:10]}",
                rule_revision=1,
                title=_title_for(policy),
                description=_description_for(policy, decisions, rule_source_note),
                rule_type=rule_type,
                authority=PolicyAuthority(level="ai_drafted", owner="policy-formulator", rank=0),
                scope=PolicyScope(),
                condition=condition,
                evaluation_mode=evaluation_mode_from(condition, required_facts),
                fact_model=rule_facts,
                attributes=attributes_for(canonical_rule, rule_facts),
                condition_provenance=provenance,
                effect=Effect(type=effect_type, action=_effect_action(policy)),
                required_facts=required_facts,
                exceptions=_exceptions_for(canonical_rule),
                effective_from=date.today(),
                machine_executable=machine_executable,
                ambiguity_status=_ambiguity_for(policy, machine_executable, provenance.code),
                review_status=ReviewStatus.CANDIDATE,
                evidence=rule_evidence,
                lineage=RuleLineage(
                    extraction_run_id=extraction_run_id,
                    deployment_name=deployment_name,
                    prompt_version=prompt_version,
                    parser_version=parser_version,
                    source_elements=rule_source_note,
                ),
                category=category,
                tags=[DOCUMENT_GUIDANCE_TAG] if guidance else [],
                group_label=group_labels.get(index, ""),
                formulation=RuleFormulation(
                    source_index=index, canonical=policy, dmn_decisions=decisions
                ),
            )
        )
        if rules[-1].group_label:
            rule_ids_by_group.setdefault(rules[-1].group_label, []).append(rules[-1].rule_id)

    # Second pass: a rule cannot name its siblings until they all have ids.
    for rule in rules:
        if rule.group_label:
            rule.related_rule_ids = [
                rid for rid in rule_ids_by_group[rule.group_label] if rid != rule.rule_id
            ]

    return rules, skipped
