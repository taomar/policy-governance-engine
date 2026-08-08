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
    notes,
    policy_attestations,
    policy_exceptions,
    policy_sets,
    policy_tests,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)


async def _reconcile_interrupted_runs() -> None:
    """Close out extraction runs that died with a previous process.

    An extraction is an in-process background task with in-process progress
    state. If the API stops mid-run — a crash, a restart to pick up new code —
    the task is gone but its `extraction_runs` row is still marked `running`,
    and the UI faithfully reports a run that will never finish. Worse, it is
    still holding a partial set of committed rules that must not be mistaken for
    a completed extraction.

    Nothing can resume such a run, so the honest thing at startup is to mark it
    failed. Rules it already committed are left in place: they are real drafts a
    reviewer may still want, and deleting them would discard work the user paid
    for. Baseline selection ignores non-completed runs, so a partial run cannot
    become the reference for a future delta.
    """

    from policy_platform.domain.models import ExtractionRun
    from policy_platform.infrastructure.db import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(
                update(ExtractionRun)
                .where(ExtractionRun.status.in_(("running", "pending")))
                .values(
                    status="failed",
                    error_message=(
                        "Interrupted — the API process stopped while this run was in "
                        "progress. Rules committed before the interruption were kept."
                    ),
                )
            )
            await session.commit()
            if result.rowcount:
                logger.warning("Marked %s interrupted extraction run(s) as failed", result.rowcount)
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
        title="Enterprise Policy Formalization and Deterministic Policy Platform",
        description=(
            "Local build. Implements Phase 1 (foundation) and Phase 5 (deterministic "
            "evaluation) of the specification. See docs/known-limitations.md for what "
            "is intentionally deferred (MAF workflows, Azure OpenAI/Search, governance UI)."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: allow the configured web dev server port plus Vite's common
    # fallback ports (Vite auto-increments if its preferred port is taken,
    # which happened locally since 5173 was already in use). A wider range
    # is allowed here since multiple concurrent local sessions may each grab
    # a different port in this range.
    web_ports = {settings.web_dev_server_port, *range(5173, 5180)}
    allowed_origins = [f"http://localhost:{p}" for p in web_ports] + [
        f"http://127.0.0.1:{p}" for p in web_ports
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
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

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
