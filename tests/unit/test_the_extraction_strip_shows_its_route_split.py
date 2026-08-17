"""The live extraction readout carries the route each rule was drafted into.

Every rule is assigned a route as it is drafted: `deterministic`, where the
source states a test the engine can compute over named facts, or `ai_ready`,
where the source states its test in words and a judge reads the rule against a
case. The rest of the product leads with that split everywhere — the register,
the review cards, the quality checks — but the in-flight progress readout showed
none of it, though the split is settled rule by rule as the run proceeds.

These tests pin two things and keep them honest against Constraint 1 (no observed
count as a literal — every expectation here is a relationship computed from the
rules the test itself built, never a number copied from a corpus):

1. A batch drafting rules of both routes reports both counters, and each counter
   equals the number of that route in the batch. The rules of the reading route
   are produced by the real mapping the run uses, so this is the value the
   mapping assigns, read back — not a number the test invented and handed to the
   dataclass, which would prove only that integers add up (§4.1).

2. A rule whose mode is absent, or is a route this code does not name, is counted
   by neither. The two counters are therefore not assumed to sum to the drafted
   total: a route added to the model later, or a record that reached the tally
   with no mode, stays visible as the difference between the counters and the
   drafted count rather than being folded into one side.

The wiring at the drafting site — that the tally is computed over the rules just
drafted and its results are the values handed to `advance` — is pinned
structurally, in the same idiom `test_coverage_shortfall_is_visible.py` uses for
the loop beside it, so a regression that stops feeding the counters fails here
rather than only in a live run.
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    PolicyFormulation,
)
from policy_platform.contracts.policy import (
    CanonicalRule,
    EvaluationMode,
    RequiredFact,
)
from policy_platform.infrastructure.extraction import extraction_progress
from policy_platform.infrastructure.extraction.ai_extraction import _route_tally
from policy_platform.infrastructure.extraction.formulation_mapping import (
    formulation_to_candidate_rules,
)

_EXTRACTION = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "policy_platform"
    / "infrastructure"
    / "extraction"
    / "ai_extraction.py"
)


# --------------------------------------------------------------------------
# Building rules the way the run does
# --------------------------------------------------------------------------


def _reading_route_rules() -> list[CanonicalRule]:
    """Rules of the judged route, produced by the real mapping the run calls.

    Two distinct obligations over different subjects, so the compound-predicate
    pass has nothing to merge. Plain obligations with no computable test come out
    of the mapping on the reading route; the caller asserts that rather than
    assuming it, because the point is to read what the mapping produced.
    """

    policies = [
        CanonicalPolicy(
            source_text="Employees must submit the form.",
            rule=CanonicalPolicyRule(
                rule_type="obligation",
                subject="employees",
                modality="must",
                predicate="submit",
                object="the form",
            ),
        ),
        CanonicalPolicy(
            source_text="Managers must approve the request.",
            rule=CanonicalPolicyRule(
                rule_type="obligation",
                subject="managers",
                modality="must",
                predicate="approve",
                object="the request",
            ),
        ),
    ]
    rules, _ = formulation_to_candidate_rules(
        PolicyFormulation(canonical_policies=policies),
        policy_set_id="test-set",
        extraction_run_id="test-run",
        deployment_name="test",
        prompt_version="test",
        parser_version="test",
    )
    return rules


def _computed_route_rule() -> CanonicalRule:
    """A rule of the computed route, built exactly as the mapping emits one.

    The mode is set at construction from the rule's own condition over named
    facts, which is what `evaluation_mode_from` decides; the tally reads that
    field back rather than deciding it again.
    """

    return CanonicalRule(
        policy_set_id="test-set",
        policy_version_id="v",
        rule_id="R-DET",
        rule_revision=1,
        title="A computed rule",
        rule_type="obligation",
        authority={"level": "ai_drafted", "owner": "x", "rank": 0},
        scope={},
        condition=AllCondition(
            all=[
                FactComparisonCondition(
                    fact="a.b", operator=ConditionOperator.GREATER_THAN, value=1
                )
            ]
        ),
        effect={"type": "require_action", "action": "do the thing"},
        required_facts=[RequiredFact(name="a.b", data_type="number")],
        effective_from="2026-01-01",
        evaluation_mode=EvaluationMode.DETERMINISTIC,
    )


def _run_the_drafting_advance(key: str, rules: list) -> dict:
    """Drive the drafting site's own sequence: tally the batch, then advance.

    This is the exact pair of statements the run executes at the drafting point.
    It reads `_route_tally` — the function the site calls — so a green here is
    the mapping's assigned modes travelling into the counters, not a hand-picked
    integer proving the dataclass adds.
    """

    deterministic, ai_ready = _route_tally(rules)
    extraction_progress.start(key, total_clauses=len(rules), total_batches=1, total_pages=1)
    extraction_progress.advance(
        key,
        drafted=len(rules),
        deterministic=deterministic,
        ai_ready=ai_ready,
    )
    record = extraction_progress.get(key)
    assert record is not None
    return record


def teardown_function() -> None:
    extraction_progress.clear()


# --------------------------------------------------------------------------
# Both routes are reported
# --------------------------------------------------------------------------


def test_a_batch_of_both_routes_reports_each_counter_from_the_rules_modes() -> None:
    reading = _reading_route_rules()
    assert reading, "the mapping returned no rules for the reading-route policies"
    assert all(rule.evaluation_mode is EvaluationMode.AI_READY for rule in reading), (
        "the reading-route fixture no longer comes out on the judged route, so this "
        f"test is not exercising a mix: {[r.evaluation_mode for r in reading]}"
    )

    computed = _computed_route_rule()
    assert computed.evaluation_mode is EvaluationMode.DETERMINISTIC

    rules = [*reading, computed]
    record = _run_the_drafting_advance("doc-both", rules)

    expected_deterministic = sum(
        1 for rule in rules if rule.evaluation_mode is EvaluationMode.DETERMINISTIC
    )
    expected_ai_ready = sum(
        1 for rule in rules if rule.evaluation_mode is EvaluationMode.AI_READY
    )

    assert record["rules_deterministic"] == expected_deterministic
    assert record["rules_ai_ready"] == expected_ai_ready
    # Both routes are genuinely present in this batch, so neither counter may sit
    # at zero — a reading that reported one route and dropped the other would
    # pass a weaker assertion.
    assert record["rules_deterministic"] > 0
    assert record["rules_ai_ready"] > 0
    # Every rule here carries a mode the tally names, so for this batch the two
    # do sum to the drafted total. The next test is the case where they must not.
    assert record["rules_deterministic"] + record["rules_ai_ready"] == record["rules_drafted"]


def test_the_counters_accumulate_across_batches_like_the_drafted_total() -> None:
    """The run advances once per batch, so the route counts are cumulative."""

    key = "doc-two-batches"
    extraction_progress.start(key, total_clauses=10, total_batches=2, total_pages=2)

    first = [_computed_route_rule(), *_reading_route_rules()]
    d1, a1 = _route_tally(first)
    extraction_progress.advance(key, drafted=len(first), deterministic=d1, ai_ready=a1)

    second = _reading_route_rules()
    d2, a2 = _route_tally(second)
    extraction_progress.advance(key, drafted=len(second), deterministic=d2, ai_ready=a2)

    record = extraction_progress.get(key)
    assert record["rules_deterministic"] == d1 + d2
    assert record["rules_ai_ready"] == a1 + a2


# --------------------------------------------------------------------------
# A mode the tally does not name is in neither counter
# --------------------------------------------------------------------------


def test_a_rule_whose_mode_is_neither_value_is_counted_by_neither() -> None:
    recognised = [_computed_route_rule(), *_reading_route_rules()]

    # One rule with no mode at all, and one carrying a route this code does not
    # name — a value the model might grow later. Both must land outside both
    # counters. Stand-ins rather than CanonicalRule instances precisely because
    # the contract's field cannot hold either value; the tally reads the
    # attribute and must not assume it is always one of the two it knows.
    unnamed = [
        types.SimpleNamespace(evaluation_mode=None),
        types.SimpleNamespace(evaluation_mode="appellate_review"),
    ]

    rules = [*recognised, *unnamed]
    record = _run_the_drafting_advance("doc-neither", rules)

    recognised_total = record["rules_deterministic"] + record["rules_ai_ready"]
    # The unnamed rules are absorbed by neither side, so the counters fall short
    # of the drafted total by exactly the number of them. That gap is the whole
    # point: it stays visible instead of being charged to one route. The
    # expected shortfall is derived from the batch the test built, never a
    # written-in number.
    assert recognised_total == len(recognised)
    assert recognised_total < record["rules_drafted"]
    assert record["rules_drafted"] - recognised_total == len(unnamed)


def test_an_empty_batch_leaves_both_counters_at_zero_without_error() -> None:
    record = _run_the_drafting_advance("doc-empty", [])
    assert record["rules_deterministic"] == 0
    assert record["rules_ai_ready"] == 0
    assert record["rules_drafted"] == 0


# --------------------------------------------------------------------------
# The drafting site actually feeds the tally into the readout
# --------------------------------------------------------------------------


def _module_tree() -> ast.Module:
    tree = ast.parse(_EXTRACTION.read_text(encoding="utf-8"))
    assert any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)
    ), "parsed the extraction module but found no functions in it"
    return tree


def _drafting_advance_call(tree: ast.Module) -> ast.Call:
    """The `extraction_progress.advance(...)` that reports a drafted batch.

    Identified by its `drafted=` keyword rather than by position, so the guard
    keeps pointing at the drafting site if the surrounding code moves.
    """

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "advance"
            and any(kw.arg == "drafted" for kw in node.keywords)
        ):
            return node
    raise AssertionError(
        "no extraction_progress.advance(..., drafted=...) call found. Either the drafting "
        "site moved or its reporting changed; this guard must not pass pointed at nothing."
    )


def test_the_drafting_site_reports_both_route_counters() -> None:
    call = _drafting_advance_call(_module_tree())
    passed = {kw.arg for kw in call.keywords}
    assert {"deterministic", "ai_ready"} <= passed, (
        "the drafting advance does not report the route split it just drafted; it passes "
        f"only {sorted(a for a in passed if a)}."
    )


def test_the_drafting_site_feeds_the_tally_rather_than_a_bare_number() -> None:
    """§4.1: the counters must be fed by a tally over the batch, not a constant.

    The values handed to `deterministic=`/`ai_ready=` must trace back to names
    that `_route_tally` produced from the drafted `rules`. A literal, or a name
    built some other way, would report a number nothing measured.
    """

    tree = _module_tree()

    tally_outputs: set[str] = set()
    tally_reads_rules = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_route_tally"
        ):
            if any(isinstance(arg, ast.Name) and arg.id == "rules" for arg in value.args):
                tally_reads_rules = True
            target = node.targets[0]
            if isinstance(target, ast.Tuple):
                tally_outputs |= {
                    element.id for element in target.elts if isinstance(element, ast.Name)
                }
            elif isinstance(target, ast.Name):
                tally_outputs.add(target.id)

    assert tally_reads_rules, (
        "_route_tally is never called over the drafted `rules`, so whatever feeds the "
        "counters was not measured from the batch."
    )

    call = _drafting_advance_call(tree)
    for name in ("deterministic", "ai_ready"):
        argument = next((kw.value for kw in call.keywords if kw.arg == name), None)
        assert isinstance(argument, ast.Name) and argument.id in tally_outputs, (
            f"the {name}= value handed to advance is not one of the tally's outputs "
            f"{sorted(tally_outputs)}; it is fed by something other than the batch's rules."
        )


def test_the_tally_reads_the_mode_and_does_not_recompute_it() -> None:
    """The counters read `evaluation_mode`; they must not re-derive it.

    `contracts/policy.py` keeps the mode derived-not-stored so a second copy
    cannot disagree with the condition it describes. A tally that called
    `evaluation_mode_from`/`evaluation_mode_for` would be making that second
    copy, on the drafting hot path, for a cosmetic count.
    """

    tree = _module_tree()
    tally = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_route_tally"
        ),
        None,
    )
    assert tally is not None, "the route tally helper is gone; the counters have no source"

    reads_mode = any(
        isinstance(node, ast.Attribute) and node.attr == "evaluation_mode"
        or (
            isinstance(node, ast.Constant)
            and node.value == "evaluation_mode"
        )
        for node in ast.walk(tally)
    )
    assert reads_mode, "the tally never reads `evaluation_mode`, so it is not reading the route"

    recompute = {
        node.func.id
        for node in ast.walk(tally)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"evaluation_mode_from", "evaluation_mode_for"}
    }
    assert not recompute, (
        f"the tally recomputes the mode via {sorted(recompute)} instead of reading the "
        "value the mapping already assigned."
    )
