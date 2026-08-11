import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.base import Base
from src.db.session import get_engine


@pytest.mark.asyncio
async def test_runs_and_llm_calls_tables_exist(db_session: AsyncSession):
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result}
    assert "runs" in tables
    assert "llm_calls" in tables


@pytest.mark.asyncio
async def test_migrations_match_models():
    """Fails when a model changes without a corresponding migration.

    A bare table-existence check would pass against wrong columns, wrong
    types, or missing constraints. This instead diffs the live schema
    produced by running the migrations against what the ORM models declare,
    which is the failure mode every later milestone's hand-written migration
    is at risk of.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync_conn: compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)
        )
    assert diff == [], f"models and migrations have drifted: {diff}"
