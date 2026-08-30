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

    async def find_documents_by_filter(
        self,
        index: str,
        *,
        filter_expr: str,
        select: str,
        page_size: int = 200,
    ) -> list[dict]:
        """Return every document matching an OData filter, with named fields, paged.

        The sibling of :meth:`find_ids_by_filter`, and it exists for one caller:
        validating a projection that is *already built* means reading what the
        index actually holds rather than what a build believed it wrote. Ids
        alone cannot answer that — the question is whether each document's
        retrieval text is a rendering of the record it names, so the text and the
        identifying fields have to come back with it.

        ``select`` is required rather than defaulted. A validation reads a few
        named fields over a whole corpus, and a lookup that silently returned
        every retrievable field would move megabytes to answer a question about
        kilobytes.
        """

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/search"
            f"?api-version={settings.azure_search_api_version}"
        )
        documents: list[dict] = []
        skip = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                body = {
                    "search": "*",
                    "filter": filter_expr,
                    "select": select,
                    "top": page_size,
                    "skip": skip,
                }
                resp = await client.post(url, headers=self._headers(), json=body)
                if resp.status_code >= 400:
                    raise AzureSearchError(
                        f"Azure Search query failed ({resp.status_code}): {resp.text[:500]}"
                    )
                batch = resp.json().get("value", [])
                documents.extend(batch)
                if len(batch) < page_size:
                    break
                skip += page_size
        return documents

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
        filter_expr: str | None = None,
        select: str | None = None,
    ) -> list[dict]:
        """Hybrid keyword + vector search, optionally scoped to specific `policy_id` values.

        ``filter_expr`` is an OData expression composed by the caller — the
        per-project index needs to scope a query to one *kind* of document and to
        one projection profile, and the expression that does that belongs with
        the schema that names those fields (`search/policy_index.py`), not here.
        It is combined with ``policy_ids`` by conjunction when both are given, so
        neither can widen the other.

        ``select`` overrides the returned field list for callers that need fields
        outside the shared default — a rule document's `rule_id`, its ordinal and
        its parent. Left absent, every existing caller gets the field list it
        always got.
        """

        settings = self._require_enabled()
        url = (
            f"{settings.azure_search_endpoint.rstrip('/')}/indexes/{index}/docs/search"
            f"?api-version={settings.azure_search_api_version}"
        )
        body: dict = {
            "search": query_text,
            "vectorQueries": [{"kind": "vector", "vector": vector, "fields": "body_vector", "k": top}],
            "top": top,
            "select": select
            or (
                "id,policy_id,document_id,document_version,clause_id,clause_number,"
                "section_heading,heading,body,status"
            ),
        }
        clauses: list[str] = []
        if policy_ids:
            if len(policy_ids) == 1:
                clauses.append(f"policy_id eq '{policy_ids[0]}'")
            else:
                # search.in expects a plain delimiter-separated value list (no quoting
                # per-value); safe here since our policy_ids are UUIDs (no commas/pipes).
                id_list = ",".join(policy_ids)
                clauses.append(f"search.in(policy_id, '{id_list}', ',')")
        if filter_expr:
            clauses.append(f"({filter_expr})")
        if clauses:
            body["filter"] = " and ".join(clauses)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise AzureSearchError(f"Azure Search query failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json().get("value", [])
