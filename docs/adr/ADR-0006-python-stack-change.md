# ADR-0006: Backend and worker implemented in Python (FastAPI + Microsoft Agent Framework Python SDK) instead of .NET

## Status
Accepted — supersedes an earlier .NET scaffold produced before this decision.

## Context
The source specification (Section 10.2/10.3) *suggests* ASP.NET Core and a .NET MAF
Durable Extension worker. During implementation, the user explicitly requested
re-evaluating the stack: preference for Python and Node.js, with explicit permission
to redo prior work.

Microsoft Agent Framework ships an official Python SDK (in addition to .NET), so
choosing Python does not violate Section 2's requirement to use Microsoft Agent
Framework for workflow orchestration, nor Section 10.4's requirement to use Azure
OpenAI as the only runtime generative endpoint (the Azure OpenAI Python SDK is
first-class and officially supported).

## Decision
Backend and worker are implemented in Python:
- **API**: FastAPI (async), Pydantic v2 for request/response and canonical schema
  models, SQLAlchemy 2.0 async ORM with the `asyncpg` driver against PostgreSQL.
- **Worker**: Python process, reserved for Microsoft Agent Framework Python SDK
  workflow hosting (Section 11). Not implemented yet in this phase (ADR-0004).
- **Migrations**: Alembic (Python-native, SQLAlchemy-integrated).
- **Frontend**: Vite + React + TypeScript, Node.js tooling (unchanged choice from
  the specification's own recommendation in Section 10.1).
- **Database**: PostgreSQL 16, Docker Compose, host port 5433 (ADR-0001 still
  applies; only the ORM/driver is SQLAlchemy/asyncpg rather than EF Core/Npgsql).

Module boundaries mirror the originally planned .NET boundaries, now as Python
packages under `src/policy_platform/`:
- `domain` — SQLAlchemy ORM entities, no framework/AI deps.
- `contracts` — canonical policy schema (Pydantic), condition AST.
- `evaluator` — deterministic evaluator, pure Python, zero I/O deps.
- `infrastructure` — SQLAlchemy engine/session/repositories.
- `api` — FastAPI application and routers.
- `worker` — reserved MAF workflow host (placeholder).

## Rationale
- Matches the user's explicit stack preference.
- Python has first-class SDKs for both Microsoft Agent Framework and Azure OpenAI,
  so no architectural capability from the specification is lost.
- FastAPI + Pydantic gives strict, versioned structured-output schema validation
  (Section 12.1) with minimal ceremony.
- SQLAlchemy's async engine works cleanly with `asyncpg` against PostgreSQL locally,
  and the dialect can be swapped for cloud deployment without touching the domain
  model (ADR-0001).

## Consequences
- **Positive:** aligns with team skill preference; equally capable of satisfying
  every non-negotiable rule in Section 5, since those are language-agnostic
  architectural constraints, not .NET idioms.
- **Negative:** an initial .NET scaffold (project files, no business logic) was
  discarded; no data or running system depended on it, so the cost is limited to
  redone scaffolding effort.
- **Migration impact:** none outstanding.
