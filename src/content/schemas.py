"""Validated API and model-output schemas for the Content Engine."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AngleType = Literal[
    "technical",
    "product",
    "business",
    "career",
    "contrarian",
    "tutorial",
    "breakdown",
    "prediction",
    "case_study",
    "comparison",
    "framework",
]
Platform = Literal["linkedin", "x"]
ArtifactStage = Literal[
    "angle",
    "outline",
    "draft",
    "voice_transform",
    "fact_check",
    "quality_evaluation",
    "rewrite",
    "linkedin_adaptation",
    "x_adaptation",
]
EditableArtifactStage = Literal[
    "angle",
    "outline",
    "draft",
    "voice_transform",
    "rewrite",
    "linkedin_adaptation",
    "x_adaptation",
]


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GeneratedClaim(BaseModel):
    statement: str = Field(min_length=1, max_length=20_000)
    claim_id: uuid.UUID


class GeneratedContent(BaseModel):
    content: str = Field(default="", max_length=100_000)
    claims: list[GeneratedClaim] = Field(default_factory=list, max_length=200)
    notes: list[str] = Field(default_factory=list, max_length=50)


class ModelQualityJudgement(BaseModel):
    authenticity: Decimal = Field(default=Decimal("0.700"), ge=0, le=1)
    clarity: Decimal = Field(default=Decimal("0.700"), ge=0, le=1)
    usefulness: Decimal = Field(default=Decimal("0.700"), ge=0, le=1)
    explanations: list[str] = Field(default_factory=list, max_length=50)


class ContentWorkflowCreate(BaseModel):
    topic_id: uuid.UUID
    angle_type: AngleType = "framework"
    platforms: list[Platform] = Field(default_factory=lambda: ["linkedin", "x"], min_length=1)

    @field_validator("platforms")
    @classmethod
    def platforms_are_unique(cls, value: list[Platform]) -> list[Platform]:
        if len(set(value)) != len(value):
            raise ValueError("platforms must be unique")
        return value


class ManualArtifactPut(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    claims: list[GeneratedClaim] = Field(default_factory=list, max_length=200)
    note: str | None = Field(default=None, max_length=2_000)


class ApprovalDecisionInput(BaseModel):
    platform: Platform
    decision: Literal["approved", "rejected"]
    actor: str = Field(default="user", min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=10_000)
    duplicate_override: bool = False
    override_reason: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def override_requires_a_reason(self) -> "ApprovalDecisionInput":
        # Enforced here as well as by ck_duplicate_checks_override_reason: an
        # override that reached the database without a reason would surface as
        # a 500 IntegrityError rather than a 422 the caller can act on.
        if self.duplicate_override and not (self.override_reason or "").strip():
            raise ValueError("override_reason is required when duplicate_override is set")
        return self


class ContentClaimReferenceRead(ORMResponse):
    id: uuid.UUID
    claimed_claim_id: uuid.UUID
    resolved_claim_id: uuid.UUID | None
    statement: str
    created_at: datetime
    updated_at: datetime


class ContentArtifactRead(ORMResponse):
    id: uuid.UUID
    workflow_id: uuid.UUID
    stage: str
    revision: int
    content: str
    structured_data: dict[str, object]
    source: str
    prompt_version: str | None
    model: str | None
    run_id: uuid.UUID | None
    claim_references: list[ContentClaimReferenceRead]
    created_at: datetime
    updated_at: datetime


class ContentApprovalRead(ORMResponse):
    id: uuid.UUID
    workflow_id: uuid.UUID
    platform: str
    decision: str
    required_level: int
    actor: str | None
    reason: str | None
    decided_at: datetime | None
    decision_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ContentWorkflowRead(ORMResponse):
    id: uuid.UUID
    topic_id: uuid.UUID
    evidence_pack_id: uuid.UUID
    angle_type: str
    requested_platforms: list[str]
    current_stage: str
    status: str
    latest_run_id: uuid.UUID | None
    artifacts: list[ContentArtifactRead]
    approvals: list[ContentApprovalRead]
    created_at: datetime
    updated_at: datetime
