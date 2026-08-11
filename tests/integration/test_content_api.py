import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.content.models import ContentArtifact
from src.content.schemas import GeneratedClaim, GeneratedContent
from src.db.models import LLMCall, Run
from src.db.session import get_session
from src.llm.mock import MockLLM


@pytest_asyncio.fixture
async def content_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    original_llm = app.state.llm_client
    app.state.llm_client = MockLLM()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.state.llm_client = original_llm
        app.dependency_overrides.pop(get_session, None)


async def create_grounded_topic(client: AsyncClient, suffix: str) -> tuple[str, str]:
    profile = await client.put(
        "/api/profile",
        json={"display_name": f"Content Builder {suffix}", "headline": "Evidence-first writer"},
    )
    assert profile.status_code == 200, profile.text

    document = await client.post(
        "/api/research/documents",
        json={
            "url": f"https://content.example/{suffix}",
            "title": "Grounded content systems",
            "content": (
                "A staged content system stores source evidence and checks every factual claim "
                "before it creates a platform-specific draft for human approval."
            ),
            "credibility": "0.900",
        },
    )
    assert document.status_code == 201, document.text
    document_id = document.json()["document"]["id"]
    topic = await client.post(
        "/api/research/topics",
        json={
            "title": "Why content pipelines need visible evidence",
            "summary": "A practical case for inspectable content generation.",
            "document_ids": [document_id],
            "scores": {
                "freshness": "0.800",
                "relevance": "0.900",
                "novelty": "0.700",
                "momentum": "0.600",
                "credibility": "0.900",
                "authority_fit": "0.850",
                "insight_potential": "0.900",
                "platform_fit": {"linkedin": "0.900", "x": "0.800"},
            },
        },
    )
    assert topic.status_code == 201, topic.text
    topic_id = topic.json()["id"]
    evidence = await client.put(
        f"/api/research/topics/{topic_id}/evidence",
        json={
            "thesis": "Visible evidence makes generated content safer to review.",
            "claims": [
                {
                    "statement": "A staged system checks claims before platform adaptation.",
                    "confidence": "0.950",
                    "verification_status": "supported",
                    "sources": [
                        {
                            "document_id": document_id,
                            "excerpt": (
                                "checks every factual claim before it creates a "
                                "platform-specific draft"
                            ),
                            "supports": True,
                        }
                    ],
                }
            ],
        },
    )
    assert evidence.status_code == 200, evidence.text
    return topic_id, evidence.json()["claims"][0]["id"]


@pytest.mark.asyncio
async def test_content_workflow_persists_stages_usage_and_approval(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    topic_id, claim_id = await create_grounded_topic(content_client, uuid.uuid4().hex)
    created = await content_client.post(
        "/api/content/workflows",
        json={
            "topic_id": topic_id,
            "angle_type": "framework",
            "platforms": ["linkedin", "x"],
        },
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]

    generated = await content_client.post(f"/api/content/workflows/{workflow_id}/run")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["status"] == "ready_for_approval"
    assert body["current_stage"] == "approval"
    assert {item["platform"] for item in body["approvals"]} == {"linkedin", "x"}
    assert all(item["decision"] == "pending" for item in body["approvals"])
    latest_stages = {artifact["stage"] for artifact in body["artifacts"]}
    assert latest_stages == {
        "angle",
        "outline",
        "draft",
        "voice_transform",
        "fact_check",
        "quality_evaluation",
        "rewrite",
        "linkedin_adaptation",
        "x_adaptation",
    }
    fact_check = next(item for item in body["artifacts"] if item["stage"] == "fact_check")
    assert fact_check["structured_data"]["passed"] is True
    quality = next(item for item in body["artifacts"] if item["stage"] == "quality_evaluation")
    assert set(quality["structured_data"]["deterministic_subscores"]) == {
        "specificity",
        "lexical_diversity",
        "sentence_rhythm",
        "formatting_restraint",
        "cliche_avoidance",
    }

    generation_run_id = uuid.UUID(generated.headers["X-Run-Id"])
    assert await db_session.get(Run, generation_run_id) is not None
    call_count = await db_session.scalar(
        select(func.count()).select_from(LLMCall).where(LLMCall.run_id == generation_run_id)
    )
    assert call_count == 8
    prompt_versions = set(
        await db_session.scalars(
            select(LLMCall.prompt_version).where(LLMCall.run_id == generation_run_id)
        )
    )
    assert "content-linkedin-adaptation/v1" in prompt_versions
    assert "content-x-adaptation/v1" in prompt_versions

    manual = await content_client.put(
        f"/api/content/workflows/{workflow_id}/artifacts/linkedin_adaptation",
        json={
            "content": "A human-edited LinkedIn draft grounded in the stored claim.",
            "claims": [{"statement": "A staged system checks claims.", "claim_id": claim_id}],
            "note": "Tightened the opening.",
        },
    )
    assert manual.status_code == 200, manual.text
    manual_artifacts = [
        item for item in manual.json()["artifacts"] if item["stage"] == "linkedin_adaptation"
    ]
    assert [item["revision"] for item in manual_artifacts] == [1, 2]
    assert manual_artifacts[-1]["source"] == "manual"

    linkedin = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "reason": "Reviewed."},
    )
    assert linkedin.status_code == 200, linkedin.text
    assert linkedin.json()["status"] == "ready_for_approval"
    x_approval = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "x", "decision": "approved"},
    )
    assert x_approval.status_code == 200, x_approval.text
    assert x_approval.json()["status"] == "approved"

    unsafe_manual = await content_client.put(
        f"/api/content/workflows/{workflow_id}/artifacts/linkedin_adaptation",
        json={
            "content": "An edit with an evidence reference from outside this workflow.",
            "claims": [
                {
                    "statement": "This statement is not grounded here.",
                    "claim_id": str(uuid.uuid4()),
                }
            ],
        },
    )
    assert unsafe_manual.status_code == 200, unsafe_manual.text
    assert unsafe_manual.json()["status"] == "fact_check_failed"
    blocked_approval = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved"},
    )
    assert blocked_approval.status_code == 409

    stored_revisions = await db_session.scalar(
        select(func.count())
        .select_from(ContentArtifact)
        .where(
            ContentArtifact.workflow_id == uuid.UUID(workflow_id),
            ContentArtifact.stage == "linkedin_adaptation",
        )
    )
    assert stored_revisions == 3


@pytest.mark.asyncio
async def test_foreign_claim_reference_stops_before_adaptation(
    content_client: AsyncClient,
) -> None:
    topic_id, _claim_id = await create_grounded_topic(content_client, uuid.uuid4().hex)
    foreign_claim_id = uuid.uuid4()
    app.state.llm_client = MockLLM(
        structured_response=GeneratedContent(
            content="A model draft with a claim from outside this evidence pack.",
            claims=[
                GeneratedClaim(
                    statement="This claim is not part of the workflow evidence.",
                    claim_id=foreign_claim_id,
                )
            ],
        )
    )
    created = await content_client.post(
        "/api/content/workflows",
        json={"topic_id": topic_id, "platforms": ["linkedin"]},
    )
    workflow_id = created.json()["id"]

    generated = await content_client.post(f"/api/content/workflows/{workflow_id}/run")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["status"] == "fact_check_failed"
    assert body["approvals"] == []
    assert "linkedin_adaptation" not in {item["stage"] for item in body["artifacts"]}
    fact_check = next(item for item in body["artifacts"] if item["stage"] == "fact_check")
    assert fact_check["structured_data"]["passed"] is False
    assert fact_check["structured_data"]["findings"][0]["status"] == "foreign"
