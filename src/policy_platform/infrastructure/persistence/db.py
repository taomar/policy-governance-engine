"""Async SQLAlchemy engine/session management (Section 23).

This module is the single place the runtime creates database connections.
Repositories and API routers depend on `get_session` (a FastAPI dependency)
rather than constructing their own engine/session.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from policy_platform.infrastructure.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped async session."""

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session
