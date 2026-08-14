"""A rule the system called changed must show the reviewer what changed.

`rule_delta` decides whether two rules are the same rule. This explainer tells
a human why one was flagged. Those are different questions and are allowed to
be answered by different lists -- but only in one direction. The explainer may
show more than identity counted; it may not show less.

It showed less. The diff walked `SEMANTIC_FIELDS`, ten top-level fields, seven
of which are constant across the live corpus. What a rule decides -- its
trigger, its subject, its temporal constraint, whether its predicate is
negated -- lives inside `formulation.canonical.rule` and `attributes`, which
that list never named. So the run-to-run comparison could correctly rule two
records different while the surface that explains the difference showed a
reviewer nothing at all, and a reviewer shown a `Changed` badge over an empty
diff draws the only available conclusion: that the tool is broken.

These tests hold the floor as a property rather than as a field list, because
a field list is what failed. The assertion is that the diff is empty exactly
when identity says the two rules are the same -- so a field added to the
schema tomorrow is covered on the day it is added, by nobody remembering
anything.
"""
from __future__ import annotations

import pytest

from policy_platform.infrastructure.assistants.rule_change_explainer import (
    PROSE_FIELDS,
    semantic_diff,
)
from policy_platform.infrastructure.projection.rule_delta import (
    SEMANTIC_FIELDS,
    identify,
)

SHARED_PASSAGE = (
    "The employee shall return all issued equipment in the event of "
    "termination from employment."
)


def _rule(**core: object) -> dict:
    """A payload shaped like a real one, with the rule core where it really lives.

    Two payloads from this helper differ only in what is passed in, so a test
    asserting they are distinguished is asserting exactly one thing.
    """
    rule = {
        "subject": "the employee",
        "predicate": "shall return",
        "object": "all issued equipment",
        "modality": "obligation",
        "trigger": None,
        "temporal_constraint": None,
    }
    rule.update(core)
    return {
        "rule_id": "AI-0000000001",
        "rule_type": "obligation",
        "effect": "permit",
        "title": "Return of equipment",
        "description": "The employee returns issued equipment.",
        "effective_from": "2024-01-01",
        "lineage": {"run": "r1"},
        "evidence": [{"page": 3}],
        "formulation": {
            "source_text": SHARED_PASSAGE,
            "canonical": {"source_text": SHARED_PASSAGE, "rule": rule},
        },
        "attributes": {"subject": rule["subject"]},
    }


#: Differences that change what the rule decides, none of which is reachable
#: from `SEMANTIC_FIELDS`. The first three are the pairs that were shown to
#: forge an identity; the fourth is a dropped negation.
CORE_DIFFERENCES = [
    pytest.param(
        {"trigger": "In the event of termination from employment"},
        {"trigger": "upon request by the issuing department"},
        id="trigger: two different occasions to act",
    ),
    pytest.param(
        {"subject": "the receipt of the equipment"},
        {"subject": "the issue of the equipment"},
        id="subject: two different things acted on",
    ),
    pytest.param(
        {"temporal_constraint": "at the end of the probationary period"},
        {"temporal_constraint": "during the probationary period"},
        id="temporal: a boundary against a span",
    ),
    pytest.param(
        {"predicate": "shall return"},
        {"predicate": "shall not return"},
        id="predicate: a dropped negation",
    ),
]


@pytest.mark.parametrize(("left_core", "right_core"), CORE_DIFFERENCES)
def test_a_difference_the_system_acted_on_is_shown_to_the_reviewer(
    left_core: dict, right_core: dict
) -> None:
    """The defect itself: flagged as changed, explained as nothing."""

    before, after = _rule(**left_core), _rule(**right_core)
    assert identify(before).content_fingerprint != identify(after).content_fingerprint

    changes = semantic_diff(before, after)

    assert changes, (
        "identity ruled these two different rules and the reviewer is shown "
        "an empty diff; the badge says changed and the explanation says nothing"
    )


@pytest.mark.parametrize(("left_core", "right_core"), CORE_DIFFERENCES)
def test_the_field_named_is_the_field_that_differs(
    left_core: dict, right_core: dict
) -> None:
    """Non-empty is not enough. Naming the wrong field is its own way to mislead."""

    changes = semantic_diff(_rule(**left_core), _rule(**right_core))
    named = {change["field"] for change in changes}

    assert "formulation" in named, f"expected the rule core to be named, got {sorted(named)}"


def test_the_diff_is_empty_exactly_when_the_rules_are_the_same_rule() -> None:
    """The property, stated in both directions.

    Silence must mean sameness and sameness must mean silence. Asserting only
    the first would be satisfied by a diff that reports every field always.
    """

    same_left, same_right = _rule(), _rule()
    differing = _rule(trigger="upon request by the issuing department")

    assert identify(same_left).content_fingerprint == identify(same_right).content_fingerprint
    assert semantic_diff(same_left, same_right) == []

    assert identify(same_left).content_fingerprint != identify(differing).content_fingerprint
    assert semantic_diff(same_left, differing) != []


def test_a_rules_position_in_the_models_output_is_not_a_change() -> None:
    """Identity strips positions, so showing one would report a phantom change.

    This is the direction the fix could have overshot in: widening the diff
    until it reports churn the identity deliberately ignores, which trains a
    reviewer to disregard it.
    """

    before = _rule()
    after = _rule()
    before["formulation"]["canonical"]["source_index"] = 0
    after["formulation"]["canonical"]["source_index"] = 7

    assert identify(before).content_fingerprint == identify(after).content_fingerprint
    assert semantic_diff(before, after) == []


def test_provenance_is_not_a_change() -> None:
    """Regenerated every run. Reporting it would flag every rule in the document."""

    before, after = _rule(), _rule()
    after["rule_id"] = "AI-9999999999"
    after["effective_from"] = "2025-06-01"
    after["lineage"] = {"run": "r2"}
    after["evidence"] = [{"page": 4}]

    assert semantic_diff(before, after) == []


def test_rewording_is_reported_as_wording_and_not_as_behaviour() -> None:
    """The separation the reviewer weighs differently, still intact."""

    before, after = _rule(), _rule()
    after["title"] = "Equipment return on exit"
    after["description"] = "Issued equipment is returned."

    assert semantic_diff(before, after) == []
    assert len(_diff_prose(before, after)) == 2


def test_every_prose_field_identity_ignores_is_reported_somewhere() -> None:
    """A field excluded from identity as prose and absent from the prose list
    would be reported by neither side, which is the same silence in miniature."""

    before, after = _rule(), _rule()
    for index, field in enumerate(PROSE_FIELDS):
        after[field] = f"changed-{index}"

    assert semantic_diff(before, after) == []
    assert len(_diff_prose(before, after)) == len(PROSE_FIELDS)


def test_the_reading_order_puts_the_curated_fields_first() -> None:
    """`SEMANTIC_FIELDS` keeps its job. It orders the diff; it no longer filters it.

    A reviewer should meet the fields chosen for them before the remainder, and
    the remainder must not reshuffle between page loads.
    """

    before = _rule(trigger="on resignation")
    after = _rule(trigger="on dismissal")
    before["rule_type"], after["rule_type"] = "obligation", "permission"
    before["effect"], after["effect"] = "permit", "deny"

    fields = [change["field"] for change in semantic_diff(before, after)]

    curated = [name for name in fields if name in SEMANTIC_FIELDS]
    remainder = [name for name in fields if name not in SEMANTIC_FIELDS]

    assert fields == curated + remainder, "curated fields must lead"
    assert curated == [name for name in SEMANTIC_FIELDS if name in curated]
    assert remainder == sorted(remainder), "the remainder must be stably ordered"
    assert semantic_diff(before, after) == semantic_diff(before, after)


def test_a_field_the_schema_gains_later_is_covered_without_being_listed() -> None:
    """Why this is a property and not a list.

    The previous diff was a list, and it went stale silently. An unlisted field
    that changes the rule's identity is shown because it changed the identity,
    not because someone remembered to add it.
    """

    before, after = _rule(), _rule()
    before["field_invented_after_this_test_was_written"] = "before"
    after["field_invented_after_this_test_was_written"] = "after"

    assert identify(before).content_fingerprint != identify(after).content_fingerprint
    named = {change["field"] for change in semantic_diff(before, after)}
    assert "field_invented_after_this_test_was_written" in named


def _diff_prose(before: dict, after: dict) -> list[dict]:
    from policy_platform.infrastructure.assistants.rule_change_explainer import _diff_fields

    return _diff_fields(before, after, PROSE_FIELDS)
