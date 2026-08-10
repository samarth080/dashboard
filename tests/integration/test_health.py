import pytest
from httpx import ASGITransport, AsyncClient

from services.api.main import app
from src.db.session import engine


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
    # This test hits the real database through the app's own get_session
    # dependency rather than the db_session fixture, so it must dispose the
    # engine itself. Without this, the connection asyncpg opened for this
    # test's event loop stays in the pool; pytest-asyncio gives the next test
    # a new loop, and checking out that stale connection raises
    # "got Future attached to a different loop" (see
    # test_db_event_loop_isolation.py and the db_session fixture).
    await engine.dispose()
