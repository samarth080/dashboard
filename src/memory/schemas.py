"""Validated API schemas for content memory."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PostPlatform = Literal["linkedin", "x"]
PostOrigin = Literal["workflow", "manual"]
PostStatus = Literal["approved_unpublished", "published_externally"]
Verdict = Literal["clear", "warn", "block"]


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PostRecordCreate(BaseModel):
    """Manual backfill of a post already published elsewhere."""

    platform: PostPlatform
    content: str = Field(min_length=1, max_length=100_000)
    status: PostStatus = "published_externally"
    posted_at: datetime | None = None
    external_url: str | None = Field(default=None, max_length=2048)
    embedding: list[float] | None = Field(default=None, max_length=16_000)
    embedding_model: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def embedding_has_model(self) -> "PostRecordCreate":
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("embedding and embedding_model must be provided together")
        return self


class PostRecordUpdate(BaseModel):
    status: PostStatus | None = None
    posted_at: datetime | None = None
    external_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PostRecordUpdate":
        if self.status is None and self.posted_at is None and self.external_url is None:
            raise ValueError("provide at least one field to update")
        return self


class PostMetricSnapshotRead(ORMResponse):
    id: uuid.UUID
    captured_at: datetime
    source: str
    is_mock: bool
    impressions: int | None
    reactions: int | None
    comments: int | None
    reposts: int | None
    clicks: int | None
    follows: int | None


class PostRecordRead(ORMResponse):
    id: uuid.UUID
    platform: str
    origin: str
    status: str
    workflow_id: uuid.UUID | None
    content: str
    content_hash: str
    posted_at: datetime | None
    external_url: str | None
    embedding_model: str | None
    snapshots: list[PostMetricSnapshotRead]
    created_at: datetime
    updated_at: datetime


class DuplicateConfigCreate(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    warn_threshold: Decimal = Field(ge=0, le=1)
    block_threshold: Decimal = Field(ge=0, le=1)
    cross_platform_check: bool = False
    lookback_days: int | None = Field(default=None, gt=0)
    active: bool = True

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "DuplicateConfigCreate":
        if self.warn_threshold > self.block_threshold:
            raise ValueError("warn threshold cannot exceed block threshold")
        return self


class DuplicateConfigRead(ORMResponse):
    id: uuid.UUID
    version: str
    warn_threshold: Decimal
    block_threshold: Decimal
    cross_platform_check: bool
    lookback_days: int | None
    active: bool
    created_at: datetime


class DuplicateNeighbour(BaseModel):
    post_record_id: uuid.UUID
    platform: str
    lexical: float
    semantic: float | None
    score: float


class DuplicateCheckRead(ORMResponse):
    id: uuid.UUID
    workflow_id: uuid.UUID
    platform: str
    config_version: str
    verdict: str
    top_similarity: Decimal
    nearest_post_record_id: uuid.UUID | None
    components: list[dict[str, object]]
    overridden: bool
    override_reason: str | None
    created_at: datetime


class DuplicatePreviewRequest(BaseModel):
    """Ad-hoc check of arbitrary text, before a workflow exists."""

    platform: PostPlatform
    content: str = Field(min_length=1, max_length=100_000)


class DuplicatePreviewResponse(BaseModel):
    verdict: Verdict
    config_version: str
    top_similarity: float
    neighbours: list[DuplicateNeighbour]
