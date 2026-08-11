"""The status inventory, frozen before the revamp changes it.

This is a characterization test, not a correctness test. It asserts nothing
about whether today's verdicts are *right* — several of them are demonstrably
confusing, which is why the revamp exists. It asserts only that they do not
move without someone noticing.

That distinction matters here more than usual. This session produced five
validators that were structurally incapable of failing, each of which reported
success over a corpus containing the exact defect it was written to catch. A
revamp that consolidates seven status representations into fewer is precisely
the kind of change that can silently flip a rule from "a human must look at
this" to "this is fine", and no unit test of an individual function would
catch it. This one compares the whole corpus, rule by rule.

The corpus is the real AD-103 extraction: 44 rules, stored payloads,
unmodified. Derivation runs through `_with_decision_readiness`, the same
function the API read path calls, so the test cannot drift from what a
reviewer actually receives.

**When a verdict change is intended**, regenerate with
`scripts/freeze_status_inventory.py` and review the diff. Regenerating to make
a failure go away discards the only record of what the system said before.
"""
from __future__ import annotations

import json

import pytest

from tests.unit.status_inventory import build_snapshot, load_corpus, load_snapshot, status_for


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


@pytest.fixture(scope="module")
def frozen():
    return load_snapshot()


@pytest.fixture(scope="module")
def live(corpus):
    return build_snapshot(corpus)


# --------------------------------------------------------------------------
# The corpus itself
# --------------------------------------------------------------------------


def test_the_corpus_is_the_real_extraction(corpus):
    """Guards every assertion below: they are meaningless over a stub."""

    assert len(corpus) == 44
    # Real AD-103 content, not synthesised.
    titles = " ".join(rule.title or "" for rule in corpus).lower()
    assert "basic salary" in titles
    assert any(rule.formulation is not None for rule in corpus)


def test_every_rule_still_parses_as_a_canonical_rule(corpus):
    """A contract change that breaks stored payloads must fail loudly here.

    These are persisted as JSONB, so a field removed from the model without a
    migration would surface first as a validation error over real data.
    """

    assert all(rule.rule_id for rule in corpus)


# --------------------------------------------------------------------------
# Per-rule verdicts
# --------------------------------------------------------------------------


def test_no_rule_changed_its_verdict(corpus, frozen):
    """The whole point. Reports every rule that moved, not just the first."""

    frozen_by_id = {entry["rule_id"]: entry for entry in frozen["rules"]}
    moved: list[str] = []

    for rule in corpus:
        current = status_for(rule)
        before = frozen_by_id.get(current["rule_id"])
        assert before is not None, f"rule missing from snapshot: {current['rule_id']}"
        for field, was in before.items():
            now = current[field]
            if now != was:
                moved.append(
                    f"{current['rule_id']} ({(current['title'] or '')[:44]!r})\n"
                    f"      {field}: {was!r} -> {now!r}"
                )

    assert not moved, "status verdicts changed:\n    " + "\n    ".join(moved)


def test_the_snapshot_covers_every_rule(corpus, frozen):
    """A rule dropped from the corpus must not quietly shrink the assertion."""

    assert {rule.rule_id for rule in corpus} == {e["rule_id"] for e in frozen["rules"]}


# --------------------------------------------------------------------------
# The headline figures the revamp is measured against
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("measure", "expected"),
    [
        ("rules", 44),
        ("machine_executable", 0),
        ("vacuous_conditions", 44),
        ("naming_an_authority", 10),
        ("rules_with_requirements", 19),
        ("requirement_phrases", 21),
        ("requirement_phrases_bundling_several", 10),
        ("inherited_from_parent_clause", 11),
        ("stored_ambiguity_differs_from_derived", 0),
        ("three_flags_disagree", 21),
    ],
)
def test_headline_totals_are_unchanged(live, measure, expected):
    """Pinned individually so a failure names which measure moved.

    These are the figures the revamp plan quotes. A phase that changes one
    should say so; one that changes it by accident should fail here.
    """

    assert live["totals"][measure] == expected


def test_stored_and_derived_ambiguity_still_agree(live):
    """`ambiguity_status` is persisted, so it can go stale.

    `decision_readiness` is derived on read precisely so a corrected
    assessment reaches rules extracted before the correction.
    `ambiguity_status` has no such protection: changing `_ambiguity_for`
    updates only rules extracted afterwards. They agree today, and this fails
    the moment they stop — which is the signal that a re-extraction, or a move
    to derive-on-read, is owed.
    """

    assert live["totals"]["stored_ambiguity_differs_from_derived"] == 0


def test_a_quarter_of_the_corpus_inherits_its_requirements(live):
    """11 of 44 rules carry a requirement their own sentence never states.

    Recorded because it sizes a decision R2 cannot avoid: a dependency node
    built from an inherited requirement must carry the parent's span, not the
    child's, or the node will cite text that does not contain it.
    """

    assert live["totals"]["inherited_from_parent_clause"] == 11


def test_the_contradiction_the_revamp_exists_to_resolve(live):
    """21 of 44 rules report three different answers about themselves.

    Recorded as its own test because it is the problem statement. When a later
    phase resolves it this test *must* fail — at which point the expectation
    moves to zero and the failure is the evidence that it worked.
    """

    assert live["totals"]["three_flags_disagree"] == 21
    assert live["totals"]["rules"] == 44


# --------------------------------------------------------------------------
# What must never regress, whatever else changes
# --------------------------------------------------------------------------


def test_every_rule_carries_a_provenance_code(corpus):
    """An empty tree must always say why it is empty.

    This is the invariant that keeps "genuinely unconditional" separable from
    "conditions we failed to encode". A rule losing its code would put those
    back in the same bucket, which is how a narrow permission comes to read as
    an open one.
    """

    missing = [
        status["rule_id"]
        for status in (status_for(rule) for rule in corpus)
        if status["condition_is_vacuous"] and not status["condition_provenance_code"]
    ]

    assert not missing, f"vacuous rules with no provenance code: {missing}"


def test_no_rule_claims_executability_without_a_condition(corpus):
    """The pairing `evaluator/engine.py` depends on.

    A rule that is `machine_executable` with a vacuous condition would be
    claiming to decide something while carrying no test.
    """

    liars = [
        status["rule_id"]
        for status in (status_for(rule) for rule in corpus)
        if status["machine_executable"] and status["condition_is_vacuous"]
    ]

    assert not liars, f"executable rules with an empty condition: {liars}"


def test_authorities_are_named_verbatim_not_invented(corpus):
    """Party names must be phrases the document supplies.

    The rules naming an authority are the seed for R2's `approval_requirement`
    nodes, so an invented name here would propagate into a structured
    dependency that looks authoritative.

    Checked against the whole canonical record, not just `source_text`. A
    parent clause legitimately governs its children — AD-103 3.2 requires the
    President's approval "in one of the following cases only", and 3.2.2
    inherits it — so the authority appears in `prerequisite` while the child's
    own sentence never mentions him. Asserting against `source_text` alone
    reported that correct inheritance as a fabrication.
    """

    for rule in corpus:
        status = status_for(rule)
        canonical = rule.formulation.canonical if rule.formulation else None
        haystack = " ".join(
            filter(
                None,
                [
                    rule.title,
                    rule.description,
                    canonical.source_text if canonical else None,
                    json.dumps(canonical.rule.model_dump(mode="json")) if canonical and canonical.rule else None,
                ],
            )
        ).casefold()
        for party in status["parties"]:
            assert party["name"].casefold() in haystack, (
                f"{status['rule_id']}: party {party['name']!r} appears nowhere in its "
                "canonical record"
            )


def test_an_inherited_authority_declares_that_it_was_inherited(corpus):
    """A party the rule's own sentence never names must say where it came from.

    This is the invariant that keeps inheritance honest. Without it a reviewer
    sees "the President" on a rule about promotions whose text does not mention
    him, with nothing to distinguish a correctly inherited requirement from a
    hallucinated one.
    """

    for rule in corpus:
        status = status_for(rule)
        canonical = rule.formulation.canonical if rule.formulation else None
        own_text = (canonical.source_text if canonical else "").casefold()
        for party in status["parties"]:
            if party["name"].casefold() in own_text:
                continue
            assert status["source_origin"] == "inherited_context", (
                f"{status['rule_id']}: party {party['name']!r} is absent from the rule's "
                f"own source text but source_origin is {status['source_origin']!r}"
            )
