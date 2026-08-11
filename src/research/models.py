"""ORM models for M2 source ingestion, topic ranking, and evidence provenance."""

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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models import utcnow


class ResearchTimestampMixin:
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


class ResearchSource(ResearchTimestampMixin, Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        CheckConstraint(
            "default_credibility >= 0 AND default_credibility <= 1",
            name="ck_research_sources_credibility",
        ),
        CheckConstraint("kind IN ('rss')", name="ck_research_sources_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="rss")
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_credibility: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.500")
    )
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list[RawDocument]] = relationship(back_populates="source")


class RawDocument(ResearchTimestampMixin, Base):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_documents_source_external"),
        CheckConstraint(
            "credibility >= 0 AND credibility <= 1", name="ck_raw_documents_credibility"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_sources.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credibility: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    raw_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="SET NULL"), index=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
    embedding_model: Mapped[str | None] = mapped_column(String(160))

    source: Mapped[ResearchSource | None] = relationship(back_populates="documents")
    duplicate_of: Mapped[RawDocument | None] = relationship(
        back_populates="duplicates", remote_side="RawDocument.id"
    )
    duplicates: Mapped[list[RawDocument]] = relationship(back_populates="duplicate_of")
    topic_links: Mapped[list[TopicDocument]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    evidence_sources: Mapped[list[EvidenceSource]] = relationship(back_populates="document")


class ScoringConfig(ResearchTimestampMixin, Base):
    __tablename__ = "scoring_configs"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_scoring_configs_name_version"),
        CheckConstraint(
            "near_duplicate_threshold >= 0 AND near_duplicate_threshold <= 1",
            name="ck_scoring_configs_duplicate_threshold",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    weights: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    near_duplicate_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    topics: Mapped[list[TopicCandidate]] = relationship(back_populates="scoring_config")


class TopicCandidate(ResearchTimestampMixin, Base):
    __tablename__ = "topic_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected')",
            name="ck_topic_candidates_status",
        ),
        CheckConstraint(
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate", index=True)
    freshness: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    relevance: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    novelty: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    momentum: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    credibility: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    authority_fit: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    insight_potential: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    platform_fit: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, index=True)
    scoring_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_configs.id"),
        nullable=False,
        index=True,
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), index=True
    )
    extraction_prompt_version: Mapped[str | None] = mapped_column(String(80))
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
    embedding_model: Mapped[str | None] = mapped_column(String(160))

    scoring_config: Mapped[ScoringConfig] = relationship(back_populates="topics")
    document_links: Mapped[list[TopicDocument]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    evidence_pack: Mapped[EvidencePack | None] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )

    @property
    def document_ids(self) -> list[uuid.UUID]:
        return [link.document_id for link in self.document_links]


class TopicDocument(Base):
    __tablename__ = "topic_documents"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topic_candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_documents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    relevance_note: Mapped[str | None] = mapped_column(String(500))

    topic: Mapped[TopicCandidate] = relationship(back_populates="document_links")
    document: Mapped[RawDocument] = relationship(back_populates="topic_links")


class EvidencePack(ResearchTimestampMixin, Base):
    __tablename__ = "evidence_packs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topic_candidates.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    thesis: Mapped[str] = mapped_column(Text, nullable=False)

    topic: Mapped[TopicCandidate] = relationship(back_populates="evidence_pack")
    claims: Mapped[list[Claim]] = relationship(back_populates="pack", cascade="all, delete-orphan")


class Claim(ResearchTimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_claims_confidence"),
        CheckConstraint(
            "verification_status IN ('unverified', 'supported', 'disputed')",
            name="ck_claims_verification_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified"
    )

    pack: Mapped[EvidencePack] = relationship(back_populates="claims")
    sources: Mapped[list[EvidenceSource]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class EvidenceSource(ResearchTimestampMixin, Base):
    __tablename__ = "evidence_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_documents.id"),
        nullable=False,
        index=True,
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str | None] = mapped_column(String(500))
    supports: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    claim: Mapped[Claim] = relationship(back_populates="sources")
    document: Mapped[RawDocument] = relationship(back_populates="evidence_sources")
