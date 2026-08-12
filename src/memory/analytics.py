"""Contract for post performance providers, plus a deterministic mock.

M4 stores performance data; it does not interpret it. Ranking, recommendation,
and any learning from engagement belong to M9.
"""

import hashlib
import math
import uuid
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class PostMetrics(BaseModel):
    """One performance sample.

    A real provider that does not report a metric must leave it None. A zero
    standing in for "unknown" would silently corrupt later analysis.
    """

    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    clicks: int | None = None
    follows: int | None = None


class AnalyticsProvider(Protocol):
    """Contract every analytics provider must satisfy.

    Implementations never persist; the caller writes the snapshot. Real
    platform providers stay behind the M7 capability gate.
    """

    @property
    def name(self) -> str: ...

    @property
    def is_mock(self) -> bool: ...

    async def fetch(
        self,
        *,
        post_id: uuid.UUID,
        platform: str,
        posted_at: datetime | None,
        now: datetime,
    ) -> PostMetrics: ...


class MockAnalyticsProvider:
    """Deterministic, credential-free `AnalyticsProvider`.

    Derives a plausible growth curve from the post id and its age, so repeated
    calls for the same post and age return identical numbers. These figures are
    invented. They exist so the schema and UI can be exercised, and every
    snapshot they produce is tagged `is_mock`.
    """

    name = "mock"
    is_mock = True

    async def fetch(
        self,
        *,
        post_id: uuid.UUID,
        platform: str,
        posted_at: datetime | None,
        now: datetime,
    ) -> PostMetrics:
        seed = int.from_bytes(hashlib.sha256(post_id.bytes).digest()[:8], "big")
        age_days = 0.0 if posted_at is None else max(0.0, (now - posted_at).total_seconds() / 86400)
        # Reach saturates rather than growing without bound.
        base = 200 + seed % 800
        impressions = int(base * math.log1p(age_days) + base / 4)
        engagement_rate = 0.02 + (seed % 30) / 1000
        engaged = int(impressions * engagement_rate)
        reactions = int(engaged * 0.7)
        comments = int(engaged * 0.2)
        reposts = engaged - reactions - comments
        return PostMetrics(
            impressions=impressions,
            reactions=reactions,
            comments=comments,
            reposts=reposts,
            clicks=int(impressions * 0.01),
            follows=int(engaged * 0.05),
        )
