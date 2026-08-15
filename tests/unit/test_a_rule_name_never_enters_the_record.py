"""A generated name for a rule is commentary, and commentary is not evidence.

A candidate rule is a claim about what a document states. A name for that rule
is ours: nobody wrote it in the document and no extraction produced it. It
exists so a reviewer can tell one rule from its neighbours on a card.

So it may be stored -- generating it on every render would be slow and costly --
but it is stored *beside* the record, in its own table, and it may never travel
with the record. If it ever did, an export or a published policy would carry
words the document never stated, attributed by position to the document.

Two tests hold that line from different directions.

The first is behavioural: a name is stored for a real rule with a distinctive
text, the real export endpoint is called, and the text must be absent. A third
test proves that scan can fail, by putting the same text where a payload's own
words go and watching the export carry it.

The second is structural, and is the one that survives new code. The export is
not the only way out of the database; there are assembled reads, publishing, a
JSON view. Rather than chase each, this asserts that only four modules in the
whole source tree can even name the storage -- the model that declares it, the
generator that writes it, the read module that serves it, and the AI router
that exposes that read. Any other module gaining the ability to reach a name is
a decision that has to be made deliberately, by editing this list.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.api.routers.candidate_rules import _to_response, export_candidate_rules
from policy_platform.domain.models import CandidateRule, CandidateRuleName, PolicySet

SRC = Path(__file__).resolve().parents[2] / "src" / "policy_platform"

#: A real extracted record, because the export validates the payload against
#: the canonical contract on the way out. A hand-written stand-in would only
#: prove that an invalid record fails to serialize.
CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "ad103_rules.json"


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# tables be created, so the real columns are exercised rather than a stand-in.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


#: A string no document, no payload and no serializer would produce on its own,
#: so finding it anywhere means it travelled from the name table.
SENTINEL = "Quorum-thresholds-for-Kestrel-Bay-zzq"

POLICY_SET = uuid.UUID(int=7)
RUN = uuid.UUID(int=8)
KEY = "a-policy-set"


def _payload() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))[0]


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (PolicySet, CandidateRule, CandidateRuleName):
            await connection.run_sync(
                lambda sync, table=table: table.__table__.create(sync, checkfirst=True)
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def _populate(session, *, payload: dict) -> uuid.UUID:
    session.add(
        PolicySet(id=POLICY_SET, key=KEY, name="A policy set", owner="someone", description="")
    )
    rule = CandidateRule(
        id=uuid.uuid4(),
        policy_set_id=POLICY_SET,
        extraction_run_id=RUN,
        rule_type="obligation",
        payload_json=payload,
        review_status="candidate",
    )
    session.add(rule)
    await session.commit()
    return rule.id


async def _export(session, fmt: str) -> str:
    response = await export_candidate_rules(key=KEY, format=fmt, session=session)
    return response.body.decode("utf-8")


class TestAStoredNameStaysOutOfTheRecord:
    async def test_the_export_does_not_carry_it(self, session) -> None:
        rule_id = await _populate(session, payload=_payload())
        session.add(
            CandidateRuleName(
                id=uuid.uuid4(),
                candidate_rule_id=rule_id,
                name_text=SENTINEL,
                model_deployment="a-deployment",
                prompt_version="a-version",
                source_digest="a-digest",
                generated_at=datetime.now(UTC),
            )
        )
        await session.commit()

        for fmt in ("json", "jsonl", "csv"):
            assert SENTINEL not in await _export(session, fmt), fmt

    async def test_the_rule_response_does_not_carry_it(self, session) -> None:
        rule_id = await _populate(session, payload=_payload())
        session.add(
            CandidateRuleName(
                id=uuid.uuid4(),
                candidate_rule_id=rule_id,
                name_text=SENTINEL,
                model_deployment="a-deployment",
                prompt_version="a-version",
                source_digest="a-digest",
                generated_at=datetime.now(UTC),
            )
        )
        await session.commit()

        candidate = await session.get(CandidateRule, rule_id)
        served = json.dumps(_to_response(candidate).model_dump(mode="json"), ensure_ascii=False)
        assert SENTINEL not in served

    async def test_the_export_would_have_shown_it(self, session) -> None:
        """Guard the guard: the scan above passes over an export that can fail.

        Without this, an export that quietly returned nothing would satisfy
        every assertion in this file.
        """
        payload = _payload() | {"title": SENTINEL}
        await _populate(session, payload=payload)

        for fmt in ("json", "jsonl", "csv"):
            assert SENTINEL in await _export(session, fmt), fmt


#: The only modules allowed to reach a stored name. Each is here for a stated
#: reason, and a fifth entry is a decision rather than an accident.
_MAY_REACH_A_NAME = {
    SRC / "domain" / "models.py",  # declares the table
    SRC / "infrastructure" / "assistants" / "rule_namer.py",  # writes it
    SRC / "infrastructure" / "assembly" / "rule_name_lookup.py",  # reads it
    SRC / "api" / "routers" / "ai.py",  # serves that read, and nothing else
}

#: How a name can be obtained. A module that mentions neither of these has no
#: way to put a name into anything it builds.
_REACHES = ("CandidateRuleName", "rule_name_lookup")

#: Naming the table in SQL is not the same as reading a name out of it, and one
#: more module does the first: teardown, which deletes these rows with the rule
#: they describe. A DELETE cannot carry a name anywhere.
_MAY_NAME_THE_TABLE = _MAY_REACH_A_NAME | {
    SRC / "infrastructure" / "persistence" / "policy_set_teardown.py",
}
_TABLE = "candidate_rule_names"


def _python_files() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


class TestNothingElseCanReachAName:
    def test_only_the_four_modules_can_obtain_one(self) -> None:
        scanned = _python_files()
        # A floor, so a scan that silently found nothing would fail here rather
        # than pass everything below.
        assert len(scanned) > 100, len(scanned)

        offenders = {
            path.relative_to(SRC).as_posix()
            for path in scanned
            if path not in _MAY_REACH_A_NAME
            and any(token in path.read_text(encoding="utf-8") for token in _REACHES)
        }
        assert offenders == set(), sorted(offenders)

    def test_only_those_and_teardown_name_the_table(self) -> None:
        offenders = {
            path.relative_to(SRC).as_posix()
            for path in _python_files()
            if path not in _MAY_NAME_THE_TABLE and _TABLE in path.read_text(encoding="utf-8")
        }
        assert offenders == set(), sorted(offenders)

    def test_each_allowed_module_still_earns_its_place(self) -> None:
        """An entry that no longer reaches a name is a standing permission."""

        for path in sorted(_MAY_NAME_THE_TABLE):
            assert path.exists(), path
            text = path.read_text(encoding="utf-8")
            assert any(token in text for token in (*_REACHES, _TABLE)), path

    def test_the_scan_would_notice_a_module_that_reached_one(self) -> None:
        """Guard the guard, over the same tokens the scan above uses."""

        pretend = "\n".join(f"from x import {token}" for token in _REACHES)
        assert any(token in pretend for token in _REACHES)
