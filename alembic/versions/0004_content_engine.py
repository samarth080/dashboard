"""Add persisted M3 content workflows, artifacts, grounding, and approvals.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "content_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topic_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("angle_type", sa.String(length=32), nullable=False),
        sa.Column("requested_platforms", sa.JSON(), nullable=False),
        sa.Column("current_stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "latest_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "angle_type IN ('technical', 'product', 'business', 'career', "
            "'contrarian', 'tutorial', 'breakdown', 'prediction', 'case_study', "
            "'comparison', 'framework')",
            name="ck_content_workflows_angle_type",
        ),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'fact_check_failed', "
            "'ready_for_approval', 'approved', 'rejected')",
            name="ck_content_workflows_status",
        ),
    )
    op.create_index("ix_content_workflows_topic_id", "content_workflows", ["topic_id"])
    op.create_index(
        "ix_content_workflows_evidence_pack_id", "content_workflows", ["evidence_pack_id"]
    )
    op.create_index("ix_content_workflows_status", "content_workflows", ["status"])
    op.create_index("ix_content_workflows_latest_run_id", "content_workflows", ["latest_run_id"])

    op.create_table(
        "content_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=120)),
        sa.Column("model", sa.String(length=160)),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "workflow_id", "stage", "revision", name="uq_content_artifacts_stage_revision"
        ),
        sa.CheckConstraint(
            "stage IN ('angle', 'outline', 'draft', 'voice_transform', "
            "'fact_check', 'quality_evaluation', 'rewrite', "
            "'linkedin_adaptation', 'x_adaptation')",
            name="ck_content_artifacts_stage",
        ),
        sa.CheckConstraint(
            "source IN ('model', 'deterministic_fallback', 'deterministic', 'manual')",
            name="ck_content_artifacts_source",
        ),
        sa.CheckConstraint("revision > 0", name="ck_content_artifacts_revision"),
    )
    op.create_index("ix_content_artifacts_workflow_id", "content_artifacts", ["workflow_id"])
    op.create_index("ix_content_artifacts_stage", "content_artifacts", ["stage"])
    op.create_index("ix_content_artifacts_run_id", "content_artifacts", ["run_id"])

    op.create_table(
        "content_claim_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_artifacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claimed_claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "resolved_claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="SET NULL"),
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "ix_content_claim_references_artifact_id",
        "content_claim_references",
        ["artifact_id"],
    )
    op.create_index(
        "ix_content_claim_references_resolved_claim_id",
        "content_claim_references",
        ["resolved_claim_id"],
    )

    op.create_table(
        "content_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("required_level", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=160)),
        sa.Column("reason", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "decision_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.UniqueConstraint("workflow_id", "platform", name="uq_content_approvals_platform"),
        sa.CheckConstraint("platform IN ('linkedin', 'x')", name="ck_content_approvals_platform"),
        sa.CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected')",
            name="ck_content_approvals_decision",
        ),
        sa.CheckConstraint(
            "required_level BETWEEN 1 AND 3", name="ck_content_approvals_required_level"
        ),
    )
    op.create_index("ix_content_approvals_workflow_id", "content_approvals", ["workflow_id"])
    op.create_index(
        "ix_content_approvals_decision_run_id", "content_approvals", ["decision_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_content_approvals_decision_run_id", table_name="content_approvals")
    op.drop_index("ix_content_approvals_workflow_id", table_name="content_approvals")
    op.drop_table("content_approvals")
    op.drop_index(
        "ix_content_claim_references_resolved_claim_id",
        table_name="content_claim_references",
    )
    op.drop_index("ix_content_claim_references_artifact_id", table_name="content_claim_references")
    op.drop_table("content_claim_references")
    op.drop_index("ix_content_artifacts_run_id", table_name="content_artifacts")
    op.drop_index("ix_content_artifacts_stage", table_name="content_artifacts")
    op.drop_index("ix_content_artifacts_workflow_id", table_name="content_artifacts")
    op.drop_table("content_artifacts")
    op.drop_index("ix_content_workflows_latest_run_id", table_name="content_workflows")
    op.drop_index("ix_content_workflows_status", table_name="content_workflows")
    op.drop_index("ix_content_workflows_evidence_pack_id", table_name="content_workflows")
    op.drop_index("ix_content_workflows_topic_id", table_name="content_workflows")
    op.drop_table("content_workflows")
