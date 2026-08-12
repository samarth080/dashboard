from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.db.session import get_session


@pytest_asyncio.fixture
async def memory_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_create_and_list_manual_posts(memory_client: AsyncClient) -> None:
    created = await memory_client.post(
        "/api/memory/posts",
        json={
            "platform": "linkedin",
            "content": "Shipping beats polishing, most of the time.",
            "external_url": "https://example.com/posts/1",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["origin"] == "manual"
    assert body["status"] == "published_externally"
    assert body["embedding_model"] == "mock-embed-v1"

    listed = await memory_client.get("/api/memory/posts")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())


@pytest.mark.asyncio
async def test_manual_post_can_be_updated_and_deleted(memory_client: AsyncClient) -> None:
    created = await memory_client.post(
        "/api/memory/posts", json={"platform": "x", "content": "A short note."}
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]

    updated = await memory_client.patch(
        f"/api/memory/posts/{post_id}", json={"external_url": "https://example.com/x/1"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["external_url"] == "https://example.com/x/1"

    deleted = await memory_client.delete(f"/api/memory/posts/{post_id}")
    assert deleted.status_code == 204

    missing = await memory_client.get(f"/api/memory/posts/{post_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_empty_update_is_rejected(memory_client: AsyncClient) -> None:
    created = await memory_client.post(
        "/api/memory/posts", json={"platform": "x", "content": "Another note."}
    )
    assert created.status_code == 201, created.text
    response = await memory_client.patch(f"/api/memory/posts/{created.json()['id']}", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_metric_snapshots_are_append_only(memory_client: AsyncClient) -> None:
    created = await memory_client.post(
        "/api/memory/posts",
        json={
            "platform": "linkedin",
            "content": "Measured over time.",
            "posted_at": "2026-08-01T00:00:00Z",
        },
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    for _ in range(3):
        captured = await memory_client.post(f"/api/memory/posts/{post_id}/metrics")
        assert captured.status_code == 201, captured.text
        assert captured.json()["is_mock"] is True

    snapshots = await memory_client.get(f"/api/memory/posts/{post_id}/metrics")
    assert snapshots.status_code == 200
    assert len(snapshots.json()) == 3


@pytest.mark.asyncio
async def test_metrics_for_a_missing_post_return_404(memory_client: AsyncClient) -> None:
    response = await memory_client.post(
        "/api/memory/posts/00000000-0000-0000-0000-000000000000/metrics"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_preview_reports_a_verdict(memory_client: AsyncClient) -> None:
    text = "Evidence packs make a draft auditable rather than merely fluent."
    created = await memory_client.post(
        "/api/memory/posts", json={"platform": "linkedin", "content": text}
    )
    assert created.status_code == 201, created.text
    preview = await memory_client.post(
        "/api/memory/duplicate-check", json={"platform": "linkedin", "content": text}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["verdict"] == "block"
    assert body["config_version"] == "v1"
    assert body["neighbours"]


@pytest.mark.asyncio
async def test_duplicate_configs_can_be_listed_and_created(memory_client: AsyncClient) -> None:
    listed = await memory_client.get("/api/memory/duplicate-configs")
    assert listed.status_code == 200
    assert any(item["version"] == "v1" for item in listed.json())

    created = await memory_client.post(
        "/api/memory/duplicate-configs",
        json={
            "version": "strict-v1",
            "warn_threshold": "0.500",
            "block_threshold": "0.700",
            "active": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["active"] is True


@pytest.mark.asyncio
async def test_duplicate_config_version_conflict_returns_409(memory_client: AsyncClient) -> None:
    response = await memory_client.post(
        "/api/memory/duplicate-configs",
        json={"version": "v1", "warn_threshold": "0.500", "block_threshold": "0.700"},
    )
    assert response.status_code == 409
