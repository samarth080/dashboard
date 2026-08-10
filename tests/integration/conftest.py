import subprocess

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
        await session.rollback()
