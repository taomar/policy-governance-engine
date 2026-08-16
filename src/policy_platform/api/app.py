"""FastAPI application factory (Section 20 API requirements — local subset)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from policy_platform.api.routers import (
    ai,
    audit,
    candidate_rules,
    documents,
    evaluations,
    extraction,
    notes,
    policy_attestations,
    policy_exceptions,
    policy_payload,
    policy_sets,
    policy_tests,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)


_INTERRUPTED_MESSAGE = (
    "Interrupted — the API process stopped while this run was in "
    "progress. Rules committed before the interruption were kept."
)


async def _reconcile_interrupted_runs_for_session(session) -> int:
    """Fail this API process's own orphaned runs and report how many.

    Takes an open session so the ownership boundary can be tested directly,
    without standing up the global sessionmaker. Returns the number of rows
    marked failed.

    The predicate carries two clauses, and both are load-bearing:

    * ``status in (running, pending)`` — the run never reached a terminal state,
      so a previous incarnation of *this* process left it dangling.
    * ``owner_kind == OWNER_API`` — the run's liveness was bound to the API
      process. Without this clause the update is table-wide and reaches runs a
      *different* process (a headless or CLI extraction) is still working. Those
      runs are legitimately ``running``; stamping them ``failed`` misreports a
      live run as a dead one and, because ``failed`` is an unusable baseline
      status, silently removes a healthy run from baseline selection.
    """

    from policy_platform.domain.models import ExtractionRun
    from policy_platform.infrastructure.persistence.repositories.candidates import (
        OWNER_API,
    )

    result = await session.execute(
        update(ExtractionRun)
        .where(
            ExtractionRun.status.in_(("running", "pending")),
            ExtractionRun.owner_kind == OWNER_API,
        )
        .values(status="failed", error_message=_INTERRUPTED_MESSAGE)
    )
    await session.commit()
    return result.rowcount or 0


async def _reconcile_interrupted_runs() -> None:
    """Close out API-owned extraction runs that died with a previous process.

    An API extraction is an in-process background task with in-process progress
    state. If the API stops mid-run — a crash, a restart to pick up new code —
    the task is gone but its `extraction_runs` row is still marked `running`,
    and the UI faithfully reports a run that will never finish. Worse, it is
    still holding a partial set of committed rules that must not be mistaken for
    a completed extraction. Nothing can resume such a run, so the honest thing
    at startup is to mark it failed. Rules it already committed are left in
    place: they are real drafts a reviewer may still want, and deleting them
    would discard work the user paid for. Baseline selection ignores
    non-completed runs, so a partial run cannot become the reference for a
    future delta.

    That premise — "the task is gone" — holds only for runs *this* runtime
    started. A run some other process is driving is not gone when the API
    restarts; it is still working. So the sweep is scoped to `owner_kind ==
    OWNER_API` (see `_reconcile_interrupted_runs_for_session`): the API cleans
    up after itself and leaves foreign runs alone rather than declaring them
    dead on its own restart.
    """

    from policy_platform.infrastructure.persistence.db import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            count = await _reconcile_interrupted_runs_for_session(session)
            if count:
                logger.warning("Marked %s interrupted extraction run(s) as failed", count)
    except Exception:  # noqa: BLE001
        # Never block startup on housekeeping: a database that is not reachable
        # yet is the API's problem to report per-request, not a reason to refuse
        # to boot.
        logger.exception("Could not reconcile interrupted extraction runs")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await _reconcile_interrupted_runs()
        yield

    app = FastAPI(
        title="PolicyVerbAItim",
        description=(
            "AI to read. Evidence to prove. Determinism to decide. Source-traceable "
            "policy formalization with deterministic evaluation — no model in the "
            "decision path. Local build; see docs/known-limitations.md for what is "
            "intentionally deferred."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS origins come from configuration (see Settings.allowed_cors_origins).
    # They used to be a hardcoded port range here, which meant running the UI on
    # any other port required editing application code — and the symptom is a
    # silent browser-side block rather than anything visible in a server log.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(policy_sets.router)
    app.include_router(candidate_rules.router)
    app.include_router(evaluations.router)
    app.include_router(documents.router)
    app.include_router(ai.router)
    app.include_router(notes.router)
    app.include_router(policy_tests.router)
    app.include_router(audit.router)
    app.include_router(policy_exceptions.router)
    app.include_router(policy_attestations.router)
    app.include_router(policy_payload.router)
    app.include_router(extraction.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
