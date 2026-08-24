"""Async SQLAlchemy engine / session factory + LangGraph checkpointer setup.

PostgreSQL from day one (impl §5.5). Engines are cached per URL; storage
functions accept an optional ``database_url`` so tests can target a separate
database while production defaults to ``settings.database_url``.
"""

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class Base(DeclarativeBase):
    pass


_engines: dict[str, AsyncEngine] = {}


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Return (and cache) an async engine for the given URL."""
    url = database_url or settings.database_url
    if url not in _engines:
        _engines[url] = create_async_engine(url)
    return _engines[url]


def session_factory(database_url: str | None = None) -> async_sessionmaker:
    """Return an async sessionmaker bound to the (cached) engine."""
    return async_sessionmaker(get_engine(database_url), expire_on_commit=False)


async def init_db(database_url: str | None = None) -> None:
    """Create course-store tables (idempotent). Models are imported so metadata
    is populated before create_all."""
    from app.storage import course_store  # noqa: F401  (registers CourseRecord)

    async with get_engine(database_url).begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def psycopg_url(database_url: str) -> str:
    """langgraph-checkpoint-postgres uses psycopg; accept an asyncpg URL."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def make_checkpointer(database_url: str | None = None) -> "AsyncPostgresSaver":
    """LangGraph PostgresSaver for session checkpoints (impl §7.3).

    Returns the async-context-manager instance from ``from_conn_string`` —
    callers must use it as ``async with make_checkpointer(url) as saver:``.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver.from_conn_string(psycopg_url(database_url or settings.database_url))
