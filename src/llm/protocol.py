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


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult: ...

    async def structured(
        self, prompt: str, *, prompt_version: str, schema: type[BaseModel]
    ) -> BaseModel: ...
