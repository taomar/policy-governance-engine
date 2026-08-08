"""Scoped, best-effort indexing of our own clauses into the shared Azure AI
Search resource.

Scoping strategy (see checkpoint / ADR): the `policy-authoring` index already
holds ~4760 unrelated documents under `policy_id = "POL-HW-001"` from another
system sharing this Search resource. To guarantee we never collide with or
misinterpret that data, every document we write uses our own
`SourceDocument.id` (a UUID) as `policy_id` — which can never equal the
string "POL-HW-001" — and every read (`search_scope.py`) restricts queries to
the set of our own document IDs. We only ever write to `policy-authoring`;
`policy-evidence` is left untouched (see docs/known-limitations.md).

Indexing is deliberately best-effort: if Azure OpenAI/Search are unavailable
or misconfigured, upload failures are logged and swallowed so a document
upload never fails because of a downstream AI/search outage.
"""
from __future__ import annotations

import logging

from policy_platform.domain.models import Clause
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


async def index_clauses_best_effort(
    *,
    document_title: str,
    document_id: str,
    document_version_id: str,
    version_number: int,
    content_hash: str,
    clauses: list[Clause],
) -> int:
    """Embed + upload `clauses` into `policy-authoring`. Returns count indexed (0 on failure)."""

    settings = get_settings()
    if not (settings.ai_enabled and settings.search_enabled) or not clauses:
        return 0

    try:
        openai_client = AzureOpenAIClient(settings)
        search_client = AzureSearchClient(settings)
        texts = [c.text for c in clauses]
        vectors = await openai_client.embed(texts)

        docs = []
        for clause, vector in zip(clauses, vectors):
            docs.append(
                {
                    "id": f"{document_version_id}_{clause.id}",
                    "policy_id": document_id,
                    "policy_version": str(version_number),
                    "policy_release_id": document_version_id,
                    "document_id": document_id,
                    "document_version": document_version_id,
                    "clause_id": str(clause.id),
                    "clause_number": clause.clause_ref,
                    "section_heading": clause.section or "",
                    "heading": document_title,
                    "body": clause.text,
                    "content_type": "clause",
                    "status": "draft",
                    "source_hash": content_hash,
                    "content_hash": content_hash,
                    "source_uri": f"local://documents/{document_id}",
                    "embedding_deployment": settings.azure_openai_embedding_deployment,
                    "embedding_dimensions": settings.azure_openai_embedding_dimensions,
                    "body_vector": vector,
                }
            )

        indexed = 0
        for i in range(0, len(docs), _BATCH_SIZE):
            batch = docs[i : i + _BATCH_SIZE]
            await search_client.upload_documents(settings.azure_search_authoring_index, batch)
            indexed += len(batch)
        return indexed
    except Exception as exc:  # noqa: BLE001 - indexing must never break the upload flow
        logger.warning("best-effort search indexing failed for document %s: %s", document_id, exc)
        return 0
