# ADR-0005: Condition evaluation uses an explicit allowlisted AST interpreter

## Status
Accepted

## Context
Section 14.1 requires an allowlisted condition AST supporting a fixed operator set,
and explicitly forbids `eval`, arbitrary code, arbitrary SQL, generated code,
unrestricted regular expressions, or network calls during condition evaluation.

## Decision
`policy_platform.contracts` defines a closed set of condition node types
(`AllCondition`, `AnyCondition`, `NotCondition`, `FactComparisonCondition`) as
Pydantic discriminated-union models, and a closed `ConditionOperator` string enum
matching exactly the operators listed in Section 14.1.
`policy_platform.evaluator.conditions` implements a single recursive-descent
interpreter (`evaluate_condition`) that pattern-matches on these closed types using
Python's `match` statement. There is no `eval`/`exec`, no dynamic attribute-based
dispatch, and no string-to-code evaluation anywhere in the evaluation path.

## Rationale
A closed type hierarchy plus an exhaustive `match` statement (with a final `case _:
raise` for unknown operators) makes it a deliberate code change to add a new
operator — this is the simplest mechanism that structurally prevents the forbidden
capabilities listed in Section 14.1.

## Consequences
- **Positive:** condition evaluation is fully deterministic, side-effect free, and
  auditable; every supported operator is enumerable for documentation and testing.
- **Negative:** adding a genuinely new operator requires a code change and version
  bump to the schema version (Section 13.6 fingerprint includes schema version).
