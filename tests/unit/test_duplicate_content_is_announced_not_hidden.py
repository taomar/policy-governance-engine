"""Uploading bytes the register already holds must be *announced*, not hidden.

The upload endpoint deduplicates: re-uploading identical bytes for the *same*
document (same title, same project) is refused with 409. That is correct and
stays. What this test pins down is the seam the 409 does not cover.

The register deliberately allows the same bytes to be registered again under a
different title, owner, or project -- an archived snapshot of a handbook, a
re-parse under a new parser, or one source serving two projects. Measurement of
the live database shows this is a capability in active use, not a corner case,
so refusing those uploads would remove something real (that trade is off the
table). The defect is quieter: the second upload succeeds with a plain success
and *no indication* that the register now holds the same source twice. To
whoever maintains a compliance register, "this is new content" and "you already
have these exact bytes under another name" are different facts, and reporting
the second as the first is a lie by omission.

So the endpoint must positively distinguish three states for the caller:

  * new content            -> the register held no other copy (checked, empty)
  * already-present content -> the register already holds these bytes elsewhere
  * refused                -> identical re-upload of *this* document (409)

An empty result for the first is load-bearing and must be distinct from
absence: it says the lookup ran and found nothing, not that the question went
unasked -- the same []-vs-None discipline the version's ingestion diagnostics
already keep.

The assertions here are structural (empty vs non-empty; the announced id equals
the id the first upload returned) and use only synthetic bytes and titles, so no
observed hash, count, or document name leaks into the test.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

# `api.app` builds Settings (which needs a database URL) at import time. Set it
# before importing, so collection does not depend on a local .env; the URL is
# never connected to because every session is overridden below.
os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******/test")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from policy_platform.api import app as app_module  # noqa: E402
from policy_platform.api.app import create_app  # noqa: E402
from policy_platform.api.routers import documents as documents_router  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    Clause,
    DocumentVersion,
    SourceDocument,
)
from policy_platform.infrastructure.ingestion import document_extraction  # noqa: E402
from policy_platform.infrastructure.persistence.db import get_session  # noqa: E402

assert app_module  # imported for its import-time side effects only


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


def _stub_extraction(*_args, **_kwargs):
    # Extraction is non-blocking and orthogonal to the dedup/announce boundary
    # under test. Raising here exercises the endpoint's own error path (caught,
    # upload still succeeds) without pulling a real parser into the test.
    raise RuntimeError("extraction stubbed out; not under test")


async def _upload(http: AsyncClient, *, title: str, owner: str, content: bytes):
    response = await http.post(
        "/api/documents/upload",
        params={"title": title, "owner": owner},
        files={"file": (f"{uuid.uuid4().hex}.bin", content, "application/octet-stream")},
    )
    body = response.json() if response.content else {}
    return response.status_code, body


async def test_reuploading_known_bytes_under_a_new_title_is_announced(monkeypatch) -> None:
    scratch = Path("data") / "documents" / f"_dedup_scratch_{uuid.uuid4().hex}"
    monkeypatch.setattr(documents_router, "_STORAGE_ROOT", scratch)
    monkeypatch.setattr(document_extraction, "extract_document", _stub_extraction)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            for table in (
                SourceDocument.__table__,
                DocumentVersion.__table__,
                Clause.__table__,
            ):
                await connection.run_sync(lambda c, t=table: t.create(c, checkfirst=True))

        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()

        async def _override():
            async with maker() as session:
                yield session

        app.dependency_overrides[get_session] = _override

        title_a = "Alpha Policy"
        title_b = "Beta Handbook"
        title_c = "Gamma Notes"
        shared_bytes = b"synthetic source bytes -- identical across two registrations"
        other_bytes = b"a completely different synthetic source document"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:
            # State 1: content the register has never seen. The announcement must
            # be an *empty* list -- checked and none found -- not a missing field.
            status1, body1 = await _upload(http, title=title_a, owner="alice", content=shared_bytes)
            assert status1 == 200
            assert body1.get("content_already_present") == []

            # State 2: the SAME bytes under a different title and owner. This is a
            # legitimate second registration and must still succeed (a separate
            # document), but it must now carry the other copy so the success is
            # not silent about the register already holding this source.
            status2, body2 = await _upload(http, title=title_b, owner="bob", content=shared_bytes)
            assert status2 == 200
            assert body2["document_id"] != body1["document_id"]
            announced = body2.get("content_already_present") or []
            assert announced, "second upload of known bytes must announce the existing copy"
            assert any(
                entry["document_id"] == body1["document_id"] and entry["title"] == title_a
                for entry in announced
            )

            # State 3: identical bytes for the SAME document -- unchanged 409.
            status3, _ = await _upload(http, title=title_a, owner="alice", content=shared_bytes)
            assert status3 == 409

            # State 4: genuinely new bytes -- empty announcement again, proving the
            # empty list means "checked, nothing found", not "never populated".
            status4, body4 = await _upload(http, title=title_c, owner="carol", content=other_bytes)
            assert status4 == 200
            assert body4.get("content_already_present") == []

        await engine.dispose()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
