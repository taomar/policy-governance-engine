from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    RuleFormulation,
)
from policy_platform.contracts.policy import EvidenceReference, RuleLineage
from policy_platform.domain.models import Base, DocumentVersion, PolicySet, SourceDocument
from policy_platform.infrastructure.persistence.policy_version_import import import_approved_policy_version
from policy_platform.infrastructure.persistence.provision_snapshot import ProvisionSnapshot
from policy_platform.infrastructure.projection.policy_case_payload import PROJECTION, to_compact
from policy_platform.infrastructure.projection.published_case_payload import (
    published_case_payload_for_policy,
    published_case_payloads_for_policy_set,
)
from tests.fixtures.factories import make_rule


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_SET_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")
_DOC_ID = uuid.UUID("00000000-0000-4000-8000-000000000102")
_DOC_VERSION_ID = uuid.UUID("00000000-0000-4000-8000-000000000103")
_EMPTY = AllCondition(all=[])


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


def _rule(rule_id: str, quote: str, subject: str, *, rule_date: date = date(2024, 1, 1)):
    canonical = CanonicalPolicy(
        source_text=quote,
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject=subject,
            modality="must",
            predicate="follow",
            object="the policy",
        ),
    )
    return make_rule(rule_id, _EMPTY, effective_from=rule_date).model_copy(
        update={
            "description": quote,
            "formulation": RuleFormulation(canonical=canonical),
            "evidence": [
                EvidenceReference(
                    document_version_id=str(_DOC_VERSION_ID),
                    source_hash=f"{rule_id}-hash",
                    page=1,
                    section="Section 1",
                    clause_id=None,
                    start_offset=0,
                    end_offset=len(quote),
                )
            ],
            "lineage": RuleLineage(source_elements="E000001"),
        }
    )


async def _seed(session: AsyncSession):
    session.add(PolicySet(id=_SET_ID, key="handbook", name="Handbook", owner="policy"))
    session.add(SourceDocument(id=_DOC_ID, title="Handbook", owner="policy", policy_set_id=_SET_ID))
    session.add(
        DocumentVersion(
            id=_DOC_VERSION_ID,
            document_id=_DOC_ID,
            version_number=1,
            content_hash="d" * 64,
            storage_path="handbook.pdf",
        )
    )
    await session.flush()

    old = _rule("AI-old", "Old published wording.", "employee")
    await import_approved_policy_version(
        session,
        policy_set_id=_SET_ID,
        version_number=1,
        effective_from=date(2023, 1, 1),
        effective_to=None,
        approved_by="reviewer",
        is_active=False,
        rules=[old],
        provisions={"AI-old": ProvisionSnapshot("old-policy", ["Old policy"])},
    )

    rules = [
        _rule("AI-alpha-2", "The employee must follow the leave policy.", "employee"),
        _rule("AI-alpha-1", "يجب على الموظف اتباع سياسة الإجازات.", "الموظف"),
        _rule("AI-beta-1", "Managers must approve exceptions.", "Managers", rule_date=date(2025, 2, 1)),
    ]
    version = await import_approved_policy_version(
        session,
        policy_set_id=_SET_ID,
        version_number=2,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        approved_by="reviewer",
        is_active=True,
        rules=rules,
        provisions={
            "AI-alpha-1": ProvisionSnapshot("alpha-policy", ["1. Leave"]),
            "AI-alpha-2": ProvisionSnapshot("alpha-policy", ["1. Leave"]),
            "AI-beta-1": ProvisionSnapshot("beta-policy", ["2. Exceptions"]),
        },
    )
    await session.commit()
    return version


@pytest.mark.asyncio
async def test_published_payloads_are_grouped_by_policy_in_the_active_version() -> None:
    session, engine = await _session()
    try:
        version = await _seed(session)

        payloads = await published_case_payloads_for_policy_set(session, "handbook")

        assert [payload["envelope"]["provision_key"] for payload in payloads] == [
            "alpha-policy",
            "beta-policy",
        ]
        assert [len(payload["rules"]) for payload in payloads] == [2, 1]
        assert {rule["rule_id"] for payload in payloads for rule in payload["rules"]} == {
            "AI-alpha-1",
            "AI-alpha-2",
            "AI-beta-1",
        }
        assert all(payload["projection"] == PROJECTION for payload in payloads)

        alpha = payloads[0]
        assert alpha["envelope"]["policy_set_id"] == str(_SET_ID)
        assert alpha["envelope"]["policy_version_id"] == str(version.id)
        assert alpha["envelope"]["version_number"] == 2
        assert alpha["envelope"]["effective_from"] == "2025-01-01"
        assert alpha["envelope"]["effective_to"] is None
        assert alpha["envelope"]["heading_path"] == ["1. Leave"]
        assert "يجب على الموظف اتباع سياسة الإجازات." in to_compact(alpha)

        beta_rule = payloads[1]["rules"][0]
        assert beta_rule["effective_from"] == "2025-02-01"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_one_policy_helper_returns_none_when_the_policy_or_active_version_is_absent() -> None:
    session, engine = await _session()
    try:
        await _seed(session)

        alpha = await published_case_payload_for_policy(session, _SET_ID, "alpha-policy")
        assert alpha is not None
        assert alpha["envelope"]["provision_key"] == "alpha-policy"
        assert await published_case_payload_for_policy(session, _SET_ID, "missing-policy") is None
        assert await published_case_payloads_for_policy_set(session, "missing-set") == []
    finally:
        await session.close()
        await engine.dispose()
