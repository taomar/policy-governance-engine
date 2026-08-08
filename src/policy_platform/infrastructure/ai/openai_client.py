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

import httpx

from policy_platform.infrastructure.settings import Settings, get_settings

_EMBEDDINGS_API_VERSION = "2024-02-01"


class AzureOpenAIError(RuntimeError):
    """Raised when a call to Azure OpenAI fails or the resource isn't configured."""


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
        timeout: float = 120.0,
        reasoning_effort: str | None = None,
    ) -> str:
        """Single chat-completion call; returns the assistant message content.

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
        if reasoning_effort is not None:
            # Reasoning-capable deployments (gpt-5.6-sol) accept this field to
            # trade latency for deeper reasoning. Not verified against every
            # deployment — if a target deployment rejects it, callers should
            # catch AzureOpenAIError and retry without it.
            body["reasoning_effort"] = reasoning_effort

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers={"api-key": settings.azure_openai_api_key}, json=body)
        if resp.status_code >= 400:
            raise AzureOpenAIError(f"Azure OpenAI chat call failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url, headers={"api-key": settings.azure_openai_api_key}, json={"input": texts}
            )
        if resp.status_code >= 400:
            raise AzureOpenAIError(f"Azure OpenAI embeddings call failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]
