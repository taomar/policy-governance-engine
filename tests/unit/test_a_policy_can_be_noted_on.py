"""A note about a policy can be written about a policy.

WHAT THIS COVERS

Notes attach to a governed entity through `entity_type` + `entity_id`. The set
of accepted entity types is a `Literal` on the create request, so adding a kind
is a one-line change — and forgetting it is a silent one from the reader's side:
the interface offers a composer, the reader types a remark, and the server
rejects it with a validation error about a field they never saw.

A policy is now a first-class record. It is approved as a unit, published as a
unit and compared across versions as a unit, so it is the natural thing for a
reviewer to want to remark on: "these two rules of this section contradict each
other" is a statement about the section, and filed against one of the two rules
it reads as a complaint about that rule alone, invisible to whoever reads the
other.

WHAT IS ASSERTED, AND WHY THE SECOND HALF MATTERS

That "provision" is accepted, and that the union is still closed. A `Literal`
widened by accident to `str` would make the first assertion pass forever while
accepting anything at all, which is how a typo in a caller becomes a row nobody
can find again.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from policy_platform.api.schemas import CreateNoteRequest


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "entity_type": "provision",
        "entity_id": "a-provision-key",
        "author": "someone",
        "author_role": "a role",
        "body": "a remark",
        **overrides,
    }


def test_a_policy_is_something_a_note_can_be_written_about() -> None:
    request = CreateNoteRequest(**_payload())
    assert request.entity_type == "provision"


def test_the_kinds_a_note_can_attach_to_are_still_a_closed_set() -> None:
    # The mutation guard for the test above: if the union were widened to a
    # bare string to make "provision" work, this would stop failing and every
    # mistyped entity type would be accepted and then never found again.
    with pytest.raises(ValidationError):
        CreateNoteRequest(**_payload(entity_type="not-a-kind-of-thing"))


@pytest.mark.parametrize(
    "kind",
    ["policy_set", "policy_version", "candidate_rule", "rule"],
)
def test_widening_the_set_did_not_drop_anything_already_in_it(kind: str) -> None:
    assert CreateNoteRequest(**_payload(entity_type=kind)).entity_type == kind
