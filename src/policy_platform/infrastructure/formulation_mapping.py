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
from policy_platform.contracts.passage import PolicyPassage
from policy_platform.infrastructure.passage_extractor import _normalize
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


def condition_provenance(policy: CanonicalPolicy, derived: object | None) -> tuple[str, str]:
    """Explain *why* a rule's condition tree looks the way it does.

    Both an unconditional rule and a rule whose conditions could not be
    projected end up with an empty `all: []` tree, and until this existed they
    were indistinguishable. That conflation is the dangerous one: "this rule
    genuinely applies always" and "this rule has conditions we failed to
    encode" demand opposite responses from a reviewer, and reading the second
    as the first turns a narrow permission into an open one.

    An empty tree is never repaired here by inventing a placeholder condition.
    A synthesised always-false node would be a constraint the document never
    stated — the same fabrication the pointer-only design exists to prevent.
    The honest move is to say which case it is and route it to a human.

    Returns ``(code, message)``.
    """

    stated = (getattr(policy.rule, "condition", None) or "").strip() if policy.rule else ""

    if derived is not None:
        return ("derived", "Conditions were projected into an executable tree.")
    if stated:
        return (
            "conditions_not_projected",
            "The source states conditions, but they could not be projected into "
            f"executable bindings: {stated!r}. The rule must not be treated as "
            "unconditional — a reviewer must supply the missing mapping.",
        )
    return (
        "no_scope_derived",
        "No conditions were found in the source. The rule may genuinely be "
        "unconditional, or its scope may have been missed during extraction; a "
        "reviewer must decide which before it can be relied on.",
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


def _ambiguity_for(
    policy: CanonicalPolicy, executable: bool, condition_code: str = "derived"
) -> AmbiguityStatus:
    """Map extraction/ambiguity signals onto the platform's ambiguity ladder.

    `ambiguity_status` answers one question only: is the rule's *meaning*
    (the source text itself) unclear enough that a policy/business reviewer
    must interpret it before the rule can be trusted? It must stay
    independent of `executable` (whether a `trusted_config` — Section 83 —
    was supplied so the rule can become an executable DMN decision), which
    is a *technical configuration* question, not a content question, and is
    already fully captured by `machine_executable` / `dmn_mapping_status`.

    Until 2025-Q_ these two were conflated here: any non-executable rule
    (which, absent a `trusted_config`, is every rule) was unconditionally
    forced to HUMAN_JUDGMENT_REQUIRED. That made the flag carry zero
    discriminative signal — a plainly unambiguous definition like "Minor: any
    person of 15 and below 18 years of age" was flagged identically to a
    genuinely vague clause, because both merely lacked machine-executability.
    A rule that is textually clear but not yet executable now maps to
    NON_BLOCKING ("needs configuration, not clarification") instead of
    HUMAN_JUDGMENT_REQUIRED ("needs a human to interpret unclear wording").
    """

    if policy.ambiguity or policy.extraction_status == ExtractionStatus.AMBIGUOUS:
        return AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    # A rule whose source states conditions that were not projected is *not*
    # merely unconfigured. Its stored tree says "always applies" while the
    # document says otherwise, so a human must reconcile the two before it can
    # be relied on — treating this as NON_BLOCKING would let a narrow
    # permission read as an open one.
    if condition_code == "conditions_not_projected":
        return AmbiguityStatus.HUMAN_JUDGMENT_REQUIRED
    if policy.extraction_status == ExtractionStatus.INCOMPLETE or policy.missing_components:
        return AmbiguityStatus.NON_BLOCKING
    if not executable:
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

        # Why the tree is empty, when it is. Recorded rather than inferred later
        # from the tree's shape, because the shape cannot distinguish "no
        # conditions exist" from "conditions exist but were not projected".
        condition_code, condition_note = condition_provenance(policy, derived)

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
                description=_description_for(policy, decisions, rule_source_note)
                + f"\n[Conditions: {condition_code} — {condition_note}]",
                rule_type=rule_type,
                authority=PolicyAuthority(level="ai_drafted", owner="policy-formulator", rank=0),
                scope=PolicyScope(),
                condition=condition,
                effect=Effect(type=effect_type, action=_effect_action(policy)),
                required_facts=required_facts,
                effective_from=date.today(),
                machine_executable=machine_executable,
                ambiguity_status=_ambiguity_for(policy, machine_executable, condition_code),
                review_status=ReviewStatus.CANDIDATE,
                evidence=rule_evidence,
                lineage=RuleLineage(
                    extraction_run_id=extraction_run_id,
                    deployment_name=deployment_name,
                    prompt_version=prompt_version,
                    parser_version=parser_version,
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
