"""Persists LLM call usage metadata to the `llm_calls` table."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LLMCall, Run
from src.llm.embeddings import EmbeddingResult
from src.llm.protocol import LLMResult, StructuredResult


async def log_llm_call(
    session: AsyncSession, run: Run, result: LLMResult | StructuredResult | EmbeddingResult
) -> LLMCall:
    """Record one LLM call's usage metadata against `run`.

    Accepts either a `generate()` result (LLMResult) or a `structured()`
    result (StructuredResult, whose `.usage` carries the same metadata) so
    both call kinds are logged through one path — structured calls spend
    tokens too and must be cost-tracked identically.

    Embedding calls (EmbeddingResult) log through the same path so embedding
    spend is tracked in one place rather than a parallel table.

    Flushes to obtain the primary key (`id` and the server-generated
    `created_at` are populated by the flush; no `refresh()` is needed to see
    them). Does not commit — the caller owns the transaction and is
    responsible for committing it.
    """
    usage = result.usage if isinstance(result, StructuredResult | EmbeddingResult) else result
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
    return call
