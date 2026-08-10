import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Run
from src.llm.logging import log_llm_call
from src.llm.mock import MockLLM


@pytest.mark.asyncio
async def test_mock_llm_call_is_logged(db_session: AsyncSession):
    run = Run()
    db_session.add(run)
    await db_session.flush()

    llm = MockLLM()
    result = await llm.generate("hello world", prompt_version="v1")
    call = await log_llm_call(db_session, run, result)

    assert call.id is not None
    assert call.run_id == run.id
    assert call.model == "mock-llm"
    assert call.cost_usd == 0.0
