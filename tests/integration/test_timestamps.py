import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Run


@pytest.mark.asyncio
async def test_created_at_is_timezone_aware(db_session: AsyncSession):
    """Timestamps must be timezone-aware.

    This project ingests job posting dates from sources in many timezones and
    schedules content by local time, so naive timestamps are a silent-bug
    hazard. Every table added in later milestones should follow this pattern.
    """
    run = Run()
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)

    assert run.created_at.tzinfo is not None
    assert run.created_at.utcoffset() is not None
