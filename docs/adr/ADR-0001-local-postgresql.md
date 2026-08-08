# ADR-0001: Use PostgreSQL for local development instead of Azure SQL

## Status
Accepted (local development only)

## Context
The target production architecture (Section 10.7) specifies Azure SQL Database as
the authoritative relational system of record. The user explicitly requested a
locally runnable environment using PostgreSQL, on a non-default port, to avoid local
Azure SQL/SQL Server tooling dependencies. A separate, unrelated PostgreSQL
container already runs on the developer machine on the default port 5432, which
independently confirms the need for a non-default port.

## Decision
Use PostgreSQL 16 via Docker Compose (`infra/local/docker-compose.yml`) for all local
development and testing. Map the container to host port **5433**.

SQLAlchemy 2.0 (async) is used with the `asyncpg` driver for the application runtime,
and `psycopg` (sync) for Alembic migrations. Entity models avoid PostgreSQL-only
constructs where a portable equivalent exists, and any PostgreSQL-specific feature
(e.g. `JSONB`) is isolated behind repository methods.

## Rationale
- Keeps local onboarding to `docker compose up` with no cloud dependency.
- Non-default port avoids conflicts with developer machines that already run
  PostgreSQL for other projects (confirmed necessary in this environment).
- SQLAlchemy's dialect system means swapping to Azure SQL or Azure Database for
  PostgreSQL for cloud deployment is a connection-string/dialect change, not a
  domain-model rewrite, provided the domain model avoids provider-specific constructs.

## Consequences
- **Positive:** zero-cost local setup; consistent behavior across developer machines.
- **Negative:** the local provider may not be the eventual production provider
  (Azure SQL vs. Azure Database for PostgreSQL is an open cloud-deployment decision,
  to be revisited in a future ADR when the Azure deployment phase begins).
- **Migration impact:** cloud deployment will require either an Azure SQL dialect
  swap (pyodbc/aioodbc) or pointing the existing PostgreSQL dialect at Azure Database
  for PostgreSQL; both are viable and deferred.
