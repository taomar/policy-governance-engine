"""A policy's history is the sightings of its key, and says only what it saw.

The failures guarded here are all failures of overclaiming. A history panel is
read as a record of what happened, so anything it states that was not observed
is worse than a blank: the reader has no way to tell the inference from the
evidence.
"""
from __future__ import annotations

import re
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# The wire contract
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENDPOINT = _REPO_ROOT / "src" / "policy_platform" / "api" / "routers" / "policy_sets.py"
_WEB_VIEW = _REPO_ROOT / "apps" / "web" / "src" / "components" / "policyTabPanes.tsx"


def _endpoint_keys() -> set[str]:
    """The key names this endpoint puts on the wire."""
    source = _ENDPOINT.read_text(encoding="utf-8")
    start = source.index("async def get_provision_history")
    end = source.find("\n@router", start)
    body = source[start:] if end == -1 else source[start:end]
    return set(re.findall(r'"([a-z_]+)":', body))


def _web_view_fields() -> set[str]:
    """The field names the web history pane reads off that wire."""
    source = _WEB_VIEW.read_text(encoding="utf-8")
    fields: set[str] = set()
    for name in ("PolicySightingView", "PolicyRuleSightingView"):
        start = source.index(f"export interface {name} {{")
        body = source[start : source.index("}", start)]
        fields |= set(re.findall(r"^\s{2}([a-z_]+)\??:", body, flags=re.MULTILINE))
    return fields


def test_the_history_endpoint_and_its_only_reader_agree_on_names() -> None:
    """A field the pane reads but the server never sends is `undefined` at runtime.

    This is not hypothetical. The pane shipped declaring `rules_changed`,
    `rule_count` and `effective_from` against a server sending `rules_reworded`
    and a `rules` list, and the tab threw on the first real payload while every
    test on both sides passed — because each side tested against its own idea of
    the shape, and the two ideas never met until the page ran.

    Nothing here checks a value. Only that the two vocabularies are the same
    one, which is the single fact neither suite could see alone.
    """
    emitted = _endpoint_keys()
    read = _web_view_fields()
    assert read, "the web view declares no fields; the parse is wrong, not the code"
    assert not (read - emitted), (
        f"the history pane reads fields the endpoint does not send: {sorted(read - emitted)}"
    )


def test_the_endpoint_sends_nothing_the_reader_has_no_name_for() -> None:
    """Sent-but-unread is a weaker fault than read-but-unsent, and still a fault.

    It means either the pane is missing something the server thought worth
    reporting, or the server is paying to serialise something nobody wanted.
    Both deserve a decision rather than a silence.
    """
    unread = _endpoint_keys() - _web_view_fields()
    assert not unread, f"the endpoint sends fields nothing reads: {sorted(unread)}"


_ASSEMBLY = (
    _REPO_ROOT
    / "src"
    / "policy_platform"
    / "infrastructure"
    / "assembly"
    / "provision_history.py"
)


def test_every_column_the_assembler_reads_is_one_the_query_selects() -> None:
    """The link before the wire, and the one no other test here can see.

    The two tests above agree the server and the pane use one vocabulary. Both
    would still pass if the assembler read a column the query never selected:
    the failure is an `AttributeError` on the first row of real data, in a
    request no unit test issues, on a page that has already rendered its header.

    The pane's own history is the evidence. `effective_from` was declared on the
    reader long before anything served it. Adding it to the payload is not
    enough; the value has to be selected before it can be read.
    """
    source = _ASSEMBLY.read_text(encoding="utf-8")
    start = source.index("_SIGHTINGS_SQL")
    selected = set(re.findall(r"AS\s+([a-z_]+)", source[start : source.index('"""', start + 40)]))
    read = set(re.findall(r"\brow\.([a-z_]+)", source))
    assert selected, "no columns parsed out of the query; the parse is wrong, not the code"
    assert not (read - selected), (
        f"the assembler reads columns the query does not select: {sorted(read - selected)}"
    )
