"""research sources, documents, topics, evidence, and pgvector

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11

"""

import uuid

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "research_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_credibility", sa.Numeric(4, 3), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("last_retrieved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "default_credibility >= 0 AND default_credibility <= 1",
            name="ck_research_sources_credibility",
        ),
        sa.CheckConstraint("kind IN ('rss')", name="ck_research_sources_kind"),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "scoring_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("near_duplicate_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "near_duplicate_threshold >= 0 AND near_duplicate_threshold <= 1",
            name="ck_scoring_configs_duplicate_threshold",
        ),
        sa.UniqueConstraint("name", "version", name="uq_scoring_configs_name_version"),
    )
    op.create_index("ix_scoring_configs_active", "scoring_configs", ["active"])

    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_sources.id", ondelete="SET NULL"),
        ),
        sa.Column("external_id", sa.String(length=500)),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=240)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("credibility", sa.Numeric(4, 3), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "duplicate_of_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_documents.id", ondelete="SET NULL"),
        ),
        sa.Column("embedding", VECTOR()),
        sa.Column("embedding_model", sa.String(length=160)),
        *_timestamps(),
        sa.CheckConstraint(
            "credibility >= 0 AND credibility <= 1",
            name="ck_raw_documents_credibility",
        ),
        sa.UniqueConstraint("canonical_url"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_raw_documents_source_external"),
    )
    op.create_index("ix_raw_documents_source_id", "raw_documents", ["source_id"])
    op.create_index("ix_raw_documents_content_hash", "raw_documents", ["content_hash"])
    op.create_index("ix_raw_documents_duplicate_of_id", "raw_documents", ["duplicate_of_id"])

    op.create_table(
        "topic_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cluster_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("freshness", sa.Numeric(4, 3), nullable=False),
        sa.Column("relevance", sa.Numeric(4, 3), nullable=False),
        sa.Column("novelty", sa.Numeric(4, 3), nullable=False),
        sa.Column("momentum", sa.Numeric(4, 3), nullable=False),
        sa.Column("credibility", sa.Numeric(4, 3), nullable=False),
        sa.Column("authority_fit", sa.Numeric(4, 3), nullable=False),
        sa.Column("insight_potential", sa.Numeric(4, 3), nullable=False),
        sa.Column("platform_fit", sa.JSON(), nullable=False),
        sa.Column("total_score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "scoring_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scoring_configs.id"),
            nullable=False,
        ),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "extraction_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id"),
        ),
        sa.Column("extraction_prompt_version", sa.String(length=80)),
        sa.Column("embedding", VECTOR()),
        sa.Column("embedding_model", sa.String(length=160)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected')",
            name="ck_topic_candidates_status",
        ),
        sa.CheckConstraint(
            "freshness >= 0 AND freshness <= 1 AND "
            "relevance >= 0 AND relevance <= 1 AND "
            "novelty >= 0 AND novelty <= 1 AND "
            "momentum >= 0 AND momentum <= 1 AND "
            "credibility >= 0 AND credibility <= 1 AND "
            "authority_fit >= 0 AND authority_fit <= 1 AND "
            "insight_potential >= 0 AND insight_potential <= 1 AND "
            "total_score >= 0 AND total_score <= 1",
            name="ck_topic_candidates_scores",
        ),
    )
    op.create_index("ix_topic_candidates_cluster_key", "topic_candidates", ["cluster_key"])
    op.create_index("ix_topic_candidates_status", "topic_candidates", ["status"])
    op.create_index("ix_topic_candidates_total_score", "topic_candidates", ["total_score"])
    op.create_index(
        "ix_topic_candidates_scoring_config_id",
        "topic_candidates",
        ["scoring_config_id"],
    )
    op.create_index(
        "ix_topic_candidates_extraction_run_id",
        "topic_candidates",
        ["extraction_run_id"],
    )

    op.create_table(
        "topic_documents",
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topic_candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relevance_note", sa.String(length=500)),
    )
    op.create_index("ix_topic_documents_document_id", "topic_documents", ["document_id"])

    op.create_table(
        "evidence_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topic_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thesis", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("topic_id"),
    )

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evidence_pack_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_claims_confidence"),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'supported', 'disputed')",
            name="ck_claims_verification_status",
        ),
    )
    op.create_index("ix_claims_evidence_pack_id", "claims", ["evidence_pack_id"])

    op.create_table(
        "evidence_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_documents.id"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("locator", sa.String(length=500)),
        sa.Column("supports", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_evidence_sources_claim_id", "evidence_sources", ["claim_id"])
    op.create_index("ix_evidence_sources_document_id", "evidence_sources", ["document_id"])

    scoring_configs = sa.table(
        "scoring_configs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("version", sa.String()),
        sa.column("weights", sa.JSON()),
        sa.column("near_duplicate_threshold", sa.Numeric()),
        sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(
        scoring_configs,
        [
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000201"),
                "name": "default",
                "version": "v1",
                "weights": {
                    "freshness": "0.15",
                    "relevance": "0.20",
                    "novelty": "0.15",
                    "momentum": "0.10",
                    "credibility": "0.15",
                    "authority_fit": "0.10",
                    "insight_potential": "0.10",
                    "platform_fit": "0.05",
                },
                "near_duplicate_threshold": 0.85,
                "active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_sources_document_id", table_name="evidence_sources")
    op.drop_index("ix_evidence_sources_claim_id", table_name="evidence_sources")
    op.drop_table("evidence_sources")
    op.drop_index("ix_claims_evidence_pack_id", table_name="claims")
    op.drop_table("claims")
    op.drop_table("evidence_packs")
    op.drop_index("ix_topic_documents_document_id", table_name="topic_documents")
    op.drop_table("topic_documents")
    op.drop_index("ix_topic_candidates_extraction_run_id", table_name="topic_candidates")
    op.drop_index("ix_topic_candidates_scoring_config_id", table_name="topic_candidates")
    op.drop_index("ix_topic_candidates_total_score", table_name="topic_candidates")
    op.drop_index("ix_topic_candidates_status", table_name="topic_candidates")
    op.drop_index("ix_topic_candidates_cluster_key", table_name="topic_candidates")
    op.drop_table("topic_candidates")
    op.drop_index("ix_raw_documents_duplicate_of_id", table_name="raw_documents")
    op.drop_index("ix_raw_documents_content_hash", table_name="raw_documents")
    op.drop_index("ix_raw_documents_source_id", table_name="raw_documents")
    op.drop_table("raw_documents")
    op.drop_index("ix_scoring_configs_active", table_name="scoring_configs")
    op.drop_table("scoring_configs")
    op.drop_table("research_sources")
    op.execute("DROP EXTENSION IF EXISTS vector")
