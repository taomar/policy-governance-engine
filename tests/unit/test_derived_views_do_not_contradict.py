"""No derived view may contradict the record it is attached to.

Several fields are derived on read rather than stored: the readiness
assessment, the XACML projection, the attribute table, the fact model, the
evaluation mode and the condition provenance. The reasoning is sound — a stored
copy goes stale the moment a derivation is corrected, and re-deriving means one
fix reaches every record at once.

It has a failure mode, and it is not obvious. A derivation reading only the
*formulation* answers "what would this sentence produce now", which is a
different question from "why does this record look like this". The two come
apart whenever the code changes: records written before the change carry one
answer in their stored fields and get another from the derivation, and the
served JSON then contradicts itself.

That is not hypothetical. Every check below was written after finding the
contradiction in served output:

* a rule carrying a fully compiled comparison reported
  `conditions_not_projected`, telling a reviewer to supply a mapping that was
  not missing;
* correcting that made two rules claim `derived_from_stated_bound` over an
  empty `all: []` tree, because their sentences state a compilable bound and
  their stored trees predate the compiler;
* nineteen records carried `compilation_status: executable` beside
  `machine_executable: false`, because "executable" meant one thing about the
  projection and another about the rule;
* `fact_model` reported a type of `null` for a name that `required_facts`
  reported as `number`, because extraction reconciled the two and the read
  paths did not.

Run over the real corpus. Constructed records would agree by construction,
which is exactly the assumption that kept failing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_platform.api.routers.candidate_rules import _with_decision_readiness
from policy_platform.contracts.policy import CanonicalRule, EvaluationMode
from policy_platform.contracts.xacml_projection import RuleEffect

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "ad103_rules.json"

#: Provenance codes that assert a condition was compiled for this record.
_CLAIMS_A_DERIVATION = {"derived", "derived_from_stated_bound"}


@pytest.fixture(scope="module")
def corpus() -> list[CanonicalRule]:
    """Real records, with their derived views recomputed here and now.

    The corpus supplies the stored half — the condition, the effect, the
    required facts, the formulation — and the read path supplies the derived
    half, by running the same function the API runs.

    Reading the derived fields straight out of the file instead looks
    equivalent and is not: the file is a snapshot, so breaking the derivation
    changes nothing a snapshot-reading test can see. Checked by mutation, and
    every one of these checks survived that version — the code was broken on
    purpose five different ways and the suite passed each time.
    """

    stored = [
        CanonicalRule.model_validate(payload)
        for payload in json.loads(CORPUS.read_text(encoding="utf-8"))
    ]
    return [_with_decision_readiness(rule) for rule in stored]


def test_the_corpus_carries_the_views_these_checks_read(corpus):
    """Guards every check below, and is the reason this file was rewritten.

    The corpus had been captured before the derived views existed, so it
    carried none of them, and five of the checks here iterated over nothing and
    passed. A guard that cannot fail is worse than no guard, because it is
    counted as coverage. `scripts/capture_corpus.py` now refuses to write a
    corpus missing any of them.
    """

    # Floor, not a pin. One extraction of the reference document yields
    # 37 policies; the number moves when the document or the extractor
    # does, and the freeze snapshot beside this is what pins it exactly.
    # What matters here is that the corpus is large enough, and carries
    # the derived views, for these checks to mean something.
    assert len(corpus) >= 30
    assert sum(1 for rule in corpus if rule.xacml_view) >= 30
    assert sum(1 for rule in corpus if rule.fact_model) >= 30
    assert sum(1 for rule in corpus if rule.condition_provenance) >= 30
    # The pair that only a compiled rule has. Without at least one, the checks
    # comparing published facts against required ones prove nothing.
    assert sum(1 for rule in corpus if rule.required_facts) >= 1
    assert sum(1 for rule in corpus if not _is_vacuous(rule)) >= 1


def _is_vacuous(rule: CanonicalRule) -> bool:
    condition = rule.condition
    return getattr(condition, "type", None) == "all" and not getattr(condition, "all", None)


def test_provenance_never_claims_a_derivation_the_tree_does_not_have(corpus):
    """The contradiction that sends a reviewer to fix nothing.

    A record saying its condition was derived, over an empty tree, is telling a
    reader two incompatible things about the same field.
    """

    contradicting = [
        (rule.rule_id, rule.condition_provenance.code)
        for rule in corpus
        if rule.condition_provenance
        and rule.condition_provenance.code in _CLAIMS_A_DERIVATION
        and _is_vacuous(rule)
    ]

    assert not contradicting, f"derivation claimed over an empty tree: {contradicting}"


def test_a_compiled_tree_is_never_reported_as_unprojected(corpus):
    """The same contradiction from the other side.

    A record carrying a real comparison must not report that its conditions
    could not be projected — that reads as a gap where there is none.
    """

    contradicting = [
        (rule.rule_id, rule.condition_provenance.code)
        for rule in corpus
        if rule.condition_provenance
        and not _is_vacuous(rule)
        and rule.condition_provenance.code not in _CLAIMS_A_DERIVATION
    ]

    assert not contradicting, f"compiled tree reported as unprojected: {contradicting}"


def test_the_published_facts_agree_with_the_facts_evaluation_requires(corpus):
    """Two fields, one name, one answer.

    `fact_model` is what a consumer reads to know what to supply;
    `required_facts` is what evaluation checks for. A type in one and a
    different type in the other means a caller following the contract still
    gets it wrong.
    """

    disagreeing: list[tuple[str, str, str | None, str | None]] = []
    for rule in corpus:
        published = {fact.name: fact.data_type for fact in rule.fact_model}
        for required in rule.required_facts:
            if required.name in published and published[required.name] != required.data_type:
                disagreeing.append(
                    (rule.rule_id, required.name, published[required.name], required.data_type)
                )

    assert not disagreeing, f"fact_model and required_facts disagree: {disagreeing}"


def test_every_required_fact_is_published(corpus):
    """A caller reading `fact_model` must find every name evaluation needs."""

    missing = [
        (rule.rule_id, required.name)
        for rule in corpus
        for required in rule.required_facts
        if required.name not in {fact.name for fact in rule.fact_model}
    ]

    assert not missing, f"required facts absent from fact_model: {missing}"


def test_the_routing_field_agrees_with_the_executable_flag(corpus):
    """`evaluation_mode` is what a consumer routes on; both must say one thing."""

    disagreeing = [
        (rule.rule_id, rule.evaluation_mode.value, rule.machine_executable)
        for rule in corpus
        if (rule.evaluation_mode is EvaluationMode.DETERMINISTIC) != rule.machine_executable
    ]

    assert not disagreeing, f"evaluation_mode contradicts machine_executable: {disagreeing}"


def _projection(rule: CanonicalRule) -> dict | None:
    """The XACML projection as served, whatever shape the contract types it as.

    `xacml_view` is loosely typed on `CanonicalRule`, so a record loaded from
    the corpus carries plain dictionaries. Reading it as a dictionary keeps the
    check honest about what a consumer actually receives.
    """

    view = rule.xacml_view
    if view is None:
        return None
    if not isinstance(view, dict):
        view = view.model_dump(mode="json")
    projection = view.get("xacml_projection")
    return projection if isinstance(projection, dict) else None


def test_the_projection_restates_the_record_rather_than_re_deriving_it(corpus):
    """A constructed disagreement, because a clean corpus contains none.

    The projection is a restatement of the record's effect in another
    vocabulary, not a second opinion about it. The two come apart whenever the
    derivation is corrected: records stored before the fix keep their effect
    while the projection reports the new reading, and one record then answers
    "does this forbid?" two ways.

    The corpus that first showed this held one such record — an obligation
    stored before negation-in-the-predicate was read, projecting as Deny after.
    Re-extracting removed it, and with it the only witness: a corpus-driven
    version of this check passed with the guard broken. Constructed here so it
    holds whatever the data happens to contain.
    """

    from policy_platform.contracts.formulation import CanonicalPolicy, CanonicalPolicyRule
    from policy_platform.contracts.formulation import CanonicalRuleType
    from policy_platform.infrastructure.projection.xacml_projection import build_xacml_view

    # A sentence the projection reads as forbidding, on its own.
    forbidding = CanonicalPolicy(
        source_text="The increase shall not exceed the stated limit.",
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.CONDITIONAL_OUTCOME,
            subject="the increase",
            modality="shall not",
            predicate="exceed",
            object="the stated limit",
        ),
    )

    derived = build_xacml_view(forbidding)
    assert derived.xacml_projection.effect is RuleEffect.DENY

    # The same sentence, on a record whose stored effect says otherwise. The
    # record wins: it is what the evaluator acts on and what the badge shows.
    restated = build_xacml_view(forbidding, record_effect=RuleEffect.PERMIT)
    assert restated.xacml_projection.effect is RuleEffect.PERMIT


def test_the_projection_never_permits_what_the_record_denies(corpus):
    """Two fields answering "does this forbid?" differently is the worst case.

    The projection is a restatement of the record's effect in another
    vocabulary. Where it disagrees, one of them is telling a reader that
    conduct the policy forbids is allowed.
    """

    disagreeing: list[tuple[str, str, str]] = []
    for rule in corpus:
        projection = _projection(rule)
        if not projection or not projection.get("effect"):
            continue
        record_forbids = rule.effect.type.value == "deny"
        projection_forbids = projection["effect"] == RuleEffect.DENY.value
        if record_forbids != projection_forbids:
            disagreeing.append((rule.rule_id, rule.effect.type.value, projection["effect"]))

    assert not disagreeing, f"projection and effect disagree about forbidding: {disagreeing}"


def test_no_served_field_uses_executable_in_two_senses(corpus):
    """`compilation_status` asked whether the *projection* was well-formed.

    A rule with no conditions projects to a valid unconditional XACML rule
    whether or not the platform can evaluate it, so nineteen records carried
    `compilation_status: executable` beside `machine_executable: false`. It is
    still computed, for the tests that read it; it is no longer served, because
    one record cannot use one word for two claims.
    """

    projections = [_projection(rule) for rule in corpus]
    assert any(projections), "no record carried a projection — the check would prove nothing"

    for projection in projections:
        if not projection:
            continue
        assert "compilation_status" not in projection
        assert "effect_basis" not in projection
