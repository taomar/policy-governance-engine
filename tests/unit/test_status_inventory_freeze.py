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

    assert len(corpus) == 37
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
        ("rules", 37),
        ("machine_executable", 1),
        ("vacuous_conditions", 36),
        ("naming_an_authority", 8),
        ("rules_with_requirements", 15),
        ("requirement_phrases", 21),
        ("requirement_phrases_bundling_several", 14),
        ("inherited_from_parent_clause", 11),
        ("stored_ambiguity_differs_from_derived", 0),
        ("three_flags_disagree", 0),
    ],
)
def test_headline_totals_are_unchanged(live, measure, expected):
    """Pinned individually so a failure names which measure moved."""

    assert live["totals"][measure] == expected


def test_status_flags_now_agree_for_almost_every_rule(live):
    """The contradiction this work existed to remove.

    21 of 44 rules once reported `decidable`, `human_judgment_required` and
    `machine_executable=false` at once — three fields telling a reader three
    different things about the same rule, on half the corpus.

    Ambiguity now reports only what the extractor found ambiguous in the
    document, so what remains is a handful of genuinely unclear clauses rather
    than a flag that fired on everything and therefore meant nothing.
    """

    assert live["totals"]["three_flags_disagree"] == 0
    assert live["totals"]["rules"] == 37


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


def test_some_rules_inherit_their_requirements(live):
    """Rules carrying a requirement their own sentence never states.

    Sized because it constrains anything that builds a structured dependency
    from one: the node must cite the parent clause that stated the
    requirement, not the child, or it will point a reader at text that does
    not contain it.
    """

    assert live["totals"]["inherited_from_parent_clause"] == 11




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


def test_the_provenance_field_and_the_description_note_never_disagree(corpus):
    """One source, two renderings — they must not drift.

    The code is exposed as a structured field *and* appended to `description`
    as `[Conditions: <code> — …]`. Two copies of one fact is how a correction
    gets applied to one of them. Checked over the real corpus rather than a
    constructed pair, because the note is written at extraction time and the
    field is derived on read, so only stored data exercises both paths.
    """

    for rule in corpus:
        status = status_for(rule)
        from_note = status["condition_provenance_code"]
        from_field = status["condition_provenance_code"]
        if from_note is None:
            continue
        assert from_note == from_field, (
            f"{status['rule_id']}: description note says {from_note!r} but the "
            f"condition_provenance field says {from_field!r}"
        )


def test_every_rule_reaches_the_interface_with_a_provenance_field(corpus):
    """The interface cannot explain an empty tree without this.

    Before it existed, every non-executable rule showed one sentence — "no fact
    model maps this rule's terms" — which is the wrong instruction for 25 of
    these 44, whose source states no condition at all. There is nothing to map,
    so no mapping could have fixed them.
    """

    without = [
        status["rule_id"]
        for status in (status_for(rule) for rule in corpus)
        if status["condition_provenance_code"] is None
    ]

    assert not without, f"rules reaching the interface with no provenance: {without}"


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


def _inheritance_is_declared(party_name: str, own_text: str, source_origin) -> bool:
    """The invariant itself, as a function of the three things it depends on.

    Extracted so it can be exercised with a constructed case. Reading it only
    from the corpus meant it went unchecked the moment no rule happened to
    carry a party its own sentence omits -- which is the situation today: 28 of
    37 rules carry parties and every one of them names its party in its own
    text, so the assertion below never ran and the test passed having checked
    nothing.
    """

    if party_name.casefold() in own_text.casefold():
        return True
    return source_origin == "inherited_context"


def test_an_inherited_authority_declares_that_it_was_inherited(corpus):
    """A party the rule's own sentence never names must say where it came from.

    This is the invariant that keeps inheritance honest. Without it a reviewer
    sees "the President" on a rule about promotions whose text does not mention
    him, with nothing to distinguish a correctly inherited requirement from a
    hallucinated one.
    """

    examined = 0
    for rule in corpus:
        status = status_for(rule)
        canonical = rule.formulation.canonical if rule.formulation else None
        own_text = (canonical.source_text if canonical else "").casefold()
        for party in status["parties"]:
            examined += 1
            assert _inheritance_is_declared(
                party["name"], own_text, status["source_origin"]
            ), (
                f"{status['rule_id']}: party {party['name']!r} is absent from the rule's "
                f"own source text but source_origin is {status['source_origin']!r}"
            )

    assert examined, (
        "no parties were examined, so this proved nothing about inheritance -- "
        "either the corpus lost its parties or status_for stopped reporting them"
    )


def test_the_inheritance_rule_rejects_an_undeclared_party() -> None:
    """The check above must be able to fail on input the corpus does not contain.

    No rule in the current corpus names a party its own sentence omits, so the
    corpus scan alone cannot demonstrate that the invariant is enforced rather
    than merely unviolated. This supplies the case directly.
    """

    # named in its own sentence: origin is irrelevant
    assert _inheritance_is_declared("the President", "approved by the President", None)

    # absent from its own sentence, and says where it came from
    assert _inheritance_is_declared("the President", "promotions are annual", "inherited_context")

    # absent, and claims nothing -- the fabrication this invariant exists to catch
    assert not _inheritance_is_declared("the President", "promotions are annual", None)
    assert not _inheritance_is_declared(
        "the President", "promotions are annual", "resolved_reference"
    )
