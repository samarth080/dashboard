import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.brain.schemas import VoiceAnalysis
from src.db.models import LLMCall, Run
from src.db.session import get_session
from src.llm.mock import MockLLM


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
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


async def create_profile(client: AsyncClient) -> None:
    response = await client.put(
        "/api/profile",
        json={
            "display_name": "Sam",
            "headline": "Builder",
            "bio": "I build useful systems.",
            "location": "India",
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_profile_career_and_settings_flow(api_client: AsyncClient) -> None:
    missing = await api_client.get("/api/profile")
    assert missing.status_code == 404

    await create_profile(api_client)
    profile = await api_client.get("/api/profile")
    assert profile.json()["display_name"] == "Sam"

    career = await api_client.put(
        "/api/profile/career",
        json={
            "current_title": "Engineer",
            "years_experience": "5.5",
            "target_roles": ["Founder", "Product Engineer"],
            "skills": ["Python", "Product"],
        },
    )
    assert career.status_code == 200, career.text
    assert career.json()["target_roles"] == ["Founder", "Product Engineer"]

    settings = await api_client.put(
        "/api/settings",
        json={
            "timezone": "Asia/Kolkata",
            "locale": "en-IN",
            "daily_llm_budget_usd": "7.50",
            "public_action_approval_level": 1,
            "memory_enabled": True,
        },
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["timezone"] == "Asia/Kolkata"
    assert settings.json()["daily_llm_budget_usd"] == "7.50"


@pytest.mark.asyncio
async def test_interest_hierarchy_rejects_duplicates_and_cycles(api_client: AsyncClient) -> None:
    await create_profile(api_client)
    root = await api_client.post("/api/interests", json={"name": "Technology", "weight": "0.900"})
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]

    child = await api_client.post(
        "/api/interests",
        json={"name": "AI Agents", "weight": "0.800", "parent_id": root_id},
    )
    assert child.status_code == 201, child.text

    duplicate = await api_client.post(
        "/api/interests", json={"name": "technology", "weight": "0.500"}
    )
    assert duplicate.status_code == 409

    cycle = await api_client.patch(
        f"/api/interests/{root_id}", json={"parent_id": child.json()["id"]}
    )
    assert cycle.status_code == 422
    assert "cycle" in cycle.json()["detail"]


@pytest.mark.asyncio
async def test_voice_analysis_is_confirmed_versioned_and_cost_logged(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_profile(api_client)
    rejected = await api_client.post(
        "/api/voice/samples",
        json={
            "content": (
                "This sample is long enough but was not affirmatively confirmed by its owner."
            ),
            "confirmed_user_provided": False,
        },
    )
    assert rejected.status_code == 422

    sample = await api_client.post(
        "/api/voice/samples",
        json={
            "title": "Product note",
            "content": (
                "Start with the user problem. Explain the trade-off plainly, then show one "
                "specific example so the recommendation is easy to evaluate and apply."
            ),
            "confirmed_user_provided": True,
        },
    )
    assert sample.status_code == 201, sample.text

    app.state.llm_client = MockLLM(
        structured_response=VoiceAnalysis(
            summary="Clear, practical explanations grounded in examples.",
            tone_descriptors=["direct", "helpful"],
            sentence_patterns=["imperative opening"],
            vocabulary_preferences=["plain language"],
            avoid_phrases=["revolutionary"],
            formatting_preferences=["short paragraphs"],
            signature_traits=["explicit trade-offs"],
            confidence=0.85,
        )
    )
    response = await api_client.post("/api/voice/analyze")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sample_count"] == 1
    assert body["analysis_prompt_version"] == "voice-analysis/v1"
    assert body["tone_descriptors"] == ["direct", "helpful"]

    run_id = uuid.UUID(response.headers["X-Run-Id"])
    assert await db_session.get(Run, run_id) is not None
    llm_call = await db_session.scalar(select(LLMCall).where(LLMCall.run_id == run_id))
    assert llm_call is not None
    assert llm_call.prompt_version == "voice-analysis/v1"

    budget = await api_client.put(
        "/api/settings",
        json={
            "timezone": "UTC",
            "locale": "en",
            "daily_llm_budget_usd": "0",
            "public_action_approval_level": 1,
            "memory_enabled": True,
        },
    )
    assert budget.status_code == 200
    blocked = await api_client.post("/api/voice/analyze")
    assert blocked.status_code == 422
    assert "budget" in blocked.json()["detail"]
