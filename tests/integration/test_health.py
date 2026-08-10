import pytest
from httpx import ASGITransport, AsyncClient

from services.api.main import app


@pytest.mark.asyncio
async def test_health_returns_ok_with_run_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "run_id" in body and body["run_id"]
    assert "X-Run-Id" in response.headers
