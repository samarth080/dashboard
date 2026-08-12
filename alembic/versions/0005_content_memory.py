"""Add M4 post history, duplicate policy, and performance snapshots.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed identity so a later data migration can target this exact row; the
# same value in every environment rather than a fresh gen_random_uuid() each
# time the migration runs.
SEED_DUPLICATE_CONFIG_ID = "6c219730-503f-4868-9e81-7f1af797022a"


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
        "post_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="SET NULL"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("external_url", sa.String(length=2048)),
        sa.Column("embedding", VECTOR()),
        sa.Column("embedding_model", sa.String(length=160)),
        *_timestamps(),
        sa.UniqueConstraint("workflow_id", "platform", name="uq_post_records_workflow_platform"),
        sa.CheckConstraint("platform IN ('linkedin', 'x')", name="ck_post_records_platform"),
        sa.CheckConstraint("origin IN ('workflow', 'manual')", name="ck_post_records_origin"),
        sa.CheckConstraint(
            "status IN ('approved_unpublished', 'published_externally')",
            name="ck_post_records_status",
        ),
        sa.CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name="ck_post_records_embedding_pair",
        ),
    )
    op.create_index("ix_post_records_platform", "post_records", ["platform"])
    op.create_index("ix_post_records_origin", "post_records", ["origin"])
    op.create_index("ix_post_records_content_hash", "post_records", ["content_hash"])
    op.create_index("ix_post_records_embedding_model", "post_records", ["embedding_model"])

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "post_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("post_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("impressions", sa.Integer()),
        sa.Column("reactions", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("reposts", sa.Integer()),
        sa.Column("clicks", sa.Integer()),
        sa.Column("follows", sa.Integer()),
        sa.CheckConstraint("source IN ('mock', 'manual')", name="ck_post_metric_snapshots_source"),
        sa.CheckConstraint("is_mock = (source = 'mock')", name="ck_post_metric_snapshots_is_mock"),
        sa.CheckConstraint(
            "impressions >= 0 AND reactions >= 0 AND comments >= 0 AND "
            "reposts >= 0 AND clicks >= 0 AND follows >= 0",
            name="ck_post_metric_snapshots_nonnegative",
        ),
    )
    op.create_index(
        "ix_post_metric_snapshots_post_record_id_captured_at",
        "post_metric_snapshots",
        ["post_record_id", "captured_at"],
    )

    op.create_table(
        "duplicate_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("warn_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column("block_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column("cross_platform_check", sa.Boolean(), nullable=False),
        sa.Column("lookback_days", sa.Integer()),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("version", name="uq_duplicate_configs_version"),
        sa.CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 1 AND "
            "block_threshold >= 0 AND block_threshold <= 1 AND "
            "warn_threshold <= block_threshold",
            name="ck_duplicate_configs_thresholds",
        ),
        sa.CheckConstraint(
            "lookback_days IS NULL OR lookback_days > 0",
            name="ck_duplicate_configs_lookback",
        ),
    )
    op.create_index("ix_duplicate_configs_active", "duplicate_configs", ["active"])
    op.create_index(
        "uq_duplicate_configs_single_active",
        "duplicate_configs",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active"),
    )

    op.create_table(
        "duplicate_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("config_version", sa.String(length=80), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("top_similarity", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "nearest_post_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("post_records.id", ondelete="SET NULL"),
        ),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("overridden", sa.Boolean(), nullable=False),
        sa.Column("override_reason", sa.Text()),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
        ),
        *_timestamps(),
        sa.CheckConstraint("platform IN ('linkedin', 'x')", name="ck_duplicate_checks_platform"),
        sa.CheckConstraint(
            "verdict IN ('clear', 'warn', 'block')", name="ck_duplicate_checks_verdict"
        ),
        sa.CheckConstraint(
            "top_similarity >= 0 AND top_similarity <= 1",
            name="ck_duplicate_checks_top_similarity",
        ),
        sa.CheckConstraint(
            "NOT overridden OR (override_reason IS NOT NULL AND btrim(override_reason) <> '')",
            name="ck_duplicate_checks_override_reason",
        ),
    )
    op.create_index("ix_duplicate_checks_workflow_id", "duplicate_checks", ["workflow_id"])
    op.create_index(
        "ix_duplicate_checks_nearest_post_record_id",
        "duplicate_checks",
        ["nearest_post_record_id"],
    )
    op.create_index("ix_duplicate_checks_run_id", "duplicate_checks", ["run_id"])

    # Seed the starting policy as data the user can edit. This is not the same
    # as hard-coding thresholds in the scorer: the engine still reads whatever
    # row is active, and has no fallback of its own.
    op.execute(
        f"""
        INSERT INTO duplicate_configs (
            id, version, warn_threshold, block_threshold,
            cross_platform_check, lookback_days, active, created_at, updated_at
        ) VALUES (
            '{SEED_DUPLICATE_CONFIG_ID}', 'v1', 0.700, 0.850,
            false, NULL, true, now(), now()
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_duplicate_checks_run_id", table_name="duplicate_checks")
    op.drop_index("ix_duplicate_checks_nearest_post_record_id", table_name="duplicate_checks")
    op.drop_index("ix_duplicate_checks_workflow_id", table_name="duplicate_checks")
    op.drop_table("duplicate_checks")

    op.drop_index("uq_duplicate_configs_single_active", table_name="duplicate_configs")
    op.drop_index("ix_duplicate_configs_active", table_name="duplicate_configs")
    op.drop_table("duplicate_configs")

    op.drop_index(
        "ix_post_metric_snapshots_post_record_id_captured_at",
        table_name="post_metric_snapshots",
    )
    op.drop_table("post_metric_snapshots")

    op.drop_index("ix_post_records_embedding_model", table_name="post_records")
    op.drop_index("ix_post_records_content_hash", table_name="post_records")
    op.drop_index("ix_post_records_origin", table_name="post_records")
    op.drop_index("ix_post_records_platform", table_name="post_records")
    op.drop_table("post_records")
