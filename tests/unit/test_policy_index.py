from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from policy_platform.infrastructure.search.policy_index import (
    PolicyIndexBuildOutcome,
    build_policy_document,
    policy_index_definition,
    policy_index_name,
    rebuild_project_policy_index,
)


def _run(coro):
    return asyncio.run(coro)


def _projection(**overrides):
    base = {
        "policy_version_id": "version-1",
        "version_number": 7,
        "provision_key": "annual-leave",
        "heading_path": ["Employee Handbook", "Annual Leave"],
        "rules": [
            {
                "id": "r1",
                "title": "Request leave",
                "statement": "Employees must request annual leave in writing.",
                "conditions": ["when an employee wants leave", {"text": "before the leave starts"}],
                "effects": [{"text": "manager approval is required"}],
            },
            {
                "id": "r2",
                "statement": "Unused leave may be carried over with approval.",
                "conditions": [],
                "effects": ["carry over is permitted"],
            },
        ],
    }
    base.update(overrides)
    return base


def _settings(*, search_enabled=True, ai_enabled=True):
    return SimpleNamespace(
        search_enabled=search_enabled,
        ai_enabled=ai_enabled,
        azure_openai_embedding_dimensions=3,
    )


class FakeOpenAI:
    async def embed(self, texts):
        self.texts = list(texts)
        return [[float(i), 0.0, 1.0] for i, _text in enumerate(texts)]


class FakeSearch:
    def __init__(self, existing_ids=()):
        self.created = []
        self.uploaded = []
        self.filters_seen = []
        self.deleted = []
        self.existing_ids = list(existing_ids)

    async def create_index(self, definition):
        self.created.append(definition)
        return definition

    async def upload_documents(self, index, documents):
        self.uploaded.append((index, list(documents)))
        return {"value": []}

    async def find_ids_by_filter(self, index, *, filter_expr, page_size=1000):
        self.filters_seen.append((index, filter_expr, page_size))
        return list(self.existing_ids)

    async def delete_documents(self, index, ids):
        self.deleted.append((index, list(ids)))
        return {"value": []}


class ExplodingSearch(FakeSearch):
    async def create_index(self, definition):
        raise RuntimeError("search unavailable")


def test_policy_index_name_is_valid_and_defensive():
    cases = [
        "ais-employee-handbook",
        "GMU Staff Handbook 2024",
        "xx",
        "___",
        "A--B!!C",
    ]

    names = [policy_index_name(case) for case in cases]

    assert len(set(names)) == len(cases)
    for name in names:
        assert name.startswith("policy-cases-")
        assert len(name) <= 128
        assert "--" not in name
        assert name[0].isalnum() and name[-1].isalnum()
        assert name == name.lower()
        assert all(char.isalnum() or char == "-" for char in name)


def test_policy_index_name_appends_digest_so_sanitized_collisions_do_not_silently_match():
    assert policy_index_name("A B") != policy_index_name("a-b")


def test_policy_index_name_truncates_with_a_digest():
    long_key = "Project " + ("Very Long Name " * 20)
    name = policy_index_name(long_key)

    assert len(name) <= 128
    assert name.endswith(policy_index_name(long_key)[-16:])


def test_index_definition_uses_existing_vector_field_and_configured_dimension():
    definition = policy_index_definition("policy-cases-test", vector_dimensions=3)
    fields = {field["name"]: field for field in definition["fields"]}

    assert fields["body_vector"]["dimensions"] == 3
    assert fields["body_vector"]["vectorSearchProfile"]
    assert "vectorSearch" in definition
    assert definition["semantic"]["defaultConfiguration"]
    assert "policy_id" in fields, "AzureSearchClient.vector_search filters this compatibility field"


def test_build_policy_document_indexes_ids_and_retrieval_text_not_payload():
    document = build_policy_document(
        policy_set_key="ais-employee-handbook",
        projection=_projection(),
        vector=[0.1, 0.2, 0.3],
    )

    assert document["policy_set_key"] == "ais-employee-handbook"
    assert document["policy_version_id"] == "version-1"
    assert document["version_number"] == 7
    assert document["provision_key"] == "annual-leave"
    assert document["heading_path"] == "Employee Handbook > Annual Leave"
    assert document["rule_count"] == 2
    assert document["body_vector"] == [0.1, 0.2, 0.3]
    assert "Request leave" in document["retrieval_text"]
    assert "manager approval is required" in document["retrieval_text"]
    assert "Unused leave may be carried over" in document["retrieval_text"]
    assert "rules" not in document
    assert "grounding_projection_v1" not in document


def test_rebuild_reports_skipped_when_search_is_disabled():
    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key="ais-employee-handbook",
            version_number=7,
            projections=[_projection()],
            settings=_settings(search_enabled=False),
            indexed_at=datetime(2026, 8, 18, tzinfo=UTC),
        )
    )

    assert outcome == PolicyIndexBuildOutcome(
        state="skipped",
        policy_set_key="ais-employee-handbook",
        index_name=policy_index_name("ais-employee-handbook"),
        version_number=7,
        document_count=0,
        indexed_at="2026-08-18T00:00:00+00:00",
    )


def test_rebuild_creates_uploads_and_removes_stale_documents():
    projection = _projection()
    live_id = build_policy_document(
        policy_set_key="ais-employee-handbook",
        projection=projection,
        vector=[0.0, 0.0, 1.0],
    )["id"]
    search = FakeSearch(existing_ids=[live_id, "stale"])
    openai = FakeOpenAI()

    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key="ais-employee-handbook",
            version_number=7,
            projections=[projection],
            settings=_settings(),
            search_client=search,
            openai_client=openai,
            indexed_at=datetime(2026, 8, 18, tzinfo=UTC),
        )
    )

    assert outcome.state == "built"
    assert outcome.document_count == 1
    assert search.created, "the rebuild must ensure the index exists before writing"
    assert len(search.uploaded[0][1]) == 1
    assert "Employees must request annual leave" in openai.texts[0]
    assert search.filters_seen == [
        (policy_index_name("ais-employee-handbook"), "policy_set_key eq 'ais-employee-handbook'", 1000)
    ]
    assert search.deleted == [(policy_index_name("ais-employee-handbook"), ["stale"])]


def test_rebuild_reports_failed_without_raising_when_search_fails():
    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key="ais-employee-handbook",
            version_number=7,
            projections=[_projection()],
            settings=_settings(),
            search_client=ExplodingSearch(),
            openai_client=FakeOpenAI(),
            indexed_at=datetime(2026, 8, 18, tzinfo=UTC),
        )
    )

    assert outcome.state == "failed"
    assert outcome.document_count == 0
    assert "search unavailable" in (outcome.error or "")
