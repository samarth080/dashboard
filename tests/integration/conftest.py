import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from src.core.settings import get_settings
from src.db.session import get_engine, get_sessionmaker, to_sync_url

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def use_test_database() -> Iterator[None]:
    """Retarget the database layer at TEST_DATABASE_URL before anything touches it.

    Without this, tests write through whatever DATABASE_URL resolves to — the
    developer's own .env by default, which is the dev database. Refuse to run
    at all if the two URLs match, rather than silently running destructive
    tests against dev data.
    """
    settings = get_settings()
    if settings.test_database_url == settings.database_url:
        pytest.exit(
            "TEST_DATABASE_URL must differ from DATABASE_URL; "
            "refusing to run tests against the dev database."
        )
    os.environ["DATABASE_URL"] = settings.test_database_url
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(use_test_database: None) -> Iterator[None]:
    """Run Alembic in-process against the test database.

    Depends explicitly on ``use_test_database`` (rather than relying on
    fixture declaration order) so migrations always land on the test
    database even if this file is reordered. Runs in-process with absolute
    paths so it works regardless of the cwd pytest was invoked from, and
    avoids a second `uv run` subprocess spin-up.
    """
    settings = get_settings()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", to_sync_url(settings.database_url))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine() -> AsyncIterator[None]:
    """Drop pooled database connections after every test.

    asyncpg binds each connection to the event loop that opened it, but
    pytest-asyncio gives every test its own loop while the engine returned by
    ``get_engine()`` is a process-wide singleton. A connection left in the
    pool by one test and checked out by the next raises "got Future attached
    to a different loop" — and it surfaces in the *next* test, not the one at
    fault.

    This is autouse so it covers every route to the database, including tests
    that go through the app's own ``get_session`` dependency rather than the
    ``db_session`` fixture. See test_db_event_loop_isolation.py.
    """
    yield
    await get_engine().dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to an outer transaction that is always rolled back.

    ``session.rollback()`` alone is not enough: ``AsyncSession.__aexit__``
    already does that, and it only undoes an *uncommitted* transaction. If a
    test itself calls ``session.commit()``, that commit lands for real and
    leaks into every later test (see test_db_isolation.py). Binding the
    session to a connection-level transaction means an in-test commit only
    releases a savepoint (``join_transaction_mode="create_savepoint"``); the
    outer transaction is rolled back unconditionally on teardown, so nothing
    a test does can persist.
    """
    engine = get_engine()
    conn = await engine.connect()
    trans = await conn.begin()
    session = async_sessionmaker(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
