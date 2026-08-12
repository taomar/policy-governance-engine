"""Every policy answers, from its own JSON, what a judge needs to decide it.

Most policy text is not a decision table and never will be, so the reading path
is the main path rather than a fallback. A consumer hands one of these records
to a judge together with the facts of a case; the record has to be sufficient
on its own.

Six questions, and what answers each:

1. *What does the document say?* — the source sentence, verbatim.
2. *What does the rule require?* — a stated condition, or the operative
   content carried by the triple: a predicate with an object or a threshold, a
   trigger, or a temporal constraint.
3. *What must be established about a case?* — the facts the policy names.
4. *What follows?* — the effect.
5. *Which path?* — `deterministic` or `ai_ready`.
6. *Where did this come from?* — evidence pointing back at the document.

Question 2 is the one that keeps being got wrong, and always in the same
direction: by looking only for a field called `condition`. A rule states its
operative content wherever the sentence puts it. "shall not exceed 10% of the
base" carries it in predicate and threshold, "begins on the first working day"
in a temporal constraint, and "provided upon promotion" in a trigger. Each is
complete; a check that reads one field reports the other two as gaps.

Run over the real corpus rather than constructed records, because the whole
point is whether actual extraction output is sufficient.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.policy_facts import facts_for

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "ad103_rules.json"


@pytest.fixture(scope="module")
def policies() -> list[CanonicalRule]:
    return [
        CanonicalRule.model_validate(payload)
        for payload in json.loads(CORPUS.read_text(encoding="utf-8"))
    ]


def _text(value: str | None) -> str:
    return (value or "").strip()


def _states_what_it_requires(rule: CanonicalRule) -> bool:
    """Whether the record carries the rule's operative content, anywhere.

    Deliberately generous about *where*, and strict about *whether*. The
    sentence decides which slot carries it, and a record is sufficient if any
    of them does.
    """

    canonical = rule.formulation.canonical if rule.formulation else None
    core = canonical.rule if canonical else None
    if core is None:
        return False
    if _text(core.condition) or _text(core.prerequisite) or _text(core.constraint):
        return True
    if _text(core.trigger) or _text(core.temporal_constraint) or _text(core.deadline):
        return True
    return bool(_text(core.predicate) and (_text(core.object) or _text(core.threshold)))


def test_the_corpus_is_the_real_extraction(policies):
    """Guards the rest: sufficiency over a stub would prove nothing."""

    assert len(policies) >= 30
    assert all(rule.formulation and rule.formulation.canonical for rule in policies)


def test_every_policy_carries_the_sentence_it_came_from(policies):
    """A judge reads the document's words, not our paraphrase of them."""

    without = [
        rule.rule_id
        for rule in policies
        if not _text(rule.formulation.canonical.source_text)
    ]

    assert not without, f"policies with no source text: {without}"


def test_every_policy_states_what_it_requires(policies):
    """The operative content is present, wherever the sentence put it."""

    without = [
        (rule.rule_id, (rule.title or "")[:60])
        for rule in policies
        if not _states_what_it_requires(rule)
    ]

    assert not without, f"policies carrying no operative content: {without}"


def test_every_policy_names_what_must_be_established(policies):
    """The things a case is measured against, named by the policy itself."""

    without = [
        rule.rule_id
        for rule in policies
        if not facts_for(rule.formulation.canonical.rule)
    ]

    assert not without, f"policies naming nothing to establish: {without}"


def test_every_policy_states_an_outcome(policies):
    """What follows when it applies."""

    without = [rule.rule_id for rule in policies if not (rule.effect and rule.effect.action)]

    assert not without, f"policies with no outcome: {without}"


def test_every_policy_says_how_it_should_be_decided(policies):
    """The routing field. A consumer reads this before anything else."""

    assert all(rule.evaluation_mode for rule in policies)


def test_every_policy_is_traceable_to_the_document(policies):
    """A judge that cannot cite the source cannot be checked."""

    without = [rule.rule_id for rule in policies if not rule.evidence]

    assert not without, f"policies with no evidence: {without}"


def test_a_delegated_decision_names_the_party_that_decides(policies):
    """The one question a delegated rule most needs answered.

    A phrase can be both the grammatical subject and the deciding authority —
    "<body> decides on <thing>" — and an earlier single-valued role kept the
    first and dropped the second, so the rule that answers this question
    answered it nowhere.
    """

    missing: list[tuple[str, str]] = []
    for rule in policies:
        core = rule.formulation.canonical.rule
        if core is None or not _text(core.assigner):
            continue
        facts = facts_for(core)
        if not any("authority" in fact.roles for fact in facts):
            missing.append((rule.rule_id, _text(core.assigner)))

    assert not missing, f"delegated rules naming no authority: {missing}"
