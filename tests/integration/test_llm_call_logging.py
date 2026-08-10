from decimal import Decimal

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
    assert call.cost_usd == Decimal("0")


@pytest.mark.asyncio
async def test_cost_usd_is_decimal_and_supports_decimal_arithmetic(db_session: AsyncSession):
    """Regression guard for cost_usd being mistyped as float.

    cost_usd is money, backed by a Postgres NUMERIC column, and must behave
    as Decimal end-to-end. Decimal and float cannot be added together
    (`Decimal + float` raises TypeError), so if cost_usd were ever float —
    on LLMResult, or on the row read back from the database — the first bit
    of real accounting arithmetic downstream would crash.
    """
    run = Run()
    db_session.add(run)
    await db_session.flush()

    llm = MockLLM()
    result = await llm.generate("hello world", prompt_version="v1")
    assert isinstance(result.cost_usd, Decimal)

    call = await log_llm_call(db_session, run, result)
    assert isinstance(call.cost_usd, Decimal)

    # Arithmetic with another Decimal must not raise.
    total = call.cost_usd + Decimal("1.500000")
    assert total == Decimal("1.500000")
