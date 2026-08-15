"""A policy's history is the sightings of its key, and says only what it saw.

The failures guarded here are all failures of overclaiming. A history panel is
read as a record of what happened, so anything it states that was not observed
is worse than a blank: the reader has no way to tell the inference from the
evidence.
"""
from __future__ import annotations

import pytest

from policy_platform.infrastructure.assembly.provision_history import (
    PolicyRuleSighting,
    PolicySighting,
    rule_fingerprint,
)


class _Row:
    """The columns the fingerprint reads, and nothing else."""

    def __init__(self, **kwargs):
        defaults = {
            "title": "a title",
            "description": "a description",
            "rule_type": "obligation",
            "condition_json": {"type": "all", "all": []},
            "effect_json": {"type": "require_action"},
            "scope_json": {"personas": []},
            "required_facts_json": [],
        }
        defaults.update(kwargs)
        for name, value in defaults.items():
            setattr(self, name, value)


def test_a_rule_republished_unchanged_hashes_the_same() -> None:
    """The witness in the database today: one rule, two versions, identical.

    If republishing alone moved the fingerprint, every version boundary would
    render as a change and the reader could never find a real one.
    """
    assert rule_fingerprint(_Row()) == rule_fingerprint(_Row())


def test_ids_and_revisions_are_not_part_of_what_changed() -> None:
    """A revision counter moves for reasons that are not changes to the policy."""
    row = _Row()
    row.revision = 1
    bumped = _Row()
    bumped.revision = 9
    assert rule_fingerprint(row) == rule_fingerprint(bumped)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "a different title"),
        ("description", "different wording"),
        ("condition_json", {"type": "all", "all": [{"type": "always"}]}),
        ("effect_json", {"type": "deny"}),
        ("scope_json", {"personas": ["someone"]}),
        ("required_facts_json", [{"name": "a-fact"}]),
        ("rule_type", "permission"),
    ],
)
def test_every_part_a_reader_would_call_the_rule_moves_the_fingerprint(field, value) -> None:
    assert rule_fingerprint(_Row()) != rule_fingerprint(_Row(**{field: value}))


def test_key_order_in_stored_json_is_not_a_change() -> None:
    """Two dicts with the same content must hash alike however they were built."""
    one = _Row(scope_json={"personas": ["a"], "processes": ["b"]})
    other = _Row(scope_json={"processes": ["b"], "personas": ["a"]})
    assert rule_fingerprint(one) == rule_fingerprint(other)


def test_the_first_sighting_defaults_to_first_seen_not_added() -> None:
    """`added` asserts the policy was absent before. Only `first_seen` is known.

    Rules published before the provision link existed carry no key, so an
    absence in an earlier version is not evidence of absence of the policy.
    """
    sighting = PolicySighting(
        version_id="v",
        version_number=1,
        is_active=False,
        approved_by=None,
        approved_at=None,
        heading_path=[],
        rules=[PolicyRuleSighting(rule_id="r", title="t", fingerprint="f")],
    )
    assert sighting.change == "first_seen"
    assert sighting.change != "added"
