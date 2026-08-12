import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.memory.analytics import MockAnalyticsProvider


@pytest.mark.asyncio
async def test_metrics_are_deterministic_for_the_same_post_and_age():
    post_id = uuid.uuid4()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    now = datetime(2026, 8, 6, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    first = await provider.fetch(post_id=post_id, platform="linkedin", posted_at=posted_at, now=now)
    second = await provider.fetch(
        post_id=post_id, platform="linkedin", posted_at=posted_at, now=now
    )
    assert first == second


@pytest.mark.asyncio
async def test_different_posts_get_different_metrics():
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    now = datetime(2026, 8, 6, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    first = await provider.fetch(
        post_id=uuid.uuid4(), platform="linkedin", posted_at=posted_at, now=now
    )
    second = await provider.fetch(
        post_id=uuid.uuid4(), platform="linkedin", posted_at=posted_at, now=now
    )
    assert first.impressions != second.impressions


@pytest.mark.asyncio
async def test_impressions_grow_with_age():
    post_id = uuid.uuid4()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    young = await provider.fetch(
        post_id=post_id, platform="x", posted_at=posted_at, now=posted_at + timedelta(days=1)
    )
    old = await provider.fetch(
        post_id=post_id, platform="x", posted_at=posted_at, now=posted_at + timedelta(days=30)
    )
    # The mock always reports impressions; assert that before comparing so
    # this stays type-safe under pyright.
    assert young.impressions is not None
    assert old.impressions is not None
    assert old.impressions > young.impressions


@pytest.mark.asyncio
async def test_engagement_never_exceeds_impressions():
    provider = MockAnalyticsProvider()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    for _ in range(25):
        metrics = await provider.fetch(
            post_id=uuid.uuid4(),
            platform="linkedin",
            posted_at=posted_at,
            now=posted_at + timedelta(days=7),
        )
        # The mock always reports every metric; assert that before arithmetic
        # so this stays type-safe under pyright.
        assert metrics.impressions is not None
        assert metrics.reactions is not None
        assert metrics.comments is not None
        assert metrics.reposts is not None
        assert metrics.clicks is not None
        engagement = metrics.reactions + metrics.comments + metrics.reposts
        assert engagement <= metrics.impressions
        assert metrics.clicks <= metrics.impressions


@pytest.mark.asyncio
async def test_a_post_with_no_posted_at_is_treated_as_brand_new():
    provider = MockAnalyticsProvider()
    metrics = await provider.fetch(
        post_id=uuid.uuid4(),
        platform="x",
        posted_at=None,
        now=datetime(2026, 8, 6, tzinfo=UTC),
    )
    assert metrics.impressions is not None
    assert metrics.impressions >= 0
