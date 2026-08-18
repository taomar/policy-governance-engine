"""Thin async Azure AI Search client (direct httpx REST calls, no SDK dependency).

Talks to Azure AI Search directly. Most existing callers use the two shared
indexes (`policy-authoring`, `policy-evidence`) and only read/write documents.
Per-project policy indexes additionally use the management endpoints below.
See `infrastructure/search/indexing.py` for the scoping strategy that keeps
shared-index writes/reads isolated from the resource's pre-existing unrelated
data.
"""
from __future__ import annotations

import httpx

from policy_platform.infrastructure.settings import Settings, get_settings


class AzureSearchError(RuntimeError):
    """Raised when a call to Azure AI Search fails or the resource isn't configured."""


class AzureSearchClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.search_enabled

    def _require_enabled(self) -> Settings:
        if not self.enabled:
            raise AzureSearchError("Azure AI Search is not configured (missing endpoint/api key in .env)")
        return self._settings

    def _headers(self) -> dict:
        return {"api-key": self._settings.azure_search_api_key, "Content-Type": "application/json"}

    async def create_index(self, definition: dict) -> dict:
        """Create or replace an index definition by name (Azure Search PUT semantics)."""

        settings = self._require_enabled()
        name = definition.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AzureSearchError("Azure Search index definition must include a non-empty name")
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{name}"
            f"?api-version={settings.azure_search_api_version}"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.put(url, headers=self._headers(), json=definition)
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search index create failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    async def delete_index(self, name: str) -> bool:
        """Delete an index by name. An index that is already absent is success."""

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{name}"
            f"?api-version={settings.azure_search_api_version}"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.delete(url, headers=self._headers())
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search index delete failed ({resp.status_code}): {resp.text[:500]}")
        return True

    async def index_exists(self, name: str) -> bool:
        """Return whether an index exists."""

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{name}"
            f"?api-version={settings.azure_search_api_version}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._headers())
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search index lookup failed ({resp.status_code}): {resp.text[:500]}")
        return True

    async def upload_documents(self, index: str, documents: list[dict]) -> dict:
        """mergeOrUpload a batch of documents (safe to call repeatedly/idempotently)."""

        settings = self._require_enabled()
        if not documents:
            return {"value": []}
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/index"
            f"?api-version={settings.azure_search_api_version}"
        )
        body = {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in documents]}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search upload failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    async def find_ids_by_filter(self, index: str, *, filter_expr: str, page_size: int = 1000) -> list[str]:
        """Return every document `id` matching an OData filter (paged). Used to locate
        stale documents (e.g. from a superseded clause-extraction run) that need
        deleting before re-indexing a corrected replacement set."""

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/search"
            f"?api-version={settings.azure_search_api_version}"
        )
        ids: list[str] = []
        skip = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                body = {"search": "*", "filter": filter_expr, "select": "id", "top": page_size, "skip": skip}
                resp = await client.post(url, headers=self._headers(), json=body)
                if resp.status_code >= 400:
                    raise AzureSearchError(f"Azure Search query failed ({resp.status_code}): {resp.text[:500]}")
                batch = resp.json().get("value", [])
                ids.extend(doc["id"] for doc in batch)
                if len(batch) < page_size:
                    break
                skip += page_size
        return ids

    async def delete_documents(self, index: str, ids: list[str]) -> dict:
        """Delete documents by key. Safe to call with an empty list."""

        settings = self._require_enabled()
        if not ids:
            return {"value": []}
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/index"
            f"?api-version={settings.azure_search_api_version}"
        )
        body = {"value": [{"@search.action": "delete", "id": doc_id} for doc_id in ids]}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search delete failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    async def vector_search(
        self,
        index: str,
        *,
        query_text: str,
        vector: list[float],
        policy_ids: list[str] | None = None,
        top: int = 6,
    ) -> list[dict]:
        """Hybrid keyword + vector search, optionally scoped to specific `policy_id` values."""

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/search"
            f"?api-version={settings.azure_search_api_version}"
        )
        body: dict = {
            "search": query_text,
            "vectorQueries": [{"kind": "vector", "vector": vector, "fields": "body_vector", "k": top}],
            "top": top,
            "select": (
                "id,policy_id,document_id,document_version,clause_id,clause_number,"
                "section_heading,heading,body,status"
            ),
        }
        if policy_ids:
            if len(policy_ids) == 1:
                body["filter"] = f"policy_id eq '{policy_ids[0]}'"
            else:
                # search.in expects a plain delimiter-separated value list (no quoting
                # per-value); safe here since our policy_ids are UUIDs (no commas/pipes).
                id_list = ",".join(policy_ids)
                body["filter"] = f"search.in(policy_id, '{id_list}', ',')"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search query failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json().get("value", [])
