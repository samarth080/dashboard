"""Validated API and workflow schemas for the Personal Brain."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

MemoryDomain = Literal[
    "personal",
    "voice",
    "content",
    "research",
    "relationship",
    "career",
    "performance",
]


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfileUpsert(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    headline: str | None = Field(default=None, max_length=240)
    bio: str | None = Field(default=None, max_length=10_000)
    location: str | None = Field(default=None, max_length=160)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        return value.strip()


class ProfileRead(ORMResponse):
    id: uuid.UUID
    display_name: str
    headline: str | None
    bio: str | None
    location: str | None
    created_at: datetime
    updated_at: datetime


class CareerProfileUpsert(BaseModel):
    current_title: str | None = Field(default=None, max_length=160)
    current_company: str | None = Field(default=None, max_length=160)
    years_experience: Decimal | None = Field(default=None, ge=0, le=80)
    target_roles: list[str] = Field(default_factory=list, max_length=50)
    target_industries: list[str] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=100)
    goals: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("target_roles", "target_industries", "skills", "goals")
    @classmethod
    def clean_string_list(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class CareerProfileRead(CareerProfileUpsert, ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class UserSettingsUpsert(BaseModel):
    timezone: str = Field(default="UTC", max_length=64)
    locale: str = Field(default="en", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    daily_llm_budget_usd: Decimal = Field(default=Decimal("5.00"), ge=0, le=100_000)
    public_action_approval_level: int = Field(default=1, ge=1, le=3)
    memory_enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown IANA timezone") from exc
        return value


class UserSettingsRead(UserSettingsUpsert, ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class InterestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)
    weight: Decimal = Field(default=Decimal("0.500"), ge=0, le=1)
    enabled: bool = True
    parent_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class InterestUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)
    weight: Decimal | None = Field(default=None, ge=0, le=1)
    enabled: bool | None = None
    parent_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class InterestRead(ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    weight: Decimal
    enabled: bool
    created_at: datetime
    updated_at: datetime


class WritingSampleCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    content: str = Field(min_length=50, max_length=50_000)
    source_label: str = Field(default="user_provided", min_length=1, max_length=80)
    confirmed_user_provided: Literal[True]


class WritingSampleRead(ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    title: str | None
    content: str
    source_label: str
    consent_confirmed_at: datetime
    created_at: datetime
    updated_at: datetime


class VoiceAnalysis(BaseModel):
    summary: str
    tone_descriptors: list[str]
    sentence_patterns: list[str]
    vocabulary_preferences: list[str]
    avoid_phrases: list[str]
    formatting_preferences: list[str]
    signature_traits: list[str]
    confidence: float = Field(ge=0, le=1)


class VoiceProfileRead(ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    summary: str
    tone_descriptors: list[str]
    sentence_patterns: list[str]
    vocabulary_preferences: list[str]
    avoid_phrases: list[str]
    formatting_preferences: list[str]
    signature_traits: list[str]
    sample_count: int
    confidence: Decimal
    analysis_prompt_version: str
    analyzed_at: datetime
    created_at: datetime
    updated_at: datetime


class MemoryUpsert(BaseModel):
    domain: MemoryDomain
    key: str = Field(min_length=1, max_length=160)
    value: dict[str, object]
    source: str = Field(min_length=1, max_length=160)
    confidence: Decimal = Field(default=Decimal("1.000"), ge=0, le=1)
    enabled: bool = True


class MemoryRead(MemoryUpsert, ORMResponse):
    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
