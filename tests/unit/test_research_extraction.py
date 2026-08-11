import uuid
from decimal import Decimal

import pytest

from src.brain.models import Interest
from src.llm.mock import MockLLM
from src.research.extraction import TopicExtractor
from src.research.models import RawDocument
from src.research.schemas import (
    PlatformFit,
    TopicExtractionOutput,
    TopicScores,
    TopicSuggestion,
)


@pytest.mark.asyncio
async def test_topic_extractor_is_versioned_and_preserves_document_ids() -> None:
    document_id = uuid.UUID("00000000-0000-0000-0000-000000000301")
    document = RawDocument(
        id=document_id,
        url="https://example.com/research",
        canonical_url="https://example.com/research",
        title="Evidence-first systems",
        content="Evidence-first systems retain source excerpts for every supported claim.",
        content_hash="a" * 64,
        credibility=Decimal("0.800"),
    )
    interest = Interest(
        name="Research systems",
        normalized_name="research systems",
        weight=Decimal("0.900"),
        enabled=True,
    )
    output = TopicExtractionOutput(
        topics=[
            TopicSuggestion(
                cluster_key="evidence-provenance",
                title="Why evidence provenance matters",
                summary="An inspectable research workflow.",
                document_ids=[document_id],
                scores=TopicScores(
                    freshness=Decimal("0.7"),
                    relevance=Decimal("0.9"),
                    novelty=Decimal("0.8"),
                    momentum=Decimal("0.6"),
                    credibility=Decimal("0.8"),
                    authority_fit=Decimal("0.9"),
                    insight_potential=Decimal("0.8"),
                    platform_fit=PlatformFit(linkedin=Decimal("0.9"), x=Decimal("0.7")),
                ),
            )
        ]
    )
    result = await TopicExtractor(MockLLM(structured_response=output)).extract(
        [document], [interest]
    )
    assert result.parsed is output
    assert result.parsed.topics[0].document_ids == [document_id]
    assert result.usage.prompt_version == "research-topic-extraction/v1"
    assert result.usage.input_tokens > 0


@pytest.mark.asyncio
async def test_topic_extractor_requires_documents() -> None:
    with pytest.raises(ValueError, match="at least one"):
        await TopicExtractor(MockLLM()).extract([], [])
