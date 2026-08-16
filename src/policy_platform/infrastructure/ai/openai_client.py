"""Thin async Azure OpenAI client (direct httpx REST calls, no SDK dependency).

Every endpoint shape here was verified live against the real `scopeaifoundry`
resource during setup (chat/completions on both `gpt-5.6-sol` and
`gpt-5.4-mini`, embeddings on `text-embedding-3-large`, all returned HTTP
200) — nothing here is a guessed/fabricated API shape.

Two deployments are used deliberately for different jobs:
- `azure_openai_deployment` (gpt-5.6-sol): higher-quality reasoning work
  where correctness matters most — extraction, rewrite, quality evaluation.
- `azure_openai_fast_deployment` (gpt-5.4-mini): interactive Ask-AI chat,
  where latency matters more than maximum reasoning depth.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from policy_platform.infrastructure.ai.usage_metering import record_call_usage
from policy_platform.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_EMBEDDINGS_API_VERSION = "2024-02-01"

#: Statuses where the request was well-formed and the service could not serve it
#: this time. Retrying is the right response: 408 and 504 are the service saying
#: it ran out of time, 429 is it asking us to slow down, and 500/502/503 are it
#: being unwell. Everything else in the 4xx range is a defect in what we sent —
#: a bad body, an expired key, a deployment that does not exist — and retrying
#: those burns the budget while hiding the error that would have explained it.
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

#: Four attempts, so a stall costs seconds rather than a whole run, and a truly
#: dead endpoint is still declared dead quickly instead of being retried into a
#: hang. With the backoff below the worst case adds well under a minute.
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 20.0

#: Passed on every extraction call. For the record, not for the effect.
#:
#: Measured directly on this deployment and it changes nothing: three batches
#: were re-read four times each with byte-identical input, and the seeded passes
#: disagreed with each other exactly as much as unseeded ones — one batch
#: returned four different passage counts from the same text. The service also
#: declines to say whether the seed was honoured, since `system_fingerprint` —
#: the field whose entire purpose is to warn that the backend moved underneath a
#: seed — comes back null from this resource.
#:
#: It is set anyway because the alternative is a blank where a determinism
#: control should be, and a blank invites the same investigation every few
#: months. The other two levers do not survive contact at all: `temperature` and
#: `top_p` are rejected outright by the reasoning deployment with a 400, so this
#: is the only one of the three that can even be sent.
#:
#: The value is arbitrary and its only requirement is that it never change.
#: Changing it would be indistinguishable, from the delta's point of view, from
#: the model drifting.
EXTRACTION_SEED = 20240817


class AzureOpenAIError(RuntimeError):
    """Raised when a call to Azure OpenAI fails or the resource isn't configured."""


class AzureOpenAITransientError(AzureOpenAIError):
    """A call failed for a reason that went away or might have.

    Separate from `AzureOpenAIError` so a caller running a long loop can tell
    "this batch is bad" from "the network hiccuped". The first should skip the
    batch; the second should not cost the caller the batches it already did.
    """


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before attempt `attempt` (1-based, so the first wait is 0).

    Exponential, capped, and jittered. Jitter matters because batches in one run
    fail for the same reason at the same moment; retrying them all on the same
    schedule reproduces the pile-up that caused the failure.
    """

    if retry_after:
        try:
            # The service asked for a specific wait. Honouring it is both more
            # polite and more likely to succeed than our own guess.
            return min(float(retry_after), _BACKOFF_CAP_SECONDS)
        except ValueError:
            pass  # A date-formatted Retry-After; fall through to our own backoff.
    ceiling = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_CAP_SECONDS)
    return random.uniform(0, ceiling)


async def _post_with_retry(
    url: str,
    *,
    headers: dict,
    body: dict,
    timeout: float,
    label: str,
) -> httpx.Response:
    """POST, trying again when the failure is one that might not recur.

    A chat completion is a request and a response, so a retry produces a fresh
    answer rather than a second copy of anything. Nothing is written to our
    database until a response comes back and is parsed, and a response that
    never arrived is never parsed, so at most one reply per call reaches the
    caller no matter how many attempts it took. Retrying cannot duplicate a
    record. It can cost the vendor a second inference — that is the price of
    not throwing away the caller's work, and it is the cheaper of the two.
    """

    last_error: Exception | None = None
    retry_after: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            delay = _retry_delay(attempt - 1, retry_after)
            logger.warning(
                "%s failed (attempt %d of %d): %s — retrying in %.1fs",
                label, attempt - 1, _MAX_ATTEMPTS, last_error, delay,
            )
            await asyncio.sleep(delay)
        retry_after = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # The reply never arrived. Whether the service did the work is
            # unknowable from here, and it does not matter: nothing downstream
            # has seen anything, so asking again is safe.
            last_error = exc
            continue

        if resp.status_code in _RETRYABLE_STATUSES:
            last_error = AzureOpenAITransientError(
                f"{label} failed ({resp.status_code}): {resp.text[:300]}"
            )
            retry_after = resp.headers.get("Retry-After")
            continue

        return resp

    raise AzureOpenAITransientError(
        f"{label} failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


class AzureOpenAIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.ai_enabled

    def _require_enabled(self) -> Settings:
        if not self.enabled:
            raise AzureOpenAIError(
                "Azure OpenAI is not configured (missing endpoint/api key/deployment in .env)"
            )
        return self._settings

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
        """Single chat-completion call; returns the assistant message content.

        NOTE on determinism: which sampling controls a deployment accepts differs
        per model, and an unsupported one is a hard 400 rather than a warning.
        Probed live against this resource on `gpt-5.6-sol`: `temperature=0` and
        `top_p=0` are both rejected ("Only the default (1) value is supported" /
        "not supported with this model"), while `seed` is accepted. So for the
        reasoning deployment `seed` is the only determinism control available,
        and callers that pass `temperature` to it will lose the call entirely.
        Accepting `seed` is not the same as honouring it: measured over six
        identical quality reviews it made no difference at all. The fast
        deployment (`gpt-5.4-mini`) does accept `temperature=0`.

        NOTE on reasoning models: `gpt-5.6-sol` (the "quality" deployment used for
        extraction/rewrite/quality-review) is a reasoning model — it silently spends
        part of `max_completion_tokens` on a hidden reasoning pass *before* any
        visible content is produced. If the budget is too small, the entire budget
        can be consumed by reasoning and the call returns `finish_reason="length"`
        with an EMPTY `content` string (confirmed live against this resource: a
        4000-token budget on a 45-clause extraction batch returned 4000 reasoning
        tokens and 0 content). Callers targeting the reasoning deployment must pass
        a generous `max_tokens` (observed need: ~1 reasoning-heavy pass + full JSON
        output, so 16000-20000+ for multi-rule extraction) and a matching `timeout`
        (large-budget calls observed taking 60-90s+). The fast deployment
        (`gpt-5.4-mini`) is NOT a reasoning model (`reasoning_tokens=0` in every
        observed call) and works fine with the smaller defaults.
        """

        settings = self._require_enabled()
        deployment_name = deployment or settings.azure_openai_deployment
        url = (
            f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
            f"{deployment_name}/chat/completions?api-version={settings.azure_openai_api_version}"
        )
        body: dict = {"messages": messages, "max_completion_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if temperature is not None:
            body["temperature"] = temperature
        if seed is not None:
            # Accepted, and measured to do nothing on the reasoning deployment:
            # six reviews of one unchanged rule set varied as much seeded as
            # unseeded (see ai_quality._AI_REVIEW_SEED). The service also
            # reports nothing back — `system_fingerprint`, the field that exists
            # to tell a caller the backend changed underneath a seed, comes back
            # null from this resource. Pass it if you like; do not build
            # anything on top of it that assumes two runs match.
            body["seed"] = seed
        if reasoning_effort is not None:
            # Reasoning-capable deployments (gpt-5.6-sol) accept this field to
            # trade latency for deeper reasoning. Not verified against every
            # deployment — if a target deployment rejects it, callers should
            # catch AzureOpenAIError and retry without it.
            body["reasoning_effort"] = reasoning_effort

        resp = await _post_with_retry(
            url,
            headers={"api-key": settings.azure_openai_api_key},
            body=body,
            timeout=timeout,
            label="Azure OpenAI chat call",
        )
        if resp.status_code >= 400:
            raise AzureOpenAIError(f"Azure OpenAI chat call failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        # One logical call, recorded once. A retried call reaches here only once
        # a response finally arrived, and a request the service refused raises
        # above before any body is read, so this counts the call that answered —
        # not each HTTP attempt, and not a call that never reached the model. The
        # usage block is passed through as the service gave it (absent when the
        # response carried none); the meter, not this client, decides who reads
        # it, and does nothing when nobody is collecting.
        record_call_usage(data.get("usage") if isinstance(data, dict) else None)
        top_choice = data["choices"][0]
        content = top_choice["message"].get("content") or ""
        truncated = top_choice.get("finish_reason") == "length"
        if not content and truncated:
            usage = data.get("usage", {})
            reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
            raise AzureOpenAIError(
                "Azure OpenAI returned empty content: the reasoning model consumed the entire "
                f"max_completion_tokens budget ({max_tokens}) on hidden reasoning "
                f"(reasoning_tokens={reasoning_tokens}) before producing visible output. "
                "Retry with a larger max_tokens value."
            )
        if truncated and json_mode:
            # Partial content plus finish_reason="length" is the silent failure
            # mode: the budget ran out mid-object, so the JSON is unterminated.
            # Callers would otherwise see a confusing parse error far from the
            # cause, or — worse — a tolerant parser could salvage a truncated
            # object and silently drop the records that never got emitted.
            # Whether the model finished is this client's business to know, so
            # refuse here rather than returning known-corrupt JSON upward.
            usage = data.get("usage", {})
            raise AzureOpenAIError(
                "Azure OpenAI returned truncated JSON: the response hit the "
                f"max_completion_tokens budget ({max_tokens}) mid-object "
                f"(completion_tokens={usage.get('completion_tokens')}, "
                f"content_chars={len(content)}). Retry with a larger max_tokens "
                "value or a smaller input batch."
            )
        return content

    async def embed(self, texts: list[str], *, deployment: str | None = None) -> list[list[float]]:
        """Embed a batch of texts, returned in the same order as the input."""

        settings = self._require_enabled()
        if not texts:
            return []
        deployment_name = deployment or settings.azure_openai_embedding_deployment
        url = (
            f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
            f"{deployment_name}/embeddings?api-version={_EMBEDDINGS_API_VERSION}"
        )
        resp = await _post_with_retry(
            url,
            headers={"api-key": settings.azure_openai_api_key},
            body={"input": texts},
            timeout=60.0,
            label="Azure OpenAI embeddings call",
        )
        if resp.status_code >= 400:
            raise AzureOpenAIError(f"Azure OpenAI embeddings call failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]
