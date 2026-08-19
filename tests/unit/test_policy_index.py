from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from json import JSONDecodeError
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.domain.models import Base, PolicyIndexState, PolicySet
from policy_platform.infrastructure.search.policy_index import (
    POLICY_INDEX_FRESHNESS_CURRENT,
    POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX,
    POLICY_INDEX_FRESHNESS_STALE,
    POLICY_INDEX_FRESHNESS_UNKNOWN,
    POLICY_INDEX_LAST_BUILT,
    POLICY_INDEX_LAST_FAILED,
    POLICY_INDEX_LAST_NEVER_ATTEMPTED,
    POLICY_INDEX_LAST_SKIPPED,
    PolicyIndexBuildOutcome,
    build_policy_document,
    policy_index_freshness,
    policy_index_definition,
    policy_index_name,
    rebuild_project_policy_index,
    record_policy_index_build_state,
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


class EmptySuccessSearch(FakeSearch):
    async def create_index(self, definition):
        raise JSONDecodeError("Expecting value", "", 0)


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


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


def test_policy_index_freshness_keeps_last_attempt_and_current_state_orthogonal():
    built_current = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000211"),
        index_name=policy_index_name("handbook"),
        status=POLICY_INDEX_LAST_BUILT,
        indexed_version_number=6,
        document_count=10,
        attempted_version_number=6,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
    )
    failed_stale = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000212"),
        index_name=policy_index_name("handbook"),
        status=POLICY_INDEX_LAST_FAILED,
        indexed_version_number=5,
        document_count=9,
        attempted_version_number=6,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
        error="search unavailable",
    )
    failed_still_current = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000213"),
        index_name=policy_index_name("handbook"),
        status=POLICY_INDEX_LAST_FAILED,
        indexed_version_number=6,
        document_count=10,
        attempted_version_number=6,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
        error="post-build cleanup failed",
    )
    skipped = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000214"),
        index_name=policy_index_name("handbook"),
        status=POLICY_INDEX_LAST_SKIPPED,
        indexed_version_number=None,
        document_count=0,
        attempted_version_number=6,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
    )

    assert policy_index_freshness(built_current, 6).last_attempt == POLICY_INDEX_LAST_BUILT
    assert policy_index_freshness(built_current, 6).freshness == POLICY_INDEX_FRESHNESS_CURRENT
    assert policy_index_freshness(failed_stale, 6).last_attempt == POLICY_INDEX_LAST_FAILED
    assert policy_index_freshness(failed_stale, 6).freshness == POLICY_INDEX_FRESHNESS_STALE
    assert policy_index_freshness(failed_still_current, 6).last_attempt == POLICY_INDEX_LAST_FAILED
    assert policy_index_freshness(failed_still_current, 6).freshness == POLICY_INDEX_FRESHNESS_CURRENT
    assert policy_index_freshness(skipped, 6).last_attempt == POLICY_INDEX_LAST_SKIPPED
    assert policy_index_freshness(skipped, 6).freshness == POLICY_INDEX_FRESHNESS_UNKNOWN
    assert policy_index_freshness(None, 6).last_attempt == POLICY_INDEX_LAST_NEVER_ATTEMPTED
    assert policy_index_freshness(None, 6).freshness == POLICY_INDEX_FRESHNESS_STALE


def test_a_skipped_attempt_still_reports_a_version_the_record_can_prove_is_behind():
    """Skipping does not erase what was last indexed, so do not discard the comparison.

    `record_policy_index_build_state` deliberately preserves
    `indexed_version_number` across a skipped attempt. When that version is
    known, comparing it against the active one is as sound here as it is for a
    failed attempt, and answering `unknown` would throw away a staleness the
    record can prove -- while the surface above it lists Active v7 and Indexed
    v6 side by side.

    `unknown` is kept for the case it actually describes: skipped with nothing
    ever indexed, where there is no version to compare and claiming `stale`
    would assert a comparison never made.
    """

    def _skipped(indexed: int | None) -> PolicyIndexState:
        return PolicyIndexState(
            policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000218"),
            index_name=policy_index_name("handbook"),
            status=POLICY_INDEX_LAST_SKIPPED,
            indexed_version_number=indexed,
            document_count=0 if indexed is None else 4,
            attempted_version_number=7,
            attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
        )

    behind = policy_index_freshness(_skipped(6), 7)
    assert behind.last_attempt == POLICY_INDEX_LAST_SKIPPED
    assert behind.freshness == POLICY_INDEX_FRESHNESS_STALE

    matching = policy_index_freshness(_skipped(7), 7)
    assert matching.freshness == POLICY_INDEX_FRESHNESS_CURRENT

    never_indexed = policy_index_freshness(_skipped(None), 7)
    assert never_indexed.freshness == POLICY_INDEX_FRESHNESS_UNKNOWN


def test_policy_index_freshness_reports_no_active_version_as_nothing_to_index():
    built_without_active_version = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000216"),
        index_name=policy_index_name("xx"),
        status=POLICY_INDEX_LAST_BUILT,
        indexed_version_number=None,
        document_count=0,
        attempted_version_number=None,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
    )
    failed_without_active_version = PolicyIndexState(
        policy_set_id=uuid.UUID("00000000-0000-4000-8000-000000000215"),
        index_name=policy_index_name("xx"),
        status=POLICY_INDEX_LAST_FAILED,
        indexed_version_number=None,
        document_count=0,
        attempted_version_number=None,
        attempted_at=datetime(2026, 8, 18, tzinfo=UTC),
        error="search unavailable",
    )

    assert policy_index_freshness(None, None).last_attempt == POLICY_INDEX_LAST_NEVER_ATTEMPTED
    assert policy_index_freshness(None, None).freshness == POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX
    assert policy_index_freshness(built_without_active_version, None).last_attempt == POLICY_INDEX_LAST_BUILT
    assert policy_index_freshness(built_without_active_version, None).freshness == POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX
    assert policy_index_freshness(failed_without_active_version, None).last_attempt == POLICY_INDEX_LAST_FAILED
    assert policy_index_freshness(failed_without_active_version, None).freshness == POLICY_INDEX_FRESHNESS_NOTHING_TO_INDEX


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


def test_build_policy_document_accepts_published_payload_envelope_shape():
    document = build_policy_document(
        policy_set_key="ais-employee-handbook",
        projection={
            "envelope": {
                "policy_version_id": "version-6",
                "version_number": 6,
                "provision_key": "conduct",
                "heading_path": ["Handbook", "Conduct"],
            },
            "spans": {"s1": {"text": "Employees must disclose conflicts."}},
            "facts": {"employee": {"name": "employee", "source_phrase": "Employees"}},
            "rules": [
                {
                    "rule_id": "AI-1",
                    "attributes": {"applies": [{"text": "Employees"}], "outcome": [{"text": "disclose"}]},
                    "effect": {"action": "must disclose"},
                }
            ],
        },
        vector=[0.1, 0.2, 0.3],
    )

    assert document["policy_version_id"] == "version-6"
    assert document["version_number"] == 6
    assert document["provision_key"] == "conduct"
    assert "Employees must disclose conflicts." in document["retrieval_text"]


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


def test_rebuild_accepts_empty_success_response_from_index_create():
    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key="ais-employee-handbook",
            version_number=7,
            projections=[_projection()],
            settings=_settings(),
            search_client=EmptySuccessSearch(),
            openai_client=FakeOpenAI(),
            indexed_at=datetime(2026, 8, 18, tzinfo=UTC),
        )
    )

    assert outcome.state == "built"
    assert outcome.document_count == 1


def test_record_policy_index_build_state_keeps_last_successful_version_when_next_build_fails():
    async def _case():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                policy_set = PolicySet(
                    id=uuid.UUID("00000000-0000-4000-8000-000000000201"),
                    key="handbook",
                    name="Handbook",
                    owner="policy",
                )
                session.add(policy_set)
                await session.flush()
                await record_policy_index_build_state(
                    session,
                    policy_set_id=policy_set.id,
                    outcome=PolicyIndexBuildOutcome(
                        state="built",
                        policy_set_key="handbook",
                        index_name=policy_index_name("handbook"),
                        version_number=6,
                        document_count=10,
                        indexed_at="2026-08-18T12:00:00+00:00",
                    ),
                )
                await record_policy_index_build_state(
                    session,
                    policy_set_id=policy_set.id,
                    outcome=PolicyIndexBuildOutcome(
                        state="failed",
                        policy_set_key="handbook",
                        index_name=policy_index_name("handbook"),
                        version_number=7,
                        document_count=0,
                        indexed_at="2026-08-18T13:00:00+00:00",
                        error="search unavailable",
                    ),
                )
                state = (await session.execute(select(PolicyIndexState))).scalar_one()
                assert state.status == "failed"
                assert state.attempted_version_number == 7
                assert state.indexed_version_number == 6
                assert state.document_count == 10
                assert state.error == "search unavailable"
        finally:
            await engine.dispose()

    _run(_case())
