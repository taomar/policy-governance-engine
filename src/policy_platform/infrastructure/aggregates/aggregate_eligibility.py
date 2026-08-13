"""Deterministic eligibility rules for cross-rule aggregate limits.

An aggregate limit only does something if the deterministic evaluator can
actually count a rule's contribution. Two lines in
`evaluator/engine.py::_evaluate_aggregate_limits` decide that, and both fail
*silently* — they skip the contribution rather than raising:

    if result is None or result.status != SATISFIED or result.overridden_by:
        continue                                   # (1) rule never contributes
    amount = facts.get(contribution.amount_fact)
    if isinstance(amount, (int, float)):           # (2) non-numeric -> 0
        total += float(amount)

That silence is the whole reason this module exists. A limit built over rules
that fail either check saves cleanly, publishes cleanly, and then never fires.
Nothing in the product tells anyone. So eligibility is computed here, up front,
deterministically — and deliberately **not** left to the AI proposer, which
would otherwise invent plausible-looking `amount_fact` names that score zero
forever.

The two conditions, derived from the code above rather than assumed:

1. **The rule must be machine-executable.** `_evaluate_rule` short-circuits on
   `if not rule.machine_executable: return NOT_APPLICABLE` *before* reading
   scope, condition or exceptions. A non-executable rule can therefore never
   reach `SATISFIED`, so check (1) always skips it.

2. **The rule must declare at least one numeric `RequiredFact`.**
   `required_facts` is the rule's only published statement of which facts it
   consumes and what type each one is. Choosing an `amount_fact` outside that
   set is invention, and check (2) turns invention into a silent zero.

Both are necessary, neither is sufficient on its own, and both are properties
of the rule alone — which is what makes this a pure function rather than an
opinion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from policy_platform.contracts.policy import CanonicalRule

#: DMN input columns carry a `type` string that becomes `RequiredFact.data_type`
#: (see `formulation_mapping.derive_condition`). DMN itself names the numeric
#: type "number"; the synonyms are accepted defensively because the field is a
#: free-text string on the contract, and a rule that is genuinely numeric should
#: not be judged ineligible over spelling.
NUMERIC_DATA_TYPES = frozenset(
    {"number", "numeric", "integer", "int", "long", "float", "double", "decimal"}
)

#: Stable reason codes. The UI maps these to explanations; keeping them as codes
#: rather than prose means the wording can change in one place without the
#: backend and frontend disagreeing about what was actually wrong.
BLOCKER_NOT_MACHINE_EXECUTABLE = "not_machine_executable"
BLOCKER_NO_NUMERIC_FACT = "no_numeric_fact"


@dataclass(frozen=True)
class NumericFact:
    """A declared fact whose value the evaluator would actually sum."""

    name: str
    data_type: str


@dataclass(frozen=True)
class RuleEligibility:
    """Whether one rule can contribute to an aggregate limit, and why not."""

    rule_id: str
    title: str
    eligible: bool
    machine_executable: bool
    numeric_facts: list[NumericFact] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "eligible": self.eligible,
            "machine_executable": self.machine_executable,
            "numeric_facts": [{"name": f.name, "data_type": f.data_type} for f in self.numeric_facts],
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class EligibilityReport:
    """Eligibility across a whole rule set, plus the counts the UI needs."""

    rules: list[RuleEligibility]

    @property
    def eligible(self) -> list[RuleEligibility]:
        return [r for r in self.rules if r.eligible]

    @property
    def can_build_limit(self) -> bool:
        """An aggregate limit is a *combined* cap, so it needs two or more
        contributors. One eligible rule is already covered by that rule's own
        condition and needs no cross-rule machinery."""

        return len(self.eligible) >= 2

    def to_dict(self) -> dict:
        blocked = [r for r in self.rules if not r.eligible]
        return {
            "total_rules": len(self.rules),
            "eligible_count": len(self.eligible),
            "blocked_count": len(blocked),
            "can_build_limit": self.can_build_limit,
            "blocker_totals": {
                BLOCKER_NOT_MACHINE_EXECUTABLE: sum(
                    1 for r in blocked if BLOCKER_NOT_MACHINE_EXECUTABLE in r.blockers
                ),
                BLOCKER_NO_NUMERIC_FACT: sum(
                    1 for r in blocked if BLOCKER_NO_NUMERIC_FACT in r.blockers
                ),
            },
            "rules": [r.to_dict() for r in self.rules],
        }


def numeric_facts_for(rule: CanonicalRule) -> list[NumericFact]:
    """Declared facts whose value `_evaluate_aggregate_limits` could sum."""

    return [
        NumericFact(name=f.name, data_type=f.data_type)
        for f in rule.required_facts
        if (f.data_type or "").strip().lower() in NUMERIC_DATA_TYPES
    ]


def assess_rule(rule: CanonicalRule) -> RuleEligibility:
    """Deterministically decide whether `rule` can contribute to a cap.

    Every blocker that applies is reported, not just the first. A rule that is
    both non-executable and factless has two distinct problems, and telling the
    reviewer about one at a time would send them round the loop twice.
    """

    blockers: list[str] = []
    if not rule.machine_executable:
        blockers.append(BLOCKER_NOT_MACHINE_EXECUTABLE)

    facts = numeric_facts_for(rule)
    if not facts:
        blockers.append(BLOCKER_NO_NUMERIC_FACT)

    return RuleEligibility(
        rule_id=rule.rule_id,
        title=rule.title,
        eligible=not blockers,
        machine_executable=rule.machine_executable,
        numeric_facts=facts,
        blockers=blockers,
    )


def assess_rules(rules: list[CanonicalRule]) -> EligibilityReport:
    """Eligibility for a whole published version, in the rules' own order."""

    return EligibilityReport(rules=[assess_rule(r) for r in rules])
