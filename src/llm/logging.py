from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LLMCall, Run
from src.llm.protocol import LLMResult, StructuredResult


async def log_llm_call(
    session: AsyncSession, run: Run, result: LLMResult | StructuredResult
) -> LLMCall:
    usage = result.usage if isinstance(result, StructuredResult) else result
    call = LLMCall(
        run_id=run.id,
        model=usage.model,
        prompt_version=usage.prompt_version,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        latency_ms=usage.latency_ms,
        cost_usd=usage.cost_usd,
    )
    session.add(call)
    await session.flush()
    await session.refresh(call)
    return call
