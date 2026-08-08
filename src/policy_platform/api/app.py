"""FastAPI application factory (Section 20 API requirements — local subset)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Enterprise Policy Formalization and Deterministic Policy Platform",
        description=(
            "Local build. Implements Phase 1 (foundation) and Phase 5 (deterministic "
            "evaluation) of the specification. See docs/known-limitations.md for what "
            "is intentionally deferred (MAF workflows, Azure OpenAI/Search, governance UI)."
        ),
        version="0.1.0",
    )

    # CORS: allow the configured web dev server port plus Vite's common
    # fallback ports (Vite auto-increments if its preferred port is taken,
    # which happened locally since 5173 was already in use).
    web_ports = {settings.web_dev_server_port, 5173, 5174, 5175}
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
