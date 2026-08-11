"""personal brain profile, interests, settings, memory, and voice

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_key", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("headline", sa.String(length=240)),
        sa.Column("bio", sa.Text()),
        sa.Column("location", sa.String(length=160)),
        *_timestamps(),
        sa.UniqueConstraint("profile_key"),
    )

    op.create_table(
        "career_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_title", sa.String(length=160)),
        sa.Column("current_company", sa.String(length=160)),
        sa.Column("years_experience", sa.Numeric(4, 1)),
        sa.Column("target_roles", sa.JSON(), nullable=False),
        sa.Column("target_industries", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("profile_id"),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("daily_llm_budget_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("public_action_approval_level", sa.Integer(), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "public_action_approval_level BETWEEN 1 AND 3",
            name="ck_user_settings_approval_level",
        ),
        sa.CheckConstraint("daily_llm_budget_usd >= 0", name="ck_user_settings_daily_budget"),
        sa.UniqueConstraint("profile_id"),
    )

    op.create_table(
        "interests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interests.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("weight", sa.Numeric(4, 3), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_interests_weight"),
        sa.UniqueConstraint("profile_id", "normalized_name", name="uq_interests_profile_name"),
    )
    op.create_index("ix_interests_parent_id", "interests", ["parent_id"])
    op.create_index("ix_interests_profile_id", "interests", ["profile_id"])

    op.create_table(
        "writing_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(length=80), nullable=False),
        sa.Column("consent_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_writing_samples_profile_id", "writing_samples", ["profile_id"])

    op.create_table(
        "voice_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tone_descriptors", sa.JSON(), nullable=False),
        sa.Column("sentence_patterns", sa.JSON(), nullable=False),
        sa.Column("vocabulary_preferences", sa.JSON(), nullable=False),
        sa.Column("avoid_phrases", sa.JSON(), nullable=False),
        sa.Column("formatting_preferences", sa.JSON(), nullable=False),
        sa.Column("signature_traits", sa.JSON(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("analysis_prompt_version", sa.String(length=80), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_voice_profiles_confidence"
        ),
        sa.UniqueConstraint("profile_id"),
    )

    op.create_table(
        "memory_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "domain IN ('personal', 'voice', 'content', 'research', 'relationship', "
            "'career', 'performance')",
            name="ck_memory_records_domain",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memory_records_confidence"
        ),
        sa.UniqueConstraint("profile_id", "domain", "key", name="uq_memory_profile_domain_key"),
    )
    op.create_index("ix_memory_records_profile_id", "memory_records", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_records_profile_id", table_name="memory_records")
    op.drop_table("memory_records")
    op.drop_table("voice_profiles")
    op.drop_index("ix_writing_samples_profile_id", table_name="writing_samples")
    op.drop_table("writing_samples")
    op.drop_index("ix_interests_profile_id", table_name="interests")
    op.drop_index("ix_interests_parent_id", table_name="interests")
    op.drop_table("interests")
    op.drop_table("user_settings")
    op.drop_table("career_profiles")
    op.drop_table("user_profiles")
