"""ORM models for the editable Personal Brain introduced in M1."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

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

MEMORY_DOMAINS = (
    "personal",
    "voice",
    "content",
    "research",
    "relationship",
    "career",
    "performance",
)


class TimestampMixin:
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


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_key: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, default="primary"
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(240))
    bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(160))

    career_profile: Mapped[CareerProfile | None] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    settings: Mapped[UserSettings | None] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    voice_profile: Mapped[VoiceProfile | None] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    interests: Mapped[list[Interest]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    writing_samples: Mapped[list[WritingSample]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    memories: Mapped[list[MemoryRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class CareerProfile(TimestampMixin, Base):
    __tablename__ = "career_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True
    )
    current_title: Mapped[str | None] = mapped_column(String(160))
    current_company: Mapped[str | None] = mapped_column(String(160))
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    target_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    target_industries: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    goals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    profile: Mapped[UserProfile] = relationship(back_populates="career_profile")


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "public_action_approval_level BETWEEN 1 AND 3",
            name="ck_user_settings_approval_level",
        ),
        CheckConstraint("daily_llm_budget_usd >= 0", name="ck_user_settings_daily_budget"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    daily_llm_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("5.00")
    )
    public_action_approval_level: Mapped[int] = mapped_column(nullable=False, default=1)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profile: Mapped[UserProfile] = relationship(back_populates="settings")


class Interest(TimestampMixin, Base):
    __tablename__ = "interests"
    __table_args__ = (
        UniqueConstraint("profile_id", "normalized_name", name="uq_interests_profile_name"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_interests_weight"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interests.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.500"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profile: Mapped[UserProfile] = relationship(back_populates="interests")
    parent: Mapped[Interest | None] = relationship(
        back_populates="children", remote_side="Interest.id"
    )
    children: Mapped[list[Interest]] = relationship(back_populates="parent")


class WritingSample(TimestampMixin, Base):
    __tablename__ = "writing_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str] = mapped_column(String(80), nullable=False, default="user_provided")
    consent_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    profile: Mapped[UserProfile] = relationship(back_populates="writing_samples")


class VoiceProfile(TimestampMixin, Base):
    __tablename__ = "voice_profiles"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_voice_profiles_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    tone_descriptors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sentence_patterns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    vocabulary_preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    avoid_phrases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    formatting_preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signature_traits: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sample_count: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    analysis_prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    profile: Mapped[UserProfile] = relationship(back_populates="voice_profile")


class MemoryRecord(TimestampMixin, Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        UniqueConstraint("profile_id", "domain", "key", name="uq_memory_profile_domain_key"),
        CheckConstraint(
            "domain IN ('personal', 'voice', 'content', 'research', 'relationship', "
            "'career', 'performance')",
            name="ck_memory_records_domain",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_records_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("1.000")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profile: Mapped[UserProfile] = relationship(back_populates="memories")
