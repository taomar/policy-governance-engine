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

import re
import uuid
from datetime import date

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionNode,
    ConditionOperator,
    FactComparisonCondition,
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
from policy_platform.contracts.policy import (
    AmbiguityStatus,
    CanonicalRule,
    Effect,
    EffectType,
    PolicyAuthority,
    PolicyScope,
    RequiredFact,
    ReviewStatus,
    RuleLineage,
    RuleType,
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
#: `classification`/`definition` map to `EffectType.INFORMATIONAL`, not
#: `ALLOW`: neither authorizes nor forbids anything, so `ALLOW` was a
#: dishonest projection — most visibly when the source is phrased negatively
#: ("shall NOT be included...") and the forced `ALLOW` asserts the literal
#: inverse of the rule's own text. See `ai_quality._definition_effect_findings`
#: for the defect this closes and `_apply_combining_algorithm` for why an
#: informational effect never competes on the allow/deny axis.
_RULE_TYPE_MAP: dict[CanonicalRuleType, tuple[RuleType, EffectType]] = {
    CanonicalRuleType.OBLIGATION: (RuleType.OBLIGATION, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.PROHIBITION: (RuleType.PROHIBITION, EffectType.DENY),
    CanonicalRuleType.PERMISSION: (RuleType.PERMISSION, EffectType.ALLOW),
    CanonicalRuleType.ENTITLEMENT: (RuleType.PERMISSION, EffectType.ALLOW),
    CanonicalRuleType.ELIGIBILITY: (RuleType.ELIGIBILITY, EffectType.ALLOW),
    CanonicalRuleType.INELIGIBILITY: (RuleType.ELIGIBILITY, EffectType.DENY),
    CanonicalRuleType.CONDITIONAL_OUTCOME: (RuleType.ROUTING, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.CALCULATION: (RuleType.CALCULATION, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.CLASSIFICATION: (RuleType.DEFINITION, EffectType.INFORMATIONAL),
    CanonicalRuleType.RECOMMENDATION: (RuleType.HUMAN_JUDGMENT_REQUIREMENT, EffectType.REQUIRE_ACTION),
    CanonicalRuleType.DEFINITION: (RuleType.DEFINITION, EffectType.INFORMATIONAL),
    CanonicalRuleType.AMBIGUOUS: (RuleType.HUMAN_JUDGMENT_REQUIREMENT, EffectType.REQUIRE_ACTION),
}

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


def parse_feel_unary_test(fact: str, expression: str) -> list[ConditionNode] | None:
    """Translate one FEEL unary test into condition leaves for `fact`.

    Returns:
        - ``[]`` for the "any value" tests (``-`` or empty), meaning this
          input places no constraint on the rule;
        - a list of leaves for a test that was fully understood;
        - ``None`` when the expression uses anything outside the supported
          subset, which the caller must treat as "not executable".

    Supported: ``-``, bare literals, ``= < <= > >= !=`` comparisons,
    ``[a..b]``/``(a..b]`` style ranges with inclusive/exclusive bounds, and
    comma-separated literal lists (rendered as ``in``).

    Everything else — ``not(...)``, function calls, arithmetic, date and
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
            value = _parse_feel_literal(expression[len(symbol):])
            if value is None:
                return None
            return [FactComparisonCondition(fact=fact, operator=operator, value=value)]

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


def derive_condition(
    decision: DmnDecision, index: int
) -> tuple[ConditionNode, list[RequiredFact]] | None:
    """Derive an executable condition for canonical policy `index`, or None.

    Returns None unless the agent itself declared the decision `executable`.
    That gate matters: `executable` is the agent's assertion that every fact
    path, type and value came from source or trusted configuration rather than
    from invention (spec Sections 42-44). Without it, any condition built here
    would rest on facts nobody vouched for.
    """

    if decision.dmn_mapping_status != DmnMappingStatus.EXECUTABLE:
        return None
    table = decision.decision_table
    row_index = _row_for_index(decision, index)
    if table is None or row_index is None:
        return None
    row = table.rules[row_index]
    if len(row.input_entries) != len(table.inputs):
        return None

    leaves: list[ConditionNode] = []
    facts: list[RequiredFact] = []
    for column, entry in zip(table.inputs, row.input_entries):
        fact = _fact_name(column)
        if not fact:
            return None
        parsed = parse_feel_unary_test(fact, entry)
        if parsed is None:
            return None
        if not parsed:
            continue
        leaves.extend(parsed)
        facts.append(RequiredFact(name=fact, data_type=(column.type or "string")))

    if not leaves:
        # Every column was "any value": the table row imposes no test at all,
        # so it is not a condition — treat it as non-derivable rather than
        # emitting a vacuously-true rule that claims to be executable.
        return None
    return AllCondition(all=leaves), facts


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
    """The action a PEP must carry out, taken from the source's own words."""

    rule = policy.rule
    if rule is None:
        return ""
    predicate = rule.predicate or ""
    obj = rule.object or ""
    parts = [obj] if _is_separator_predicate(predicate) else [p for p in (predicate, obj) if p]
    return " ".join(" ".join(parts).split())[:200]


def _ambiguity_for(policy: CanonicalPolicy, executable: bool) -> AmbiguityStatus:
    """Map extraction/ambiguity signals onto the platform's ambiguity ladder.

    Any recorded ambiguity code, or an ambiguous/incomplete extraction status,
    forces human judgement — as does the absence of a derivable machine
    condition, preserving the platform's existing invariant that a rule with no
    real condition is never marked unambiguous.
    """

    if policy.ambiguity or policy.extraction_status == ExtractionStatus.AMBIGUOUS:
        return AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    if not executable:
        return AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    if policy.extraction_status == ExtractionStatus.INCOMPLETE or policy.missing_components:
        return AmbiguityStatus.NON_BLOCKING
    return AmbiguityStatus.NONE


def _description_for(policy: CanonicalPolicy, decisions: list[DmnDecision], source_note: str) -> str:
    """Human-facing description: verbatim source first, then honest caveats.

    Reviewers judge a drafted rule against what the document actually said, so
    the source text leads. The notes that follow name every reason the rule is
    not executable, using the specification's own requirement codes, so a
    reviewer can see *what would have to be supplied* rather than just that
    something was missing.
    """

    lines = [policy.source_text.strip(), "", f"[Formulated by policy agent — source: {source_note}]"]
    statuses = {d.dmn_mapping_status.value for d in decisions}
    if statuses:
        lines.append(f"[DMN mapping: {', '.join(sorted(statuses))}]")
    requirements = sorted({r.value for d in decisions for r in d.requirements})
    if requirements:
        lines.append(f"[Enrichment required: {', '.join(requirements)}]")
    if policy.ambiguity:
        lines.append(f"[Ambiguity: {', '.join(a.value for a in policy.ambiguity)}]")
    if policy.missing_components:
        lines.append(f"[Missing: {', '.join(str(m) for m in policy.missing_components)}]")
    return "\n".join(lines).strip()


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
        label = " ".join(f"{subject} {predicate}".split())[:120]
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
    source_note: str = "unspecified",
    category: str = "",
) -> tuple[list[CanonicalRule], list[dict]]:
    """Convert one formulation into draft `CanonicalRule`s ready for review.

    Returns `(rules, skipped)`, where `skipped` entries carry a machine-readable
    reason so nothing disappears silently from an extraction run's summary.
    """

    rules: list[CanonicalRule] = []
    skipped: list[dict] = []
    group_labels = _group_labels(formulation)
    rule_ids_by_group: dict[str, list[str]] = {}

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

        decisions = formulation.decisions_for(index)
        derived = next(
            (d for d in (derive_condition(dec, index) for dec in decisions) if d is not None),
            None,
        )
        if derived is None:
            condition: ConditionNode = _VACUOUS_CONDITION
            required_facts: list[RequiredFact] = []
            machine_executable = False
        else:
            condition, required_facts = derived
            machine_executable = True

        rules.append(
            CanonicalRule(
                policy_set_id=policy_set_id,
                policy_version_id="draft",
                rule_id=f"AI-{uuid.uuid4().hex[:10]}",
                rule_revision=1,
                title=_title_for(policy),
                description=_description_for(policy, decisions, source_note),
                rule_type=rule_type,
                authority=PolicyAuthority(level="ai_drafted", owner="policy-formulator", rank=0),
                scope=PolicyScope(),
                condition=condition,
                effect=Effect(type=effect_type, action=_effect_action(policy)),
                required_facts=required_facts,
                effective_from=date.today(),
                machine_executable=machine_executable,
                ambiguity_status=_ambiguity_for(policy, machine_executable),
                review_status=ReviewStatus.CANDIDATE,
                evidence=evidence or [],
                lineage=RuleLineage(
                    extraction_run_id=extraction_run_id,
                    deployment_name=deployment_name,
                    prompt_version=prompt_version,
                    parser_version=parser_version,
                ),
                category=category,
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
