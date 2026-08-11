import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.db.models import LLMCall, Run
from src.db.session import get_session
from src.llm.mock import MockLLM
from src.research.models import RawDocument
from src.research.schemas import (
    PlatformFit,
    TopicExtractionOutput,
    TopicScores,
    TopicSuggestion,
)


@pytest_asyncio.fixture
async def research_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    original_llm = app.state.llm_client
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.state.llm_client = original_llm
        app.dependency_overrides.pop(get_session, None)


async def ingest_document(
    client: AsyncClient,
    *,
    url: str,
    title: str,
    content: str,
    embedding: list[float] | None = None,
) -> dict:
    payload: dict[str, object] = {
        "url": url,
        "title": title,
        "content": content,
        "credibility": "0.800",
    }
    if embedding is not None:
        payload["embedding"] = embedding
        payload["embedding_model"] = "test-embedding-v1"
    response = await client.post("/api/research/documents", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_source_and_document_deduplication_flow(research_client: AsyncClient) -> None:
    source = await research_client.post(
        "/api/research/sources",
        json={
            "key": "example-feed",
            "name": "Example feed",
            "url": "https://EXAMPLE.com:443/feed?utm_source=test",
            "default_credibility": "0.750",
        },
    )
    assert source.status_code == 201, source.text
    assert source.json()["url"] == "https://example.com/feed"

    original_content = (
        "Bounded research workflows retain source provenance, normalize every public document, "
        "and preserve explicit evidence before any content generation stage begins. The design "
        "makes each claim inspectable and keeps ranking weights outside application code."
    )
    original = await ingest_document(
        research_client,
        url="https://example.com/posts/research?utm_campaign=launch&a=1",
        title="Bounded research workflows",
        content=original_content,
    )
    assert original["outcome"] == "created"
    document_id = original["document"]["id"]
    assert original["document"]["canonical_url"] == "https://example.com/posts/research?a=1"

    canonical_duplicate = await ingest_document(
        research_client,
        url="https://EXAMPLE.com:443/posts/research?a=1#details",
        title="Same URL",
        content="Different content that should not replace the canonical document.",
    )
    assert canonical_duplicate["outcome"] == "canonical_duplicate"
    assert canonical_duplicate["document"]["id"] == document_id

    content_duplicate = await ingest_document(
        research_client,
        url="https://example.com/mirrors/research",
        title="Mirrored copy",
        content=original_content,
    )
    assert content_duplicate["outcome"] == "content_duplicate"
    assert content_duplicate["document"]["id"] == document_id

    near_duplicate = await ingest_document(
        research_client,
        url="https://example.com/posts/research-update",
        title="Bounded research workflows update",
        content=f"{original_content} One detail was added.",
    )
    assert near_duplicate["outcome"] == "near_duplicate"
    assert near_duplicate["document"]["duplicate_of_id"] == document_id

    canonical_list = await research_client.get("/api/research/documents")
    all_documents = await research_client.get(
        "/api/research/documents", params={"include_duplicates": "true"}
    )
    assert len(canonical_list.json()) == 1
    assert len(all_documents.json()) == 2


@pytest.mark.asyncio
async def test_ranked_topic_and_evidence_pack_flow(research_client: AsyncClient) -> None:
    first = await ingest_document(
        research_client,
        url="https://example.org/research/one",
        title="Evidence-first research",
        content=(
            "Evidence-first research stores the source excerpt beside every claim so reviewers "
            "can distinguish a supported conclusion from an unverified model suggestion."
        ),
    )
    second = await ingest_document(
        research_client,
        url="https://example.org/research/two",
        title="Configurable ranking",
        content=(
            "Configurable ranking makes freshness and relevance weights visible, versioned, "
            "and reproducible instead of burying product policy in application constants."
        ),
    )
    first_id = first["document"]["id"]
    second_id = second["document"]["id"]

    topic = await research_client.post(
        "/api/research/topics",
        json={
            "title": "Why research systems need evidence provenance",
            "summary": "A practical architecture for inspectable research workflows.",
            "document_ids": [first_id],
            "scores": {
                "freshness": "0.900",
                "relevance": "0.950",
                "novelty": "0.700",
                "momentum": "0.600",
                "credibility": "0.800",
                "authority_fit": "0.850",
                "insight_potential": "0.900",
                "platform_fit": {"linkedin": "0.900", "x": "0.700"},
            },
        },
    )
    assert topic.status_code == 201, topic.text
    topic_body = topic.json()
    assert topic_body["document_ids"] == [first_id]
    assert topic_body["total_score"] == "0.8250"

    pack = await research_client.put(
        f"/api/research/topics/{topic_body['id']}/evidence",
        json={
            "thesis": "Evidence provenance makes research outputs auditable.",
            "claims": [
                {
                    "statement": "Every supported claim retains a source excerpt.",
                    "confidence": "0.900",
                    "verification_status": "supported",
                    "sources": [
                        {
                            "document_id": first_id,
                            "excerpt": (
                                "Evidence-first research stores the source excerpt beside every "
                                "claim."
                            ),
                            "locator": "paragraph 1",
                            "supports": True,
                        }
                    ],
                }
            ],
        },
    )
    assert pack.status_code == 200, pack.text
    assert pack.json()["claims"][0]["verification_status"] == "supported"

    loaded = await research_client.get(f"/api/research/topics/{topic_body['id']}/evidence")
    assert loaded.status_code == 200
    assert loaded.json()["claims"][0]["sources"][0]["document_id"] == first_id

    unrelated = await research_client.put(
        f"/api/research/topics/{topic_body['id']}/evidence",
        json={
            "thesis": "Invalid cross-topic evidence.",
            "claims": [
                {
                    "statement": "This source is not linked to the topic.",
                    "confidence": "0.500",
                    "sources": [
                        {
                            "document_id": second_id,
                            "excerpt": "Configurable ranking makes weights visible and versioned.",
                        }
                    ],
                }
            ],
        },
    )
    assert unrelated.status_code == 422
    assert "linked to the topic" in unrelated.json()["detail"]


@pytest.mark.asyncio
async def test_pgvector_embedding_round_trip(
    research_client: AsyncClient, db_session: AsyncSession
) -> None:
    result = await ingest_document(
        research_client,
        url="https://example.net/vector",
        title="Vector-backed research",
        content="This sufficiently long document verifies the optional vector storage path.",
        embedding=[0.1, 0.2, 0.3],
    )
    document = await db_session.get(RawDocument, uuid.UUID(result["document"]["id"]))
    assert document is not None
    assert document.embedding is not None
    assert list(document.embedding) == pytest.approx([0.1, 0.2, 0.3])
    assert document.embedding_model == "test-embedding-v1"


@pytest.mark.asyncio
async def test_structured_extraction_clusters_topics_and_logs_usage(
    research_client: AsyncClient, db_session: AsyncSession
) -> None:
    profile = await research_client.put(
        "/api/profile",
        json={"display_name": "Researcher", "headline": "Evidence-first builder"},
    )
    assert profile.status_code == 200, profile.text

    first = await ingest_document(
        research_client,
        url="https://research.example/one",
        title="Evidence provenance",
        content=(
            "Evidence provenance keeps claims connected to exact source excerpts and makes every "
            "research conclusion inspectable by a human reviewer."
        ),
    )
    second = await ingest_document(
        research_client,
        url="https://research.example/two",
        title="Bounded research workflows",
        content=(
            "Bounded research workflows separate normalization, ranking, claims, and evidence so "
            "model output never silently becomes an attributed fact."
        ),
    )
    first_id = uuid.UUID(first["document"]["id"])
    second_id = uuid.UUID(second["document"]["id"])

    common_scores = TopicScores(
        freshness=Decimal("0.800"),
        relevance=Decimal("0.900"),
        novelty=Decimal("0.750"),
        momentum=Decimal("0.600"),
        credibility=Decimal("0.850"),
        authority_fit=Decimal("0.900"),
        insight_potential=Decimal("0.850"),
        platform_fit=PlatformFit(linkedin=Decimal("0.900"), x=Decimal("0.700")),
    )
    app.state.llm_client = MockLLM(
        structured_response=TopicExtractionOutput(
            topics=[
                TopicSuggestion(
                    cluster_key="Evidence Provenance",
                    title="Evidence provenance for AI research",
                    summary="Keep claims inspectable from source to output.",
                    document_ids=[first_id],
                    scores=common_scores,
                ),
                TopicSuggestion(
                    cluster_key="evidence-provenance",
                    title="Bounded evidence workflows",
                    summary="Separate model suggestions from supported facts.",
                    document_ids=[second_id],
                    scores=common_scores,
                ),
            ]
        )
    )
    response = await research_client.post(
        "/api/research/extract",
        json={"document_ids": [str(first_id), str(second_id)]},
    )
    assert response.status_code == 200, response.text
    topics = response.json()
    assert len(topics) == 1
    assert topics[0]["cluster_key"] == "evidence-provenance"
    assert set(topics[0]["document_ids"]) == {str(first_id), str(second_id)}
    assert topics[0]["extraction_prompt_version"] == "research-topic-extraction/v1"

    run_id = uuid.UUID(response.headers["X-Run-Id"])
    assert await db_session.get(Run, run_id) is not None
    llm_call = await db_session.scalar(select(LLMCall).where(LLMCall.run_id == run_id))
    assert llm_call is not None
    assert llm_call.prompt_version == "research-topic-extraction/v1"
