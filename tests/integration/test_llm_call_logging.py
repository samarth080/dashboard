from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Run
from src.llm.embeddings import MockEmbedder
from src.llm.mock import MockLLM
from src.llm.persistence import log_llm_call


class _StructuredSchema(BaseModel):
    """Realistic-shaped schema: a required field, no default."""

    verdict: str


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


@pytest.mark.asyncio
async def test_structured_llm_call_is_logged(db_session: AsyncSession):
    """FIX 2 regression test: structured() calls must be cost-loggable too.

    Before this fix, log_llm_call only accepted a bare LLMResult, and
    structured() returned a bare BaseModel with no usage metadata at all —
    there was no way to log a structured call. Structured output is where
    most agentic token spend happens, so this closes a real hole in the
    llm_calls table.
    """
    run = Run()
    db_session.add(run)
    await db_session.flush()

    llm = MockLLM()
    result = await llm.structured("classify this", prompt_version="v1", schema=_StructuredSchema)
    call = await log_llm_call(db_session, run, result)

    assert call.id is not None
    assert call.run_id == run.id
    assert call.model == "mock-llm"
    assert call.prompt_version == "v1"
    assert isinstance(call.cost_usd, Decimal)


@pytest.mark.asyncio
async def test_embedding_call_is_logged(db_session: AsyncSession):
    """M4 regression test: embed() calls must be cost-loggable too.

    Before this fix, log_llm_call only accepted LLMResult and
    StructuredResult — EmbeddingResult had no equivalent coverage, so nothing
    proved an embedding call actually produces a valid llm_calls row.
    Embedding calls spend tokens exactly like generation calls and must be
    cost-tracked identically, including that output_tokens is always 0 and
    cost_usd survives the round trip through the NUMERIC column as Decimal.
    """
    run = Run()
    db_session.add(run)
    await db_session.flush()

    embedder = MockEmbedder()
    result = await embedder.embed(["four small tokens here"])
    call = await log_llm_call(db_session, run, result)

    assert call.id is not None
    assert call.run_id == run.id
    assert call.model == "mock-embed-v1"
    assert call.prompt_version == "embedding/mock-embed-v1"
    assert call.output_tokens == 0
    assert isinstance(call.cost_usd, Decimal)
    assert call.cost_usd == Decimal("0")
