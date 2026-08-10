import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_runs_and_llm_calls_tables_exist(db_session: AsyncSession):
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result}
    assert "runs" in tables
    assert "llm_calls" in tables
