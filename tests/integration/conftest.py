import subprocess
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory, engine


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    yield


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine() -> AsyncIterator[None]:
    """Drop pooled database connections after every test.

    asyncpg binds each connection to the event loop that opened it, but
    pytest-asyncio gives every test its own loop while ``engine`` is a
    module-level singleton. A connection left in the pool by one test and
    checked out by the next raises "got Future attached to a different loop"
    — and it surfaces in the *next* test, not the one at fault.

    This is autouse so it covers every route to the database, including tests
    that go through the app's own ``get_session`` dependency rather than the
    ``db_session`` fixture. See test_db_event_loop_isolation.py.
    """
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
        await session.rollback()
