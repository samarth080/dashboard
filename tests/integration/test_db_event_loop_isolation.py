import asyncio

from sqlalchemy import text

from src.db.session import get_engine, get_sessionmaker


def test_engine_can_be_reused_across_event_loops():
    """Regression: asyncpg connections are bound to the event loop that opened them.

    pytest-asyncio gives every async test its own event loop, but the engine
    returned by ``get_engine()`` is an ``lru_cache``d singleton whose pool
    outlives any single loop. A connection left in the pool by one test and
    checked out by the next raises "got Future attached to a different loop".
    The ``db_session`` fixture prevents that by disposing the engine on
    teardown; this test locks in that discipline without depending on test
    ordering.
    """

    async def query_then_release() -> None:
        async with get_sessionmaker()() as session:
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
        await get_engine().dispose()

    asyncio.run(query_then_release())
    asyncio.run(query_then_release())
