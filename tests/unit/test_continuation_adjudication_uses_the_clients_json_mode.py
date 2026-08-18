"""Continuation adjudication asks the client for JSON the way the client offers.

`AzureOpenAIClient.chat()` takes `json_mode: bool` and, when set, puts
`response_format={"type": "json_object"}` on the request itself -- and also
guards the truncated-JSON failure mode. The adjudicator instead passed
`response_format=` straight through, a keyword `chat()` does not accept, so the
call raised `TypeError` before it ever reached the model. `discover_continuations`
catches per-window failures and degrades to the earlier tiers, so the whole
model tier was dead on every window while the run reported a plausible number.

These tests drive the real adjudicator with a client whose `chat()` signature is
the real one -- keyword-only, `json_mode`, no `response_format`. That is what
makes the red load-bearing: passing the wrong keyword raises exactly the
`TypeError` the run hit, and a client that tolerated any keyword would prove
nothing (this repository's most-logged failure, a green test over a dead path).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from policy_platform.infrastructure.extraction.continuation_adjudicator import (
    ClauseWindow,
    adjudicate_window,
    discover_continuations,
)


class _ClientWithRealChatSignature:
    """A stand-in whose `chat()` accepts exactly what the real client accepts.

    No `**kwargs`: an unexpected keyword raises `TypeError`, reproducing the
    live failure rather than hiding it. It records `json_mode` so a test can
    show the JSON guarantee was actually requested of the model.
    """

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[dict] = []

    async def chat(
        self,
        messages: list[dict],
        *,
        deployment: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 1500,
        temperature: float | None = None,
        seed: int | None = None,
        timeout: float = 120.0,
        reasoning_effort: str | None = None,
    ) -> str:
        self.calls.append({"json_mode": json_mode, "deployment": deployment})
        return self._reply


_SETTINGS = SimpleNamespace(azure_openai_deployment="test-deployment")

# A governing stem that stops mid-thought, and the case that completes it. The
# stem carries no terminal full stop, which is the format-independent signal
# that makes the window worth a model call on any document.
_PARENT = ClauseWindow(
    element_id="e-parent",
    rule_id="R-parent",
    text="Salary shall be increased in one of the following cases only:",
)
_CHILD = ClauseWindow(
    element_id="e-child",
    rule_id="R-child",
    text="3.2.1 An annual increment is applied each January.",
)


def _reply_linking_parent_to_child() -> str:
    # The model quotes the parent's own promise verbatim, which is what turns a
    # proposed link into a confirmed one.
    return json.dumps(
        {
            "links": [
                {
                    "parent": "e-parent",
                    "child": "e-child",
                    "quote": "in one of the following cases only",
                }
            ]
        }
    )


async def test_adjudicate_window_asks_the_model_in_json_mode_and_links() -> None:
    client = _ClientWithRealChatSignature(_reply_linking_parent_to_child())

    edges = await adjudicate_window(client, _SETTINGS, [_PARENT, _CHILD])

    # The call reached the model, and asked for JSON the way the client offers
    # it rather than through a keyword the client rejects.
    assert len(client.calls) == 1
    assert client.calls[0]["json_mode"] is True
    # A verified quote produces a confirmed continuation between the two rules.
    assert len(edges) == 1
    assert edges[0].state == "confirmed"
    assert edges[0].source_rule_id == "R-parent"
    assert edges[0].target_rule_id == "R-child"


async def test_the_model_tier_is_not_silently_dead_end_to_end() -> None:
    # Through the public entry point, which catches a window failure and
    # degrades to the earlier tiers. Under the defect that catch swallowed the
    # TypeError and the tier returned nothing on every run; a working tier
    # returns the confirmed link.
    client = _ClientWithRealChatSignature(_reply_linking_parent_to_child())

    edges = await discover_continuations(
        client, _SETTINGS, [_PARENT, _CHILD], resolved_element_ids=set()
    )

    assert [e.state for e in edges] == ["confirmed"]
    assert (edges[0].source_rule_id, edges[0].target_rule_id) == ("R-parent", "R-child")


async def test_a_rule_read_from_a_continuation_is_not_marked_second_class() -> None:
    # Constraint 5 / no second-class tagging: a confirmed continuation carries a
    # verified quote as its evidence, the same standing any structural link has.
    # How the link was found is not a mark against either endpoint.
    client = _ClientWithRealChatSignature(_reply_linking_parent_to_child())

    edges = await adjudicate_window(client, _SETTINGS, [_PARENT, _CHILD])

    assert edges[0].evidence is not None
    assert "verified_quote" in edges[0].evidence.signals
