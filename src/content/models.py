"""ORM models for persisted content stages, grounding, and approval."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models import utcnow

CONTENT_STAGES = (
    "angle",
    "outline",
    "draft",
    "voice_transform",
    "fact_check",
    "quality_evaluation",
    "rewrite",
    "linkedin_adaptation",
    "x_adaptation",
)
WORKFLOW_STATUSES = (
    "created",
    "running",
    "fact_check_failed",
    "ready_for_approval",
    "approved",
    "rejected",
)


class ContentTimestampMixin:
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


class ContentWorkflow(ContentTimestampMixin, Base):
    __tablename__ = "content_workflows"
    __table_args__ = (
        CheckConstraint(
            "angle_type IN ('technical', 'product', 'business', 'career', "
            "'contrarian', 'tutorial', 'breakdown', 'prediction', 'case_study', "
            "'comparison', 'framework')",
            name="ck_content_workflows_angle_type",
        ),
        CheckConstraint(
            "status IN ('created', 'running', 'fact_check_failed', "
            "'ready_for_approval', 'approved', 'rejected')",
            name="ck_content_workflows_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topic_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    angle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_platforms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    current_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created", index=True)
    latest_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )

    artifacts: Mapped[list[ContentArtifact]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="ContentArtifact.created_at, ContentArtifact.revision",
    )
    approvals: Mapped[list[ContentApproval]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="ContentApproval.platform",
    )


class ContentArtifact(ContentTimestampMixin, Base):
    __tablename__ = "content_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "stage", "revision", name="uq_content_artifacts_stage_revision"
        ),
        CheckConstraint(
            "stage IN ('angle', 'outline', 'draft', 'voice_transform', "
            "'fact_check', 'quality_evaluation', 'rewrite', "
            "'linkedin_adaptation', 'x_adaptation')",
            name="ck_content_artifacts_stage",
        ),
        CheckConstraint(
            "source IN ('model', 'deterministic_fallback', 'deterministic', 'manual')",
            name="ck_content_artifacts_source",
        ),
        CheckConstraint("revision > 0", name="ck_content_artifacts_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(160))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )

    workflow: Mapped[ContentWorkflow] = relationship(back_populates="artifacts")
    claim_references: Mapped[list[ContentClaimReference]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class ContentClaimReference(ContentTimestampMixin, Base):
    __tablename__ = "content_claim_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claimed_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resolved_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)

    artifact: Mapped[ContentArtifact] = relationship(back_populates="claim_references")


class ContentApproval(ContentTimestampMixin, Base):
    __tablename__ = "content_approvals"
    __table_args__ = (
        UniqueConstraint("workflow_id", "platform", name="uq_content_approvals_platform"),
        CheckConstraint("platform IN ('linkedin', 'x')", name="ck_content_approvals_platform"),
        CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected')",
            name="ck_content_approvals_decision",
        ),
        CheckConstraint(
            "required_level BETWEEN 1 AND 3", name="ck_content_approvals_required_level"
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
    decision: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actor: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )

    workflow: Mapped[ContentWorkflow] = relationship(back_populates="approvals")
