import time

from pydantic import BaseModel

from src.llm.protocol import LLMResult


class MockLLM:
    model_name = "mock-llm"

    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult:
        start = time.perf_counter()
        text = f"[mock response to: {prompt[:50]}]"
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResult(
            text=text,
            model=self.model_name,
            prompt_version=prompt_version,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=latency_ms,
            cost_usd=0.0,
        )

    async def structured(
        self, prompt: str, *, prompt_version: str, schema: type[BaseModel]
    ) -> BaseModel:
        return schema()
