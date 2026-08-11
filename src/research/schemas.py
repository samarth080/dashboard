"""Validated API and domain schemas for the Research Engine."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SCORE_COMPONENTS = (
    "freshness",
    "relevance",
    "novelty",
    "momentum",
    "credibility",
    "authority_fit",
    "insight_potential",
    "platform_fit",
)

IngestionOutcome = Literal[
    "created",
    "canonical_duplicate",
    "content_duplicate",
    "near_duplicate",
]


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResearchSourceCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["rss"] = "rss"
    url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True
    default_credibility: Decimal = Field(default=Decimal("0.500"), ge=0, le=1)
    configuration: dict[str, object] = Field(default_factory=dict)


class ResearchSourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    enabled: bool | None = None
    default_credibility: Decimal | None = Field(default=None, ge=0, le=1)
    configuration: dict[str, object] | None = None


class ResearchSourceRead(ORMResponse):
    id: uuid.UUID
    key: str
    name: str
    kind: str
    url: str
    enabled: bool
    default_credibility: Decimal
    configuration: dict[str, object]
    last_retrieved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentIngest(BaseModel):
    source_id: uuid.UUID | None = None
    external_id: str | None = Field(default=None, max_length=500)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=240)
    content: str = Field(min_length=1, max_length=1_000_000)
    language: str | None = Field(default=None, max_length=16)
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime | None = None
    credibility: Decimal | None = Field(default=None, ge=0, le=1)
    raw_metadata: dict[str, object] = Field(default_factory=dict)
    embedding: list[float] | None = Field(default=None, max_length=16_000)
    embedding_model: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def embedding_has_model(self) -> "DocumentIngest":
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("embedding and embedding_model must be provided together")
        return self


class RawDocumentRead(ORMResponse):
    id: uuid.UUID
    source_id: uuid.UUID | None
    external_id: str | None
    url: str
    canonical_url: str
    title: str
    author: str | None
    content: str
    language: str | None
    published_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    credibility: Decimal
    raw_metadata: dict[str, object]
    duplicate_of_id: uuid.UUID | None
    embedding_model: str | None
    created_at: datetime
    updated_at: datetime


class IngestionResult(BaseModel):
    document: RawDocumentRead
    outcome: IngestionOutcome


class RefreshResult(BaseModel):
    source_id: uuid.UUID
    fetched: int
    created: int
    duplicates: int


class ScoringWeights(BaseModel):
    freshness: Decimal = Field(ge=0)
    relevance: Decimal = Field(ge=0)
    novelty: Decimal = Field(ge=0)
    momentum: Decimal = Field(ge=0)
    credibility: Decimal = Field(ge=0)
    authority_fit: Decimal = Field(ge=0)
    insight_potential: Decimal = Field(ge=0)
    platform_fit: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def weight_sum_is_positive(self) -> "ScoringWeights":
        if sum(self.as_decimals().values(), start=Decimal("0")) <= 0:
            raise ValueError("at least one scoring weight must be positive")
        return self

    def as_decimals(self) -> dict[str, Decimal]:
        return {name: getattr(self, name) for name in SCORE_COMPONENTS}

    def as_storage(self) -> dict[str, str]:
        return {name: str(value) for name, value in self.as_decimals().items()}


class ScoringConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    weights: ScoringWeights
    near_duplicate_threshold: Decimal = Field(default=Decimal("0.850"), ge=0, le=1)
    active: bool = False


class ScoringConfigRead(ORMResponse):
    id: uuid.UUID
    name: str
    version: str
    weights: dict[str, object]
    near_duplicate_threshold: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("weights")
    @classmethod
    def weights_have_exact_keys(cls, value: dict[str, object]) -> dict[str, object]:
        if set(value) != set(SCORE_COMPONENTS):
            raise ValueError("stored scoring weights have invalid keys")
        return value


class PlatformFit(BaseModel):
    linkedin: Decimal = Field(ge=0, le=1)
    x: Decimal = Field(ge=0, le=1)

    def mean(self) -> Decimal:
        return (self.linkedin + self.x) / Decimal("2")

    def as_storage(self) -> dict[str, object]:
        return {"linkedin": str(self.linkedin), "x": str(self.x)}


class TopicScores(BaseModel):
    freshness: Decimal = Field(ge=0, le=1)
    relevance: Decimal = Field(ge=0, le=1)
    novelty: Decimal = Field(ge=0, le=1)
    momentum: Decimal = Field(ge=0, le=1)
    credibility: Decimal = Field(ge=0, le=1)
    authority_fit: Decimal = Field(ge=0, le=1)
    insight_potential: Decimal = Field(ge=0, le=1)
    platform_fit: PlatformFit

    def components(self) -> dict[str, Decimal]:
        values = {name: getattr(self, name) for name in SCORE_COMPONENTS if name != "platform_fit"}
        values["platform_fit"] = self.platform_fit.mean()
        return values


class TopicCreate(BaseModel):
    cluster_key: str | None = Field(default=None, min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=20_000)
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    scores: TopicScores
    scoring_config_id: uuid.UUID | None = None
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    embedding: list[float] | None = Field(default=None, max_length=16_000)
    embedding_model: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def embedding_has_model(self) -> "TopicCreate":
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("embedding and embedding_model must be provided together")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("document_ids must be unique")
        return self


class TopicRescore(BaseModel):
    scores: TopicScores
    scoring_config_id: uuid.UUID | None = None


class TopicRead(ORMResponse):
    id: uuid.UUID
    cluster_key: str
    title: str
    summary: str
    status: str
    freshness: Decimal
    relevance: Decimal
    novelty: Decimal
    momentum: Decimal
    credibility: Decimal
    authority_fit: Decimal
    insight_potential: Decimal
    platform_fit: dict[str, object]
    total_score: Decimal
    scoring_config_id: uuid.UUID
    scored_at: datetime
    extraction_run_id: uuid.UUID | None
    extraction_prompt_version: str | None
    embedding_model: str | None
    document_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class TopicSuggestion(BaseModel):
    cluster_key: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=20_000)
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    scores: TopicScores

    @field_validator("document_ids")
    @classmethod
    def documents_are_unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("document_ids must be unique")
        return value


class TopicExtractionOutput(BaseModel):
    topics: list[TopicSuggestion] = Field(default_factory=list, max_length=50)


class TopicExtractionRequest(BaseModel):
    document_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("document_ids")
    @classmethod
    def requested_documents_are_unique(
        cls, value: list[uuid.UUID] | None
    ) -> list[uuid.UUID] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("document_ids must be unique")
        return value


class EvidenceSourceInput(BaseModel):
    document_id: uuid.UUID
    excerpt: str = Field(min_length=10, max_length=20_000)
    locator: str | None = Field(default=None, max_length=500)
    supports: bool = True


class ClaimInput(BaseModel):
    statement: str = Field(min_length=1, max_length=20_000)
    confidence: Decimal = Field(ge=0, le=1)
    verification_status: Literal["unverified", "supported", "disputed"] = "unverified"
    sources: list[EvidenceSourceInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def supported_claim_has_source(self) -> "ClaimInput":
        if self.verification_status == "supported" and not any(
            source.supports for source in self.sources
        ):
            raise ValueError("a supported claim requires at least one supporting source")
        return self


class EvidencePackPut(BaseModel):
    thesis: str = Field(min_length=1, max_length=20_000)
    claims: list[ClaimInput] = Field(default_factory=list, max_length=200)


class EvidenceSourceRead(ORMResponse):
    id: uuid.UUID
    document_id: uuid.UUID
    excerpt: str
    locator: str | None
    supports: bool
    created_at: datetime
    updated_at: datetime


class ClaimRead(ORMResponse):
    id: uuid.UUID
    statement: str
    confidence: Decimal
    verification_status: str
    sources: list[EvidenceSourceRead]
    created_at: datetime
    updated_at: datetime


class EvidencePackRead(ORMResponse):
    id: uuid.UUID
    topic_id: uuid.UUID
    thesis: str
    claims: list[ClaimRead]
    created_at: datetime
    updated_at: datetime
