"""A model call's token cost must reach a reader, not be thrown away.

Every Azure OpenAI chat response carries a ``usage`` block. The client read it
only to explain a truncation and discarded it on the success path, so the one
cost figure the service returns on every call reached nobody: no counter, no
reply, no screen. That is the "built and wired to nothing" failure this
repository has logged repeatedly, in the specific shape of a number computed and
dropped.

These tests hold two things at once:

* the **producer** — a successful ``chat`` publishes its usage into whatever
  collection scope is open, exactly once per logical call however many HTTP
  attempts it took, and never invents a figure the service did not give;
* the **consumer** — ``ask`` (the Ask-AI endpoint's entry point) opens such a
  scope around its one model call and puts the result on its reply, so the
  figure is carried to the caller rather than left in a variable.

Four outcomes are kept apart throughout, because merging them reports a cost
that did not happen: a call that reported figures, a call that reported none
(absent, not zero), a call that never reached the model (absent from the meter
entirely), and a call nobody was collecting (recorded nowhere). No observed
token count or model name is asserted here — the numbers are test inputs fed in
and checked by round-trip and relationship, never a corpus figure written as a
literal.
"""
from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

import httpx
import pytest

from policy_platform.infrastructure.ai import openai_client
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient, AzureOpenAIError
from policy_platform.infrastructure.ai.usage_metering import (
    collect_token_usage,
    record_call_usage,
)
from policy_platform.infrastructure.assistants import ai_chat


class _Settings:
    ai_enabled = True
    search_enabled = False
    azure_openai_endpoint = "https://example.invalid"
    azure_openai_api_key = "key"
    azure_openai_deployment = "quality"
    azure_openai_fast_deployment = "fast"
    azure_openai_embedding_deployment = "embed"
    azure_openai_api_version = "2024-10-21"
    azure_search_authoring_index = "index"


def _ok(content: str = '{"ok": true}') -> httpx.Response:
    """A 200 that carries no usage block — a call that reported nothing."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        request=httpx.Request("POST", "https://example.invalid"),
    )


def _ok_with_usage(
    prompt: int,
    completion: int,
    total: int,
    *,
    reasoning: int | None = None,
    content: str = '{"ok": true}',
) -> httpx.Response:
    """A 200 whose usage block reports the given counts, shaped like the service's."""
    usage: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
    if reasoning is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": usage,
        },
        request=httpx.Request("POST", "https://example.invalid"),
    )


def _embedding_with_usage(prompt: int, total: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [{"index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": prompt, "total_tokens": total},
        },
        request=httpx.Request("POST", "https://example.invalid"),
    )


def _status(code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        code,
        text="upstream said no",
        headers=headers or {},
        request=httpx.Request("POST", "https://example.invalid"),
    )


@pytest.fixture
def calls(monkeypatch):
    """Records every POST attempt, and makes backoff instant."""

    attempts: list[str] = []

    async def _no_sleep(_seconds):
        attempts.append(f"slept:{_seconds:.0f}")

    monkeypatch.setattr(openai_client.asyncio, "sleep", _no_sleep)
    return attempts


def _client_returning(monkeypatch, calls, outcomes):
    """Each entry is a Response to return or an Exception to raise, in order."""

    queue = list(outcomes)

    class _Transport:
        async def post(self, url, headers=None, json=None):
            calls.append("post")
            result = queue.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(openai_client.httpx, "AsyncClient", lambda **_kw: _Transport())
    return AzureOpenAIClient(_Settings())


def _posts(calls) -> int:
    return sum(1 for c in calls if c == "post")


# --- producer: chat publishes its usage into the active scope -----------------


class TestASuccessfulCallReportsItsCost:
    async def test_a_successful_call_reports_its_tokens_to_an_open_scope(
        self, monkeypatch, calls
    ):
        # Red before the client was wired: the success path discarded `usage`,
        # so the scope saw a call it could not cost. The numbers are inputs, not
        # observed figures; the assertions are round-trip and a sum relationship.
        prompt, completion = 7, 11
        client = _client_returning(
            monkeypatch, calls, [_ok_with_usage(prompt, completion, prompt + completion)]
        )

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        report = scope.report()
        assert report.calls == 1
        assert report.calls_without_usage == 0
        assert report.prompt_tokens == prompt
        assert report.completion_tokens == completion
        assert report.total_tokens == prompt + completion

    async def test_reasoning_tokens_are_read_from_the_nested_detail(
        self, monkeypatch, calls
    ):
        prompt, completion, reasoning = 3, 4, 5
        client = _client_returning(
            monkeypatch,
            calls,
            [_ok_with_usage(prompt, completion, prompt + completion, reasoning=reasoning)],
        )

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        assert scope.report().reasoning_tokens == reasoning

    async def test_a_call_without_the_nested_detail_leaves_reasoning_absent(
        self, monkeypatch, calls
    ):
        # A fast (non-reasoning) deployment reports prompt/completion/total but no
        # reasoning detail. That field is absent for the call, not zero.
        client = _client_returning(monkeypatch, calls, [_ok_with_usage(3, 4, 7)])

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        assert scope.report().reasoning_tokens is None

    async def test_an_embedding_call_reports_its_tokens_to_the_same_scope(
        self, monkeypatch, calls
    ):
        client = _client_returning(
            monkeypatch,
            calls,
            [_embedding_with_usage(prompt=5, total=5)],
        )

        with collect_token_usage() as scope:
            vectors = await client.embed(["one input"])

        assert vectors == [[0.1, 0.2]]
        assert scope.report().calls == 1
        assert scope.report().prompt_tokens == 5
        assert scope.report().completion_tokens is None
        assert scope.report().total_tokens == 5


class TestTheFourStatesAreHeldApart:
    async def test_a_call_that_reports_no_usage_stays_absent_not_zero(
        self, monkeypatch, calls
    ):
        # The state this task most easily gets wrong: a 200 with no usage block
        # is a call whose cost is unknown, not a call that cost zero. Defaulting
        # it to 0 would report a cost that did not happen.
        client = _client_returning(monkeypatch, calls, [_ok("answered")])

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        report = scope.report()
        assert report.calls == 1
        assert report.calls_without_usage == 1
        assert report.prompt_tokens is None
        assert report.completion_tokens is None
        assert report.total_tokens is None

    async def test_a_reported_zero_is_kept_distinct_from_absent(
        self, monkeypatch, calls
    ):
        # The counterpart: a usage block that genuinely says zero is present, and
        # must survive as 0 rather than being read as "nothing reported".
        client = _client_returning(monkeypatch, calls, [_ok_with_usage(0, 0, 0)])

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        report = scope.report()
        assert report.calls_without_usage == 0
        assert report.prompt_tokens == 0
        assert report.total_tokens == 0

    async def test_a_call_that_fails_before_the_model_records_nothing(
        self, monkeypatch, calls
    ):
        # A request the service refuses (a non-retryable 4xx) raises before any
        # response body is read, so nothing was spent and nothing is recorded:
        # the call is absent from the meter, not a zero-cost entry.
        client = _client_returning(monkeypatch, calls, [_status(400)])

        with collect_token_usage() as scope:
            with pytest.raises(AzureOpenAIError):
                await client.chat([{"role": "user", "content": "x"}])

        report = scope.report()
        assert report.calls == 0
        assert report.prompt_tokens is None

    async def test_a_call_made_with_no_scope_open_records_nothing(
        self, monkeypatch, calls
    ):
        # Nobody was collecting, so the figure was never asked for. The call must
        # still succeed, and must not leak into a scope opened afterwards.
        client = _client_returning(monkeypatch, calls, [_ok_with_usage(7, 11, 18)])

        assert await client.chat([{"role": "user", "content": "x"}]) == '{"ok": true}'

        with collect_token_usage() as later:
            pass
        assert later.report().calls == 0


class TestOneLogicalCallIsCountedOnce:
    async def test_a_retried_call_counts_once_not_once_per_attempt(
        self, monkeypatch, calls
    ):
        # Three HTTP attempts, one logical call. The cost of a retry is a second
        # inference at the vendor; here it must read as the single call it was,
        # carrying the usage of the attempt that finally answered.
        prompt, completion = 7, 11
        client = _client_returning(
            monkeypatch,
            calls,
            [
                httpx.ReadTimeout("stalled"),
                _status(503),
                _ok_with_usage(prompt, completion, prompt + completion),
            ],
        )

        with collect_token_usage() as scope:
            await client.chat([{"role": "user", "content": "x"}])

        assert _posts(calls) == 3
        report = scope.report()
        assert report.calls == 1
        assert report.prompt_tokens == prompt


class TestAbsentAndZeroCoexistInOneScope:
    async def test_a_missing_block_and_a_reported_zero_are_both_visible(self):
        # Driven at the meter directly (no transport): one call reports nothing
        # and one reports zeros. The scope must show two calls, one of them
        # without usage, and a prompt total of 0 contributed by the zero call —
        # proving absent and zero are not the same fact.
        with collect_token_usage() as scope:
            record_call_usage(None)
            record_call_usage(
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            )

        report = scope.report()
        assert report.calls == 2
        assert report.calls_without_usage == 1
        assert report.prompt_tokens == 0

    async def test_a_stray_non_count_is_read_as_absent(self):
        # A bool is an int in Python but never a token count; a malformed field
        # must be absent rather than silently counted as 0 or 1.
        with collect_token_usage() as scope:
            record_call_usage({"prompt_tokens": True, "completion_tokens": "12"})

        report = scope.report()
        assert report.calls == 1
        assert report.calls_without_usage == 1
        assert report.prompt_tokens is None
        assert report.completion_tokens is None


# --- consumer: ask() opens a scope and surfaces the figure on its reply --------


class _RecordingClient:
    """Stands in for the real client, recording into the ambient scope exactly as
    the wired client does on its success path, so a test can prove `ask` opens
    the scope and reads it back rather than that the client works."""

    usage_to_report: Any = None

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        record_call_usage(type(self).usage_to_report)
        return json.dumps({"groups": [], "reflection": "."})


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingClient]:
    monkeypatch.setattr(ai_chat, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_chat, "AzureOpenAIClient", _RecordingClient)
    _RecordingClient.usage_to_report = None
    return _RecordingClient


class TestAskCarriesTheCostToItsReader:
    async def test_ask_puts_the_calls_token_usage_on_its_reply(
        self, recorded: type[_RecordingClient]
    ):
        # Red before ask() was wired: with no scope opened around the call, the
        # recorded usage went nowhere and the reply carried no cost. The consumer
        # is ask(); its reader is the /api/ai/ask response this dict becomes.
        prompt, completion = 7, 11
        recorded.usage_to_report = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }

        reply = await ai_chat.ask(None, question="what does the handbook say?", policy_set_key=None)

        assert "usage" in reply
        usage = reply["usage"]
        assert usage["calls"] == 1
        assert usage["calls_without_usage"] == 0
        assert usage["prompt_tokens"] == prompt
        assert usage["completion_tokens"] == completion
        assert usage["total_tokens"] == prompt + completion

    async def test_ask_carries_a_missing_usage_figure_across_as_absent(
        self, recorded: type[_RecordingClient]
    ):
        # A call that reported no usage must reach the reader as absent, not as a
        # zero cost. `null` on the wire, `None` here — distinct from a real 0.
        recorded.usage_to_report = None

        reply = await ai_chat.ask(None, question="a general question", policy_set_key=None)

        usage = reply["usage"]
        assert usage["calls"] == 1
        assert usage["calls_without_usage"] == 1
        assert usage["prompt_tokens"] is None
        assert usage["total_tokens"] is None


def test_ask_is_the_caller_that_opens_a_usage_scope():
    """The capability is only real if production reaches it. Walk ai_chat's AST
    and prove `ask` itself contains the call that opens the collection scope —
    evidence of the caller, not merely that the scope works when called."""
    source = pathlib.Path(ai_chat.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    ask = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask"
    )
    opens_scope = [
        node
        for node in ast.walk(ask)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "collect_token_usage"
    ]
    assert opens_scope, "ask() must open a collect_token_usage() scope to surface usage on its reply"
