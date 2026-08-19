"""Per-project Azure AI Search index for case-to-policy retrieval.

This module owns the callable surface only. It is deliberately not wired into
publish or teardown yet.

Input shape for one policy
--------------------------
Until the publisher-owned projection module lands, `build_policy_document`
accepts this explicit subset of a future `grounding_projection_v1` dict:

```
{
    "policy_version_id": "published version id",
    "version_number": 3,
    "provision_key": "stable policy key across versions",
    "heading_path": ["Handbook", "Leave"],
    "rules": [
        {
            "id": "rule id",
            "title": "optional generated/display title",
            "statement": "verbatim or compact rule statement",
            "conditions": ["when text", {"text": "when text"}],
            "effects": ["then text", {"text": "then text"}],
        }
    ],
}
```

The index stores ids, counts, headings, retrieval text and embeddings. It does
not store the light JSON payload: PostgreSQL remains the source of truth and the
payload is rebuilt at evaluation time.

Vector/semantic configuration note
----------------------------------
The repository contains the field used by the existing authoring index
(`body_vector`) and the embedding dimension setting, but not the live authoring
index schema. The definition below therefore uses the same vector field name and
the configured embedding dimension, with the 2025-09-01 REST field names
(`dimensions`, `vectorSearchProfile`), a standard HNSW cosine profile and a
semantic configuration over heading/retrieval text. If the live authoring index
uses different profile names, that cannot be determined from this repo alone.
"""
from __future__ import annotations

import hashlib
from json import JSONDecodeError
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import PolicyIndexState
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

POLICY_INDEX_PREFIX = "policy-cases-"
_NAME_DIGEST_CHARS = 16
_MAX_INDEX_NAME_LENGTH = 128
_MAX_RETRIEVAL_TEXT_CHARS = 12_000
_VECTOR_PROFILE = "policy-cases-vector-profile"
_VECTOR_ALGORITHM = "policy-cases-hnsw"
_SEMANTIC_CONFIG = "policy-cases-semantic"

PolicyIndexBuildState = Literal["built", "skipped", "failed"]
PolicyIndexDropState = Literal["dropped", "skipped", "failed"]
PolicyIndexLastAttempt = Literal["built", "skipped", "failed", "never_attempted"]
PolicyIndexFreshnessState = Literal["current", "stale", "nothing_to_index", "unknown"]

# Kept as two axes because constraint 5 forbids collapsing "what happened"
# into "what is usable now": a failed attempt can leave a current index, and a
# skipped attempt says nothing about freshness.
POLICY_INDEX_LAST_BUILT = "built"
POLICY_INDEX_LAST_SKIPPED = "skipped"
POLICY_INDEX_LAST_FAILED = "failed"
POLICY_INDEX_LAST_NEVER_ATTEMPTED = "never_attempted"
POLICY_INDEX_FRESHNESS_CURRENT = "current"
POLICY_INDEX_FRESHNESS_STALE = "stale"
POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX = "nothing_to_index"
POLICY_INDEX_FRESHNESS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class PolicyIndexFreshness:
    """Freshness derived from the app's recorded build state, not Azure Search.

    This is intentionally not the same mechanism as
    `ai_case_project.py`'s live retrieval guard. The retrieval path asks Azure
    whether an index exists and whether returned hits belong to the active
    approved version: "can this query safely run right now?" This derivation
    reads `policy_index_states`: "what did the app last try to build, and does
    the last recorded successful build match the active version?" They can
    legitimately disagree if the Search index is edited or deleted out of band,
    so unifying them would make either the page-load state expensive and brittle
    or the retrieval guard blind to live drift.
    """

    last_attempt: PolicyIndexLastAttempt
    freshness: PolicyIndexFreshnessState


@dataclass(frozen=True)
class PolicyIndexBuildOutcome:
    """Structured state for best-effort policy index builds.

    `state` is the headline because a bare document count cannot distinguish
    "there were no published policies" from "Search was down and nothing was
    indexed." A failed build means publish may continue, but the caller must
    report that the grounding index may be stale or absent.
    """

    state: PolicyIndexBuildState
    policy_set_key: str
    index_name: str
    version_number: int | None
    document_count: int
    indexed_at: str
    error: str | None = None


@dataclass(frozen=True)
class PolicyIndexDropOutcome:
    """Structured state for best-effort project index deletion."""

    state: PolicyIndexDropState
    policy_set_key: str
    index_name: str
    deleted: bool | None
    attempted_at: str
    error: str | None = None


def policy_index_name(policy_set_key: str) -> str:
    """Derive a valid, collision-resistant Azure Search index name for a project."""

    digest = hashlib.sha256(policy_set_key.encode("utf-8")).hexdigest()[:_NAME_DIGEST_CHARS]
    stem = re.sub(r"[^a-z0-9]+", "-", policy_set_key.lower())
    stem = re.sub(r"-{2,}", "-", stem).strip("-") or "project"

    suffix = f"-{digest}"
    available = _MAX_INDEX_NAME_LENGTH - len(POLICY_INDEX_PREFIX) - len(suffix)
    if len(stem) > available:
        stem = stem[:available].rstrip("-") or "project"
    name = f"{POLICY_INDEX_PREFIX}{stem}{suffix}"
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", name):
        raise ValueError(f"derived invalid Azure Search index name {name!r}")
    if "--" in name or len(name) > _MAX_INDEX_NAME_LENGTH:
        raise ValueError(f"derived invalid Azure Search index name {name!r}")
    return name


def policy_index_freshness(
    state: PolicyIndexState | None,
    active_version_number: int | None,
) -> PolicyIndexFreshness:
    """Derive recorded freshness without opening a database session or probing Search."""

    if state is None:
        last_attempt: PolicyIndexLastAttempt = POLICY_INDEX_LAST_NEVER_ATTEMPTED
    else:
        last_attempt = cast(PolicyIndexLastAttempt, state.status)

    if active_version_number is None:
        return PolicyIndexFreshness(
            last_attempt=last_attempt,
            freshness=POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX,
        )
    if state is None:
        return PolicyIndexFreshness(
            last_attempt=last_attempt,
            freshness=POLICY_INDEX_FRESHNESS_STALE,
        )
    if state.status == POLICY_INDEX_LAST_SKIPPED:
        return PolicyIndexFreshness(
            last_attempt=last_attempt,
            freshness=POLICY_INDEX_FRESHNESS_UNKNOWN,
        )
    if state.indexed_version_number == active_version_number:
        return PolicyIndexFreshness(
            last_attempt=last_attempt,
            freshness=POLICY_INDEX_FRESHNESS_CURRENT,
        )
    return PolicyIndexFreshness(
        last_attempt=last_attempt,
        freshness=POLICY_INDEX_FRESHNESS_STALE,
    )


def policy_index_definition(name: str, *, vector_dimensions: int | None = None) -> dict:
    """Return the Azure AI Search schema for one project's policy index."""

    dimensions = vector_dimensions or get_settings().azure_openai_embedding_dimensions
    return {
        "name": name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "retrievable": True},
            {"name": "policy_set_key", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "policy_version_id", "type": "Edm.String", "filterable": True, "retrievable": True},
            {
                "name": "version_number",
                "type": "Edm.Int32",
                "filterable": True,
                "sortable": True,
                "retrievable": True,
            },
            {"name": "provision_key", "type": "Edm.String", "searchable": True, "filterable": True, "retrievable": True},
            {"name": "heading_path", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "retrieval_text", "type": "Edm.String", "searchable": True, "retrievable": True},
            {
                "name": "body_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "retrievable": False,
                "dimensions": dimensions,
                "vectorSearchProfile": _VECTOR_PROFILE,
            },
            {"name": "rule_count", "type": "Edm.Int32", "filterable": True, "sortable": True, "retrievable": True},
            # Compatibility fields keep AzureSearchClient.vector_search usable
            # against this index without changing its live callers.
            {"name": "policy_id", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "document_id", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "document_version", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "clause_id", "type": "Edm.String", "retrievable": True},
            {"name": "clause_number", "type": "Edm.String", "retrievable": True},
            {"name": "section_heading", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "heading", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "body", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "status", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "content_type", "type": "Edm.String", "filterable": True, "retrievable": True},
        ],
        "vectorSearch": {
            "algorithms": [{"name": _VECTOR_ALGORITHM, "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
            "profiles": [{"name": _VECTOR_PROFILE, "algorithm": _VECTOR_ALGORITHM}],
        },
        "semantic": {
            "defaultConfiguration": _SEMANTIC_CONFIG,
            "configurations": [
                {
                    "name": _SEMANTIC_CONFIG,
                    "prioritizedFields": {
                        "titleField": {"fieldName": "heading"},
                        "prioritizedContentFields": [{"fieldName": "retrieval_text"}],
                        "prioritizedKeywordsFields": [{"fieldName": "provision_key"}],
                    },
                }
            ],
        },
    }


def policy_document_id(*, policy_version_id: str, provision_key: str) -> str:
    """Stable key for one published policy in the project index."""

    digest = hashlib.sha256(f"{policy_version_id}\0{provision_key}".encode("utf-8")).hexdigest()[:24]
    return f"policy-{digest}"


def build_policy_document(
    *,
    policy_set_key: str,
    projection: dict,
    vector: Sequence[float],
) -> dict:
    """Build one Azure Search document from one policy's grounding projection."""

    metadata = _projection_metadata(projection)
    policy_version_id = str(metadata["policy_version_id"])
    version_number = int(metadata["version_number"])
    provision_key = str(metadata["provision_key"])
    heading_parts = _strings(metadata.get("heading_path", []))
    rules = _projection_rules(projection)
    retrieval_text = _retrieval_text_for_projection(projection)
    heading_path = " > ".join(heading_parts)
    heading = heading_parts[-1] if heading_parts else provision_key

    return {
        "id": policy_document_id(policy_version_id=policy_version_id, provision_key=provision_key),
        "policy_set_key": policy_set_key,
        "policy_version_id": policy_version_id,
        "version_number": version_number,
        "provision_key": provision_key,
        "heading_path": heading_path,
        "retrieval_text": retrieval_text,
        "body_vector": list(vector),
        "rule_count": len(rules),
        "policy_id": provision_key,
        "document_id": policy_set_key,
        "document_version": policy_version_id,
        "clause_id": "",
        "clause_number": "",
        "section_heading": heading_path,
        "heading": heading,
        "body": retrieval_text,
        "status": "published",
        "content_type": "policy",
    }


def build_retrieval_text(*, heading_parts: Sequence[str], rules: Sequence[dict]) -> str:
    """Compose compact match text from headings plus rule titles/statements/effects."""

    parts: list[str] = []
    parts.extend(_strings(heading_parts))
    for rule in rules:
        parts.extend(_strings([rule.get("title"), rule.get("statement")]))
        parts.extend(_text_items(rule.get("conditions")))
        parts.extend(_text_items(rule.get("effects")))
    text = " \n".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))
    return text[:_MAX_RETRIEVAL_TEXT_CHARS].rstrip()


async def rebuild_project_policy_index(
    *,
    policy_set_key: str,
    version_number: int | None,
    projections: Iterable[dict],
    settings: Settings | None = None,
    search_client: AzureSearchClient | None = None,
    openai_client: AzureOpenAIClient | None = None,
    indexed_at: datetime | None = None,
) -> PolicyIndexBuildOutcome:
    """Best-effort full rebuild of one project's published-latest policy index."""

    settings = settings or get_settings()
    index_name = policy_index_name(policy_set_key)
    now = _timestamp(indexed_at)
    if not settings.search_enabled:
        return PolicyIndexBuildOutcome(
            state="skipped",
            policy_set_key=policy_set_key,
            index_name=index_name,
            version_number=version_number,
            document_count=0,
            indexed_at=now,
        )

    try:
        if not (openai_client or settings.ai_enabled):
            raise RuntimeError("Azure OpenAI embeddings are not configured")
        search_client = search_client or AzureSearchClient(settings)
        openai_client = openai_client or AzureOpenAIClient(settings)
        projection_list = list(projections)
        texts = [
            _retrieval_text_for_projection(projection)
            for projection in projection_list
        ]
        vectors = await openai_client.embed(texts) if texts else []
        documents = [
            build_policy_document(policy_set_key=policy_set_key, projection=projection, vector=vector)
            for projection, vector in zip(projection_list, vectors)
        ]

        await _create_index_accepting_empty_success(
            search_client,
            policy_index_definition(
                index_name,
                vector_dimensions=settings.azure_openai_embedding_dimensions,
            ),
        )
        await search_client.upload_documents(index_name, documents)
        indexed_ids = await search_client.find_ids_by_filter(
            index_name,
            filter_expr=f"policy_set_key eq {_odata_string(policy_set_key)}",
        )
        live_ids = {doc["id"] for doc in documents}
        stale_ids = sorted(doc_id for doc_id in indexed_ids if doc_id not in live_ids)
        if stale_ids:
            await search_client.delete_documents(index_name, stale_ids)
        return PolicyIndexBuildOutcome(
            state="built",
            policy_set_key=policy_set_key,
            index_name=index_name,
            version_number=version_number,
            document_count=len(documents),
            indexed_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - publish must not fail because Search did
        logger.warning("best-effort policy index rebuild failed for set %s: %s", policy_set_key, exc)
        return PolicyIndexBuildOutcome(
            state="failed",
            policy_set_key=policy_set_key,
            index_name=index_name,
            version_number=version_number,
            document_count=0,
            indexed_at=now,
            error=str(exc),
        )


async def read_policy_index_state(
    session: AsyncSession, *, policy_set_id: object
) -> PolicyIndexState | None:
    """The recorded build state for one project's policy index, or None.

    None means no build was ever attempted, which is a different fact from a
    build that ran and indexed nothing — `policy_index_freshness` keeps those
    apart. Reading lives here beside the write rather than in the router so the
    two stay one boundary: a caller that wants this row does not need to know
    which table holds it.
    """

    result = await session.execute(
        select(PolicyIndexState).where(PolicyIndexState.policy_set_id == policy_set_id)
    )
    return result.scalar_one_or_none()


async def record_policy_index_build_state(
    session: AsyncSession,
    *,
    policy_set_id: object,
    outcome: PolicyIndexBuildOutcome,
) -> PolicyIndexState:
    """Persist the latest rebuild attempt without lying about stale content.

    A failed rebuild updates the attempt status and error, but deliberately keeps
    the previously indexed version/document count. That is the fact the retrieval
    path needs to tell "stale relative to the active version" from "fresh but no
    match".
    """

    result = await session.execute(
        select(PolicyIndexState).where(PolicyIndexState.policy_set_id == policy_set_id)
    )
    state = result.scalar_one_or_none()
    attempted_at = _parse_timestamp(outcome.indexed_at)
    if state is None:
        state = PolicyIndexState(
            policy_set_id=policy_set_id,
            index_name=outcome.index_name,
            document_count=0,
            status=outcome.state,
            attempted_version_number=outcome.version_number,
            attempted_at=attempted_at,
        )
        session.add(state)

    state.index_name = outcome.index_name
    state.status = outcome.state
    state.attempted_version_number = outcome.version_number
    state.attempted_at = attempted_at
    state.error = outcome.error
    if outcome.state == "built":
        state.indexed_version_number = outcome.version_number
        state.document_count = outcome.document_count
        state.built_at = attempted_at
    elif outcome.state == "skipped" and state.indexed_version_number is None:
        state.document_count = 0
        state.built_at = None
    return state


def policy_index_build_outcome_payload(outcome: PolicyIndexBuildOutcome) -> dict:
    return {
        "state": outcome.state,
        "policy_set_key": outcome.policy_set_key,
        "index_name": outcome.index_name,
        "version_number": outcome.version_number,
        "document_count": outcome.document_count,
        "indexed_at": outcome.indexed_at,
        "error": outcome.error,
    }


def failed_policy_index_build_outcome(
    *,
    policy_set_key: str,
    version_number: int | None,
    error: str,
    indexed_at: datetime | None = None,
) -> PolicyIndexBuildOutcome:
    return PolicyIndexBuildOutcome(
        state="failed",
        policy_set_key=policy_set_key,
        index_name=policy_index_name(policy_set_key),
        version_number=version_number,
        document_count=0,
        indexed_at=_timestamp(indexed_at),
        error=error,
    )


async def drop_project_policy_index(
    *,
    policy_set_key: str,
    settings: Settings | None = None,
    search_client: AzureSearchClient | None = None,
    attempted_at: datetime | None = None,
) -> PolicyIndexDropOutcome:
    """Best-effort deletion of the whole per-project policy index."""

    settings = settings or get_settings()
    index_name = policy_index_name(policy_set_key)
    now = _timestamp(attempted_at)
    if not settings.search_enabled:
        return PolicyIndexDropOutcome(
            state="skipped",
            policy_set_key=policy_set_key,
            index_name=index_name,
            deleted=None,
            attempted_at=now,
        )
    try:
        search_client = search_client or AzureSearchClient(settings)
        deleted = await search_client.delete_index(index_name)
        return PolicyIndexDropOutcome(
            state="dropped",
            policy_set_key=policy_set_key,
            index_name=index_name,
            deleted=deleted,
            attempted_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - teardown must report, not hide, Search failure
        logger.warning("best-effort policy index drop failed for set %s: %s", policy_set_key, exc)
        return PolicyIndexDropOutcome(
            state="failed",
            policy_set_key=policy_set_key,
            index_name=index_name,
            deleted=None,
            attempted_at=now,
            error=str(exc),
        )


def _strings(values: object) -> list[str]:
    if isinstance(values, str):
        return [values]
    if not isinstance(values, Iterable):
        return []
    return [value for value in values if isinstance(value, str)]


def _text_items(values: object) -> list[str]:
    if isinstance(values, str):
        return [values]
    if not isinstance(values, Iterable):
        return []
    items: list[str] = []
    for value in values:
        if isinstance(value, str):
            items.append(value)
        elif isinstance(value, dict):
            items.extend(_strings([value.get("title"), value.get("statement"), value.get("text"), value.get("effect")]))
    return items


def _projection_metadata(projection: dict) -> dict:
    envelope = projection.get("envelope")
    return envelope if isinstance(envelope, dict) else projection


def _projection_rules(projection: dict) -> list[dict]:
    return [rule for rule in projection.get("rules", []) if isinstance(rule, dict)]


def _retrieval_text_for_projection(projection: dict) -> str:
    metadata = _projection_metadata(projection)
    rules = _projection_rules(projection)
    parts = [build_retrieval_text(heading_parts=_strings(metadata.get("heading_path", [])), rules=rules)]
    spans = projection.get("spans")
    if isinstance(spans, dict):
        parts.extend(_strings(item.get("text") for item in spans.values() if isinstance(item, dict)))
    facts = projection.get("facts")
    if isinstance(facts, dict):
        for item in facts.values():
            if isinstance(item, dict):
                parts.extend(_strings([item.get("name"), item.get("source_phrase")]))
    return " \n".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))[
        :_MAX_RETRIEVAL_TEXT_CHARS
    ].rstrip()


async def _create_index_accepting_empty_success(search_client: AzureSearchClient, definition: dict) -> None:
    try:
        await search_client.create_index(definition)
    except JSONDecodeError:
        # The live Search service may return a 2xx with an empty body for PUT.
        # AzureSearchClient raises before JSON parsing for non-2xx responses, so
        # this only accepts the already-successful empty-response variant.
        return


def _odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _timestamp(value: datetime | None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
