"""Contract shared by every LLM provider implementation (mock or real).

`LLMClient` is the seam real providers (OpenAI, Anthropic, ...) are plugged
in behind in later milestones. Anything written against `LLMClient` — agents,
tasks, tests — must keep working unmodified when a mock is swapped for a real
provider, so the contract is deliberately narrow: two methods, both returning
usage metadata, neither touching persistence.
"""

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: Decimal


class StructuredResult[T: BaseModel](BaseModel):
    """Parsed structured output plus the usage metadata needed to cost-log it.

    `structured()` spends tokens exactly like `generate()` does, but a bare
    parsed object has nowhere to carry token counts, latency, or cost.
    Bundling them here lets `log_llm_call` (src/llm/persistence.py) accept
    one result shape for both call kinds instead of forking its logic.
    """

    parsed: T
    usage: LLMResult


class LLMClient(Protocol):
    """Contract every LLM provider implementation must satisfy.

    Responsibilities of an implementation:
    - Return accurate usage metadata (tokens, latency, cost) on every call,
      for both `generate` and `structured` — cost tracking depends on this
      being complete, not just present on the "easy" path.
    - Raise on failure (rate limits, malformed provider responses, schema
      validation failures for `structured`) rather than returning a
      placeholder result; callers are expected to handle exceptions, not
      sniff sentinel values.
    - Never persist anything. Implementations only talk to the provider and
      return a result; the caller owns persistence via
      `src.llm.persistence.log_llm_call`. This keeps providers swappable and
      testable without a database.
    """

    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult: ...

    async def structured[T: BaseModel](
        self, prompt: str, *, prompt_version: str, schema: type[T]
    ) -> StructuredResult[T]: ...
