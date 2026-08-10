from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LLMCall, Run
from src.llm.protocol import LLMResult


async def log_llm_call(session: AsyncSession, run: Run, result: LLMResult) -> LLMCall:
    call = LLMCall(
        run_id=run.id,
        model=result.model,
        prompt_version=result.prompt_version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
    )
    session.add(call)
    await session.flush()
    await session.refresh(call)
    return call
