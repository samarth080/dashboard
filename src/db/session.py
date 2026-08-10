from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.settings import get_settings


def to_sync_url(url: str) -> str:
    """Convert an asyncpg SQLAlchemy URL to its psycopg2 (sync) equivalent.

    Used by Alembic, which drives migrations synchronously and cannot use
    the asyncpg driver directly.
    """
    return make_url(url).set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the process-wide async engine on first use.

    Building it lazily keeps importing this module side-effect free, lets tests
    retarget the database via cache_clear(), and means a forked worker builds
    its own pool rather than inheriting the parent's sockets.
    """
    return create_async_engine(get_settings().database_url, echo=False)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
