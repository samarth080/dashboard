from decimal import Decimal

import pytest
from pydantic import BaseModel

from src.llm.mock import MockLLM


class DummySchema(BaseModel):
    name: str = "default"


@pytest.mark.asyncio
async def test_generate_returns_llm_result():
    llm = MockLLM()
    result = await llm.generate("hello", prompt_version="v1")
    assert result.model == "mock-llm"
    assert result.prompt_version == "v1"
    assert result.cost_usd == Decimal("0")
    assert result.text.startswith("[mock response")
    assert result.input_tokens == 1
    assert result.output_tokens > 0


@pytest.mark.asyncio
async def test_structured_returns_schema_instance():
    llm = MockLLM()
    result = await llm.structured("hello", prompt_version="v1", schema=DummySchema)
    assert isinstance(result, DummySchema)
    assert result.name == "default"
