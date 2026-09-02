"""A long run must not be undone by one call that stalls.

Extraction is tens of remote calls over tens of minutes. Every one of them can
fail for reasons that have nothing to do with the work: a connection that never
answers, a service that is briefly unwell, a rate limit. A loop that treats any
such failure as fatal has no way to finish as its input grows — the chance that
*some* call stalls rises with the number of calls, so a long enough document can
become impossible to extract even though every individual batch is fine.

Two defences, and they are different. Retrying handles the failure that goes
away on its own. Classifying an exhausted retry as the *agent's* failure rather
than the *run's* handles the one that does not, so the cost is the batch it
happened on rather than every batch already paid for.

Neither may cost correctness: a retry must not be able to write a second copy of
anything, and a failure that will never succeed must not be retried at all.
"""

from __future__ import annotations

import httpx
import pytest

from policy_platform.infrastructure.ai import openai_client
from policy_platform.infrastructure.ai.openai_client import (
    AzureOpenAIClient,
    AzureOpenAIError,
    AzureOpenAITransientError,
)


class _Settings:
    ai_enabled = True
    azure_openai_endpoint = "https://example.invalid"
    azure_openai_api_key = "key"
    azure_openai_deployment = "quality"
    azure_openai_secondary_deployment = "fast"
    azure_openai_embedding_deployment = "embed"
    azure_openai_api_version = "2024-10-21"


def _ok(content: str = '{"ok": true}') -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
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


class TestAFailureThatMightNotRecurIsTriedAgain:
    @pytest.mark.asyncio
    async def test_a_stall_is_retried_and_the_call_succeeds(self, monkeypatch, calls):
        client = _client_returning(
            monkeypatch, calls, [httpx.ReadTimeout("stalled"), _ok("recovered")]
        )

        assert await client.chat([{"role": "user", "content": "x"}]) == "recovered"
        assert _posts(calls) == 2

    @pytest.mark.asyncio
    async def test_a_connection_that_never_opened_is_retried(self, monkeypatch, calls):
        client = _client_returning(
            monkeypatch, calls, [httpx.ConnectError("refused"), _ok("recovered")]
        )

        assert await client.chat([{"role": "user", "content": "x"}]) == "recovered"
        assert _posts(calls) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
    async def test_a_service_that_is_briefly_unwell_is_retried(
        self, monkeypatch, calls, code
    ):
        client = _client_returning(monkeypatch, calls, [_status(code), _ok("recovered")])

        assert await client.chat([{"role": "user", "content": "x"}]) == "recovered"
        assert _posts(calls) == 2

    @pytest.mark.asyncio
    async def test_the_service_is_obeyed_when_it_asks_for_a_specific_wait(
        self, monkeypatch, calls
    ):
        client = _client_returning(
            monkeypatch,
            calls,
            [_status(429, {"Retry-After": "7"}), _ok("recovered")],
        )

        await client.chat([{"role": "user", "content": "x"}])

        assert "slept:7" in calls, (
            f"expected the wait the service asked for to be honoured; "
            f"actual: {calls}"
        )


class TestAFailureThatWillNeverSucceedIsNotRetried:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    async def test_a_request_the_service_refuses_is_not_repeated(
        self, monkeypatch, calls, code
    ):
        """Retrying these burns the budget and buries the error that explains it."""

        client = _client_returning(monkeypatch, calls, [_status(code)])

        with pytest.raises(AzureOpenAIError) as caught:
            await client.chat([{"role": "user", "content": "x"}])

        assert _posts(calls) == 1, (
            f"expected one attempt for a {code}; actual: {_posts(calls)}"
        )
        assert not isinstance(caught.value, AzureOpenAITransientError)
        assert str(code) in str(caught.value)

    @pytest.mark.asyncio
    async def test_giving_up_says_so_and_says_how_many_times_it_tried(
        self, monkeypatch, calls
    ):
        client = _client_returning(
            monkeypatch, calls, [httpx.ReadTimeout("stalled")] * openai_client._MAX_ATTEMPTS
        )

        with pytest.raises(AzureOpenAITransientError, match="after 4 attempts"):
            await client.chat([{"role": "user", "content": "x"}])

        assert _posts(calls) == openai_client._MAX_ATTEMPTS


class TestARetryCannotDuplicateAnything:
    @pytest.mark.asyncio
    async def test_only_one_reply_ever_reaches_the_caller(self, monkeypatch, calls):
        """Three attempts, one answer.

        A reply that never arrived is never parsed, so no number of attempts can
        put a second copy of a record in front of the caller. The cost of a
        retry is a second inference at the vendor, not a duplicate here.
        """

        client = _client_returning(
            monkeypatch,
            calls,
            [httpx.ReadTimeout("a"), _status(503), _ok("the only answer")],
        )

        assert await client.chat([{"role": "user", "content": "x"}]) == "the only answer"
        assert _posts(calls) == 3


class TestAnExhaustedRetryCostsTheBatchAndNotTheRun:
    """The second defence, and the one that matters when retrying is not enough.

    `ai_extraction` commits per batch and catches each agent's own error to skip
    a batch and carry on. A transport failure used to escape that guard, because
    it was neither agent's error — so it reached the run-level handler, which
    marks the whole run failed. The batches already committed survived in the
    database, but the run was dead: no linking pass, no validation, no delta,
    and the previous extraction already superseded. The fix is to report an
    exhausted retry as the agent's own failure so the guard built for exactly
    this applies.
    """

    @pytest.mark.asyncio
    async def test_the_formulator_reports_it_as_its_own_failure(self, monkeypatch):
        from policy_platform.infrastructure.extraction import policy_formulator

        class _Stalling:
            async def chat(self, *_a, **_kw):
                raise AzureOpenAITransientError("chat call failed after 4 attempts")

        agent = policy_formulator.PolicyFormulatorAgent(_Stalling(), _Settings())

        with pytest.raises(policy_formulator.PolicyFormulationError, match="unreachable"):
            await agent.formulate("Employees must submit the form.")

    @pytest.mark.asyncio
    async def test_the_passage_extractor_reports_it_as_its_own_failure(self, monkeypatch):
        from policy_platform.infrastructure.extraction import passage_extractor

        class _Stalling:
            async def chat(self, *_a, **_kw):
                raise AzureOpenAITransientError("chat call failed after 4 attempts")

        agent = passage_extractor.PassageExtractorAgent(_Stalling(), _Settings())

        with pytest.raises(passage_extractor.PassageExtractionError, match="unreachable"):
            await agent.extract("Employees must submit the form.")

    @pytest.mark.asyncio
    async def test_a_batch_the_agent_can_serve_is_unaffected(self, monkeypatch, calls):
        """The volume floor: proves the stall was the reason, not a broken agent."""

        from policy_platform.infrastructure.extraction import policy_formulator

        served: list[str] = []

        class _Flaky:
            def __init__(self):
                self.seen = 0

            async def chat(self, *_a, **_kw):
                self.seen += 1
                if self.seen == 1:
                    raise AzureOpenAITransientError("failed after 4 attempts")
                return (
                    '{"CANONICAL_JSON": {"canonical_policies": []}, '
                    '"DMN_JSON": {"dmn_projection": {"decisions": []}}}'
                )

        agent = policy_formulator.PolicyFormulatorAgent(_Flaky(), _Settings())

        with pytest.raises(policy_formulator.PolicyFormulationError):
            await agent.formulate("batch one")
        served.append("batch two")
        await agent.formulate("batch two")

        assert served == ["batch two"], (
            f"expected the batch after the stall to be served; actual: {served}"
        )

    def test_waits_grow_with_each_attempt(self) -> None:
        early = max(openai_client._retry_delay(1, None) for _ in range(200))
        later = max(openai_client._retry_delay(3, None) for _ in range(200))

        assert later > early, f"expected backoff to grow; actual: {early} then {later}"

    def test_waits_are_capped(self) -> None:
        assert (
            max(openai_client._retry_delay(20, None) for _ in range(200))
            <= openai_client._BACKOFF_CAP_SECONDS
        )

    def test_waits_are_spread_so_failures_do_not_retry_in_lockstep(self) -> None:
        """Batches in one run fail together; retrying together repeats the pile-up."""

        drawn = {round(openai_client._retry_delay(3, None), 4) for _ in range(50)}

        assert len(drawn) > 1, f"expected jitter; actual: every wait was {drawn}"

    def test_a_date_formatted_retry_after_falls_back_rather_than_crashing(self) -> None:
        assert openai_client._retry_delay(1, "Wed, 21 Oct 2015 07:28:00 GMT") >= 0
