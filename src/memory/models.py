"""ORM models for post history, duplicate policy, and performance snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models import utcnow

POST_PLATFORMS = ("linkedin", "x")
POST_ORIGINS = ("workflow", "manual")
POST_STATUSES = ("approved_unpublished", "published_externally")
DUPLICATE_VERDICTS = ("clear", "warn", "block")


class MemoryTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        server_default=func.now(),
    )


class PostRecord(MemoryTimestampMixin, Base):
    """One post, per platform. Never implies anything was published by us."""

    __tablename__ = "post_records"
    __table_args__ = (
        # NULL workflow_id rows (manual backfill) are distinct in Postgres, so
        # this constrains workflow-origin rows only and makes re-approval
        # idempotent without touching manual history.
        UniqueConstraint("workflow_id", "platform", name="uq_post_records_workflow_platform"),
        CheckConstraint("platform IN ('linkedin', 'x')", name="ck_post_records_platform"),
        CheckConstraint("origin IN ('workflow', 'manual')", name="ck_post_records_origin"),
        CheckConstraint(
            "status IN ('approved_unpublished', 'published_externally')",
            name="ck_post_records_status",
        ),
        # A vector with no model string (or vice versa) is invisible to every
        # similarity query while appearing embedded — the worst failure mode
        # for a duplicate detector, so the pair is enforced structurally.
        CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name="ck_post_records_embedding_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    # No explicit index: uq_post_records_workflow_platform already creates a
    # btree led by workflow_id, which serves every lookup a plain index would.
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_workflows.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_url: Mapped[str | None] = mapped_column(String(2048))
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
    embedding_model: Mapped[str | None] = mapped_column(String(160), index=True)

    snapshots: Mapped[list[PostMetricSnapshot]] = relationship(
        back_populates="post_record",
        cascade="all, delete-orphan",
        order_by="PostMetricSnapshot.captured_at",
    )


class PostMetricSnapshot(Base):
    """Append-only performance sample. Never updated in place.

    Unreported metrics stay NULL rather than 0: a zero that means "unknown"
    would silently corrupt any later analysis. No `updated_at`: an
    auto-updating column would contradict "never updated in place" and make
    an accidental UPDATE look expected, mirroring the immutable `Run` table
    in `src/db/models.py`.
    """

    __tablename__ = "post_metric_snapshots"
    __table_args__ = (
        CheckConstraint("source IN ('mock', 'manual')", name="ck_post_metric_snapshots_source"),
        CheckConstraint("is_mock = (source = 'mock')", name="ck_post_metric_snapshots_is_mock"),
        CheckConstraint(
            "impressions >= 0 AND reactions >= 0 AND comments >= 0 AND "
            "reposts >= 0 AND clicks >= 0 AND follows >= 0",
            name="ck_post_metric_snapshots_nonnegative",
        ),
        Index(
            "ix_post_metric_snapshots_post_record_id_captured_at",
            "post_record_id",
            "captured_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    impressions: Mapped[int | None] = mapped_column(Integer)
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    reposts: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    follows: Mapped[int | None] = mapped_column(Integer)

    post_record: Mapped[PostRecord] = relationship(back_populates="snapshots")


class DuplicateConfig(MemoryTimestampMixin, Base):
    """Versioned duplicate policy. The engine holds no default thresholds."""

    __tablename__ = "duplicate_configs"
    __table_args__ = (
        UniqueConstraint("version", name="uq_duplicate_configs_version"),
        CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 1 AND "
            "block_threshold >= 0 AND block_threshold <= 1 AND "
            "warn_threshold <= block_threshold",
            name="ck_duplicate_configs_thresholds",
        ),
        CheckConstraint(
            "lookback_days IS NULL OR lookback_days > 0",
            name="ck_duplicate_configs_lookback",
        ),
        # M4 gates approval on "the" active config, so ambiguity here is
        # worse than in M2's scoring_configs. Partial unique index instead of
        # a plain one so any number of inactive rows can coexist.
        Index(
            "uq_duplicate_configs_single_active",
            "active",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    warn_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    block_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    cross_platform_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lookback_days: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class DuplicateCheck(MemoryTimestampMixin, Base):
    """Persisted, inspectable verdict for one workflow/platform check.

    Note the rounding seam: `top_similarity` is stored at 3 decimal places
    while the verdict is computed from the full-precision float, so a true
    0.6996 persists as 0.700 next to a `clear` verdict against a 0.700 warn
    threshold. That is expected, not a bug — the stored value is a display
    rounding of the number the verdict was actually computed from.
    """

    __tablename__ = "duplicate_checks"
    __table_args__ = (
        CheckConstraint("platform IN ('linkedin', 'x')", name="ck_duplicate_checks_platform"),
        CheckConstraint(
            "verdict IN ('clear', 'warn', 'block')", name="ck_duplicate_checks_verdict"
        ),
        CheckConstraint(
            "top_similarity >= 0 AND top_similarity <= 1",
            name="ck_duplicate_checks_top_similarity",
        ),
        # The milestone's central audit guarantee — a blocked draft may only
        # be approved with a written justification — made structural rather
        # than resting entirely on application code. btrim closes the
        # empty-string hole a bare NOT NULL would leave.
        CheckConstraint(
            "NOT overridden OR (override_reason IS NOT NULL AND btrim(override_reason) <> '')",
            name="ck_duplicate_checks_override_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    top_similarity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    nearest_post_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("post_records.id", ondelete="SET NULL"), index=True
    )
    components: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )
