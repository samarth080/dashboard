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


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
        await session.rollback()
    # asyncpg binds each connection to the event loop that opened it, but
    # pytest-asyncio gives every test its own loop while `engine` is a
    # module-level singleton. Without disposing, the next test checks out a
    # connection owned by a dead loop and asyncpg raises "got Future attached
    # to a different loop". See test_db_event_loop_isolation.py.
    await engine.dispose()
