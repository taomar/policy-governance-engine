from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from policy_platform.infrastructure.search import search_client
from policy_platform.infrastructure.search.search_client import AzureSearchClient, AzureSearchError


def _run(coro):
    return asyncio.run(coro)


def _settings(*, enabled: bool = True):
    return SimpleNamespace(
        search_enabled=enabled,
        azure_search_endpoint="https://search.example",
        azure_search_api_key="key",
        azure_search_api_version="2025-09-01",
    )


class _Transport:
    def __init__(self, responses: list[httpx.Response], calls: list[tuple[str, str, dict | None]]):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def put(self, url, *, headers=None, json=None):
        self._calls.append(("PUT", url, json))
        return self._responses.pop(0)

    async def get(self, url, *, headers=None):
        self._calls.append(("GET", url, None))
        return self._responses.pop(0)

    async def delete(self, url, *, headers=None):
        self._calls.append(("DELETE", url, None))
        return self._responses.pop(0)


def _response(status: int, body: dict | str = "") -> httpx.Response:
    content = body if isinstance(body, str) else httpx.Response(200, json=body).content
    return httpx.Response(status, content=content, request=httpx.Request("GET", "https://search.example"))


def test_create_index_puts_the_definition(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(
        search_client.httpx,
        "AsyncClient",
        lambda **_kw: _Transport([_response(201, {"name": "policy-cases-x"})], calls),
    )

    result = _run(AzureSearchClient(_settings()).create_index({"name": "policy-cases-x", "fields": []}))

    assert result == {"name": "policy-cases-x"}
    assert calls == [
        (
            "PUT",
            "https://search.example/indexes/policy-cases-x?api-version=2025-09-01",
            {"name": "policy-cases-x", "fields": []},
        )
    ]


def test_create_index_requires_a_name():
    with pytest.raises(AzureSearchError, match="non-empty name"):
        _run(AzureSearchClient(_settings()).create_index({"fields": []}))


def test_index_exists_distinguishes_present_absent_and_error(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    responses = [_response(200, {"name": "present"}), _response(404), _response(500, "boom")]
    monkeypatch.setattr(
        search_client.httpx,
        "AsyncClient",
        lambda **_kw: _Transport(responses, calls),
    )
    client = AzureSearchClient(_settings())

    assert _run(client.index_exists("present")) is True
    assert _run(client.index_exists("absent")) is False
    with pytest.raises(AzureSearchError, match="lookup failed"):
        _run(client.index_exists("broken"))


def test_delete_index_treats_absent_as_success(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    responses = [_response(204), _response(404)]
    monkeypatch.setattr(
        search_client.httpx,
        "AsyncClient",
        lambda **_kw: _Transport(responses, calls),
    )
    client = AzureSearchClient(_settings())

    assert _run(client.delete_index("present")) is True
    assert _run(client.delete_index("absent")) is False


def test_index_management_requires_search_configuration():
    client = AzureSearchClient(_settings(enabled=False))

    with pytest.raises(AzureSearchError, match="not configured"):
        _run(client.index_exists("x"))
