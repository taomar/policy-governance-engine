"""Rule selection and precedence resolution (Section 15.4).

Section 15.4 lists exactly 8 precedence dimensions, in this literal order:
1. Authority rank.
2. Jurisdiction.
3. Scope specificity.
4. Explicit override.
5. Explicit exception.
6. Effective date.
7. Rule priority.
8. Supersession relationship.

Each is implemented below in that order. Two dimensions required an explicit
interpretive choice because the spec does not further define them — both are
called out at the point they're implemented, rather than silently guessed:

- "Jurisdiction" as its OWN dimension (distinct from "scope specificity" one
  level below) is read as lex specialis: among applicable rules, one with a
  specific (non-wildcard) jurisdiction that matched the request is more
  targeted than one with no jurisdiction restriction, and ranks higher. This
  mirrors the real-world legal principle that a specific-jurisdiction rule
  overrides a general default. "Scope specificity" then only scores the
  remaining 3 dimensions (organizational unit, persona, process) so the
  jurisdiction signal isn't silently double-counted across two list items.
- "Explicit exception" is read structurally, in parallel with "Explicit
  override" right above it in the same list (both literally named
  "Explicit..."): a rule authored with `rule_type == EXCEPTION` or carrying
  one or more `RuleException` entries is a declared, authoring-time exception
  to a more general rule, and ranks higher on that basis alone — independent
  of whether any particular exception is *triggered* for a given evaluation.
  The alternative reading (rank only rules whose exception actually triggered
  this evaluation) was considered and rejected here because it would require
  evaluating conditions before precedence ordering, an architecture change
  the spec doesn't call for, and because "explicit" more naturally describes
  a declared trait than a runtime outcome.

"Supersession relationship" is inherently a relationship between two specific
rules, not a scalar property of one rule in isolation — it is handled as a
binary flag ("is this rule named in some other applicable rule's
`supersedes_rule_ids`?") computed across the full candidate set, which
correctly orders direct supersession pairs. Multi-hop transitive chains
(A supersedes B supersedes C) are not fully resolved by this binary scoring;
this is a known, documented simplification, not a silent gap.

This is NOT "newest rule always wins" (explicitly forbidden by Section 15.4) —
six other dimensions are considered before effective date, and effective date
itself is only a tiebreak among rules tied on everything above it, with
rule_id as the final deterministic tiebreaker to guarantee a stable total
order regardless of input ordering.
"""
from __future__ import annotations

from policy_platform.contracts.policy import CanonicalRule, RuleType


def _jurisdiction_specificity(rule: CanonicalRule) -> int:
    jurisdictions = rule.scope.jurisdictions
    return 1 if jurisdictions and jurisdictions != ["*"] else 0


def _scope_specificity(rule: CanonicalRule) -> int:
    """Specificity across the 3 non-jurisdiction scope dimensions.
    Jurisdiction is scored separately (see `_jurisdiction_specificity`) since
    Section 15.4 lists it as its own, higher-priority dimension.
    """
    scope = rule.scope
    dimensions = [scope.organizational_units, scope.personas, scope.processes]
    score = 0
    for dim in dimensions:
        if dim and dim != ["*"]:
            score += 1
    return score


def _has_explicit_exception(rule: CanonicalRule) -> bool:
    return rule.rule_type == RuleType.EXCEPTION or bool(rule.exceptions)


def _is_superseded_by_another(rule: CanonicalRule, all_rules: list[CanonicalRule]) -> bool:
    return any(rule.rule_id in r.supersedes_rule_ids for r in all_rules if r.rule_id != rule.rule_id)


def sort_key(rule: CanonicalRule, all_rules: list[CanonicalRule]) -> tuple:
    return (
        -rule.authority.rank,
        -_jurisdiction_specificity(rule),
        -_scope_specificity(rule),
        -int(rule.is_explicit_override),
        -int(_has_explicit_exception(rule)),
        rule.effective_from.toordinal() * -1,
        -rule.priority,
        int(_is_superseded_by_another(rule, all_rules)),
        rule.rule_id,
    )


def order_rules_by_precedence(rules: list[CanonicalRule]) -> list[CanonicalRule]:
    """Return rules in a stable, deterministic precedence order."""

    return sorted(rules, key=lambda r: sort_key(r, rules))
