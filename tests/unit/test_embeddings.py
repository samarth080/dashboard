import math
from decimal import Decimal

import pytest

from src.llm.embeddings import MockEmbedder
from src.memory.similarity import cosine_similarity


@pytest.mark.asyncio
async def test_embed_returns_one_vector_per_text():
    result = await MockEmbedder().embed(["first text", "second text"])
    assert len(result.vectors) == 2
    assert all(len(vector) == MockEmbedder.dimensions for vector in result.vectors)


@pytest.mark.asyncio
async def test_vectors_are_l2_normalized():
    result = await MockEmbedder().embed(["normalization matters here"])
    norm = math.sqrt(sum(value * value for value in result.vectors[0]))
    assert norm == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embedding_is_deterministic():
    first = await MockEmbedder().embed(["exactly the same input"])
    second = await MockEmbedder().embed(["exactly the same input"])
    assert first.vectors == second.vectors


@pytest.mark.asyncio
async def test_shared_vocabulary_scores_higher_than_unrelated_text():
    result = await MockEmbedder().embed(
        [
            "evidence grounded content pipelines",
            "evidence grounded content workflows",
            "sourdough bread starter hydration",
        ]
    )
    related = cosine_similarity(result.vectors[0], result.vectors[1])
    unrelated = cosine_similarity(result.vectors[0], result.vectors[2])
    assert related > unrelated


@pytest.mark.asyncio
async def test_empty_text_produces_a_zero_vector():
    result = await MockEmbedder().embed([""])
    assert set(result.vectors[0]) == {0.0}


@pytest.mark.asyncio
async def test_usage_metadata_is_cost_loggable():
    result = await MockEmbedder().embed(["four small tokens here"])
    assert result.usage.model == "mock-embed-v1"
    assert result.usage.prompt_version == "embedding/mock-embed-v1"
    assert result.usage.input_tokens == 4
    assert result.usage.output_tokens == 0
    assert result.usage.cost_usd == Decimal("0")
