from decimal import Decimal

import pytest
from pydantic import BaseModel

from src.llm.mock import MockLLM
from src.llm.protocol import StructuredResult


class DummySchema(BaseModel):
    name: str = "default"


class NestedSchema(BaseModel):
    label: str


class RequiredFieldsSchema(BaseModel):
    """A schema shaped like a realistic structured-output target: required
    scalar fields plus a nested model with its own required field. No
    field here has a default, so `schema()` alone raises ValidationError —
    this is exactly the shape that broke the old MockLLM.structured().
    """

    name: str
    count: int
    active: bool
    tags: list[str]
    metadata: dict[str, str]
    nested: NestedSchema


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
    assert isinstance(result, StructuredResult)
    assert isinstance(result.parsed, DummySchema)
    assert result.parsed.name == "default"
    # usage metadata must be present so the call can be cost-logged
    assert result.usage.model == "mock-llm"
    assert result.usage.prompt_version == "v1"
    assert result.usage.cost_usd == Decimal("0")


@pytest.mark.asyncio
async def test_structured_handles_schema_with_required_fields():
    """FIX 1 regression test: MockLLM must not crash on realistic schemas."""
    llm = MockLLM()
    result = await llm.structured("hello", prompt_version="v1", schema=RequiredFieldsSchema)
    parsed = result.parsed
    assert isinstance(parsed, RequiredFieldsSchema)
    assert isinstance(parsed.name, str)
    assert isinstance(parsed.count, int)
    assert isinstance(parsed.active, bool)
    assert parsed.tags == []
    assert parsed.metadata == {}
    assert isinstance(parsed.nested, NestedSchema)
    assert isinstance(parsed.nested.label, str)


@pytest.mark.asyncio
async def test_structured_response_can_be_injected():
    """A mock you cannot tell what to return is not useful for testing."""
    canned = RequiredFieldsSchema(
        name="alice",
        count=3,
        active=True,
        tags=["a", "b"],
        metadata={"k": "v"},
        nested=NestedSchema(label="pinned"),
    )
    llm = MockLLM(structured_response=canned)
    result = await llm.structured("hello", prompt_version="v1", schema=RequiredFieldsSchema)
    assert result.parsed is canned


@pytest.mark.asyncio
async def test_latency_ms_is_injectable():
    """FIX 9: latency_ms should be controllable rather than always 0."""
    llm = MockLLM(latency_ms=42)
    generate_result = await llm.generate("hello", prompt_version="v1")
    assert generate_result.latency_ms == 42

    structured_result = await llm.structured("hello", prompt_version="v1", schema=DummySchema)
    assert structured_result.usage.latency_ms == 42


@pytest.mark.asyncio
async def test_latency_ms_defaults_to_zero():
    llm = MockLLM()
    result = await llm.generate("hello", prompt_version="v1")
    assert result.latency_ms == 0


async def test_structured_return_type_is_concrete_for_pyright() -> None:
    """FIX 3 regression guard.

    If `structured()` ever erases the schema type back to bare `BaseModel`,
    this line fails pyright (assigning `BaseModel` to a `DummySchema`
    -typed variable is a type error) even though it would still pass at
    runtime under pytest.
    """
    llm = MockLLM()
    result = await llm.structured("hello", prompt_version="v1", schema=DummySchema)
    typed_parsed: DummySchema = result.parsed
    assert typed_parsed.name == "default"
