"""What makes two quality runs comparable, derived rather than declared.

`quality_runs.methodology_version` exists so that a trend is only drawn
between runs the same suite produced: `QualityPage.tsx:475-481` looks for a
prior run to diff against and accepts one only when the version matches,
because "prompt/schema upgrades change what can be discovered, so they
establish a new baseline rather than masquerading as policy improvement or
regression".

That guard is right, and it was disarmed. The constant it reads was
hand-maintained at ``"2"`` while the detector suite changed enough to take
one unchanged 273-record set from 23 findings to 99. All seven recorded
runs on that set claim the same methodology, so the comparison the guard
was built to prevent is the one it permitted.

A hand-maintained constant drifts the moment someone adds a detector and
forgets, which is what happened. So the value is derived from the suite
itself, in two independent halves:

* the **inventory** -- which detectors ``_deterministic_findings``
  composes, read out of its own syntax tree. Complete for structural
  change: adding, removing or renaming a detector moves the value, and
  nobody has to remember anything.
* the **behaviour** -- what the suite reports about a fixed synthetic
  corpus, recorded as (category, severity, which records). This sees
  change *inside* a detector, which the inventory cannot: a threshold that
  moves or a severity that is reclassified changes what the probe reports
  while the inventory stays identical.

Each half covers the other's blind spot.

Neither half reads formatting. The inventory is taken from the AST, so a
reordered import, a reflowed call or an edited comment leaves the version
alone; the behaviour half sees findings, never the source that produced
them. Finding *messages* are excluded on purpose -- rewording a
recommendation is a copy edit, not a change of method -- while the record
ids a finding names are included, so a detector that starts flagging a
different set of records moves the version even if it flags the same
number of them.

Where this is still blind: a behavioural change inside a detector that the
probe corpus never exercises. That blindness is pinned rather than hoped
away -- `tests/unit/test_methodology_version_is_derived.py` asserts exactly
which categories the probe reaches, so extending the corpus is a visible
change and losing coverage fails.

The bias is deliberate and one-sided. Saying "different methodology" when
the suite is really unchanged costs a re-score, and
`scripts/rescore_baselines.py` does that on demand. Saying "same
methodology" when it is not is how an instrument change gets reported as a
quality improvement, which is the defect this exists to prevent.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import inspect
import json
import textwrap
from collections.abc import Callable, Sequence
from datetime import date

from policy_platform.contracts.conditions import (
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    ExtractionStatus,
)
from policy_platform.contracts.policy import (
    AmbiguityStatus,
    CanonicalRule,
    Effect,
    EffectType,
    PolicyAuthority,
    PolicyScope,
    RuleException,
    RuleFormulation,
    RuleType,
)

#: Bumped by hand when the *derivation* changes, so that values produced by
#: two different fingerprinting schemes can never collide. It is not the
#: identity of the suite -- the suffix is -- and leaving it alone does not
#: suppress a change the way leaving ``"2"`` alone did.
_GENERATION = "3"

#: 12 hex characters of SHA-256. The whole value has to fit
#: ``quality_runs.methodology_version``, which is ``varchar(20)``.
_DIGEST_CHARS = 12

_AUTHORITY = PolicyAuthority(level="corporate", owner="methodology-probe", rank=10)
_SCOPE = PolicyScope(
    jurisdictions=["*"], organizational_units=["*"], personas=["*"], processes=["*"]
)


def _probe_rule(
    rule_id: str,
    title: str,
    *,
    fact: str = "probe_fact",
    operator: ConditionOperator = ConditionOperator.EQUALS,
    value: object = True,
    rule_type: RuleType = RuleType.APPROVAL_REQUIREMENT,
    effect_type: EffectType = EffectType.ALLOW,
    **overrides: object,
) -> CanonicalRule:
    """One synthetic record. Never a copy of a real document.

    Dates are fixed in the past on purpose. A probe rule dated relative to
    today would make the fingerprint change by itself on some future
    morning, which would report an instrument change that never happened --
    the same false signal in the other direction.
    """
    return CanonicalRule(
        policy_set_id="methodology-probe",
        policy_version_id="probe",
        rule_id=rule_id,
        rule_revision=1,
        title=title,
        rule_type=rule_type,
        authority=_AUTHORITY,
        scope=_SCOPE,
        condition=FactComparisonCondition(fact=fact, operator=operator, value=value),
        effect=Effect(type=effect_type, action="probe_action"),
        effective_from=date(2020, 1, 1),
        **overrides,  # type: ignore[arg-type]
    )


def _probe_corpus() -> list[CanonicalRule]:
    """A fixed corpus shaped to trip detectors, not to resemble a policy."""
    return [
        # Same id twice: the identity check.
        _probe_rule("probe-dup", "Approval required for travel"),
        _probe_rule("probe-dup", "Approval required for travel"),
        # A record that says it cannot be decided as written.
        _probe_rule(
            "probe-blocking",
            "Reasonable notice must be given",
            ambiguity_status=AmbiguityStatus.BLOCKING,
        ),
        _probe_rule(
            "probe-nonblocking",
            "Notice should normally be given",
            ambiguity_status=AmbiguityStatus.NON_BLOCKING,
        ),
        # Past its own end date while still in the active set.
        _probe_rule(
            "probe-expired",
            "Interim allowance applies",
            effective_to=date(2021, 1, 1),
        ),
        # An exception measured against a fact the rule never declares.
        _probe_rule(
            "probe-orphan-exception",
            "Deduction applies on lateness",
            exceptions=[
                RuleException(
                    exception_id="probe-exc",
                    description="unless previously excused",
                    condition=FactComparisonCondition(
                        fact="fact_the_rule_never_declares",
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                )
            ],
        ),
        # Two records carrying one decision, and a qualifier standing alone
        # as though it were one.
        _probe_rule("probe-split-a", "Deduction is 5% on first occurrence"),
        _probe_rule("probe-split-b", "Deduction is 25% on second occurrence"),
        _probe_rule("probe-qualifier", "Where operationally practicable"),
        # A predicate that decides nothing.
        _probe_rule(
            "probe-degenerate",
            "Applies",
            fact="probe_fact",
            operator=ConditionOperator.EXISTS,
            value=None,
        ),
        # A definition, which names nothing to measure.
        _probe_rule(
            "probe-definition",
            "Working day means a day other than a weekend",
            rule_type=RuleType.ELIGIBILITY,
            effect_type=EffectType.INFORMATIONAL,
        ),
        # Formed logic carrying attributes its own source sentence never
        # states. Reaching the faithfulness detector matters more than the
        # others: it is the largest contributor to the finding count, and its
        # severity mapping is the kind of change the inventory half cannot
        # see.
        _probe_rule(
            "probe-unfaithful",
            "Managers approve travel requests",
            formulation=RuleFormulation(
                source_index=0,
                canonical=CanonicalPolicy(
                    source_text="Managers approve travel requests.",
                    extraction_status=ExtractionStatus.COMPLETE,
                    rule=CanonicalPolicyRule(
                        rule_type=CanonicalRuleType.OBLIGATION,
                        subject="Managers",
                        predicate="approve",
                        object="travel requests",
                        # Neither of these appears in the sentence above.
                        threshold="500 dinars",
                        temporal_constraint="within 30 days",
                    ),
                ),
            ),
        ),
        # Formed logic with the decomposition incomplete.
        _probe_rule(
            "probe-malformed",
            "Employees shall comply",
            formulation=RuleFormulation(
                source_index=1,
                canonical=CanonicalPolicy(
                    source_text="Employees shall comply.",
                    extraction_status=ExtractionStatus.INCOMPLETE,
                    rule=CanonicalPolicyRule(
                        rule_type=CanonicalRuleType.OBLIGATION,
                        subject="Employees",
                    ),
                ),
            ),
        ),
    ]


def composed_detectors(suite: Callable[..., object]) -> tuple[str, ...]:
    """The detectors `suite` composes, read from its own syntax tree.

    Structural rather than remembered: this is derived from the calls the
    function actually makes, so a detector cannot be added to the suite
    without the inventory noticing. Reading the AST rather than the text
    means comments, blank lines and wrapping do not register as change.

    Every named call is collected, not only the arguments of
    ``findings.extend(...)``. A narrower rule was tried and was wrong: a
    detector invoked inside a comprehension, or through a local variable,
    reads as a different node type and vanished from the inventory. Builtins
    are excluded because they are stable and would only add noise.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(suite)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if not hasattr(builtins, name):
                names.add(name)
    return tuple(sorted(names))


def observed_shape(
    suite: Callable[[list[CanonicalRule]], Sequence[dict]],
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """What `suite` reports about the probe corpus.

    Category, severity and the records named -- never the wording. A
    reworded recommendation is a copy edit; a detector that changes which
    records it names has changed method.
    """
    findings = suite(_probe_corpus())
    return tuple(
        sorted(
            (
                str(f.get("category", "")),
                str(f.get("severity", "")),
                tuple(sorted(str(r) for r in f.get("affected_rule_ids", []))),
            )
            for f in findings
        )
    )


def derive_methodology_version(
    suite: Callable[[list[CanonicalRule]], Sequence[dict]],
) -> str:
    """The identity of the detector suite, as ``3-<12 hex>``."""
    payload = json.dumps(
        {
            "generation": _GENERATION,
            "detectors": composed_detectors(suite),
            "shape": observed_shape(suite),
        },
        sort_keys=True,
        default=list,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
    return f"{_GENERATION}-{digest}"
