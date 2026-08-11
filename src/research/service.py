"""Transaction-neutral operations for research ingestion, ranking, and evidence."""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.brain.models import Interest
from src.brain.service import get_user_settings, require_primary_profile
from src.db.models import LLMCall, Run, utcnow
from src.llm.persistence import log_llm_call
from src.llm.protocol import LLMClient
from src.research.dedup import content_hash, normalize_content, token_similarity
from src.research.extraction import (
    TOPIC_EXTRACTION_PROMPT_NAME,
    TOPIC_EXTRACTION_PROMPT_VERSION,
    TopicExtractor,
)
from src.research.models import (
    Claim,
    EvidencePack,
    EvidenceSource,
    RawDocument,
    ResearchSource,
    ScoringConfig,
    TopicCandidate,
    TopicDocument,
)
from src.research.schemas import (
    DocumentIngest,
    EvidencePackPut,
    IngestionOutcome,
    ResearchSourceCreate,
    ResearchSourcePatch,
    ScoringConfigCreate,
    ScoringWeights,
    TopicCreate,
    TopicExtractionRequest,
    TopicRescore,
    TopicSuggestion,
)
from src.research.scoring import calculate_total_score
from src.research.sources import RSSSource, canonicalize_url

MAX_SIMILARITY_CANDIDATES = 1_000
_CLUSTER_SEPARATOR = re.compile(r"[^a-z0-9]+")


class ResearchError(Exception):
    status_code = 400


class ResearchNotFound(ResearchError):
    status_code = 404


class ResearchConflict(ResearchError):
    status_code = 409


class ResearchValidationError(ResearchError):
    status_code = 422


@dataclass(frozen=True)
class IngestedDocument:
    document: RawDocument
    outcome: IngestionOutcome


def normalize_cluster_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return _CLUSTER_SEPARATOR.sub("-", normalized).strip("-")[:200]


async def list_sources(session: AsyncSession) -> list[ResearchSource]:
    return list(await session.scalars(select(ResearchSource).order_by(ResearchSource.name)))


async def create_source(session: AsyncSession, data: ResearchSourceCreate) -> ResearchSource:
    if await session.scalar(select(ResearchSource.id).where(ResearchSource.key == data.key)):
        raise ResearchConflict("a research source with this key already exists")
    try:
        url = canonicalize_url(data.url)
    except ValueError as exc:
        raise ResearchValidationError(str(exc)) from exc
    source = ResearchSource(
        key=data.key,
        name=data.name.strip(),
        kind=data.kind,
        url=url,
        enabled=data.enabled,
        default_credibility=data.default_credibility,
        configuration=data.configuration,
    )
    session.add(source)
    await session.flush()
    return source


async def require_source(session: AsyncSession, source_id: uuid.UUID) -> ResearchSource:
    source = await session.get(ResearchSource, source_id)
    if source is None:
        raise ResearchNotFound("research source not found")
    return source


async def patch_source(
    session: AsyncSession, source_id: uuid.UUID, data: ResearchSourcePatch
) -> ResearchSource:
    source = await require_source(session, source_id)
    fields = data.model_fields_set
    for field in ("name", "enabled", "default_credibility", "configuration"):
        if field in fields:
            value = getattr(data, field)
            if value is None:
                raise ResearchValidationError(f"source {field} cannot be null")
            setattr(source, field, value)
    if "url" in fields:
        if data.url is None:
            raise ResearchValidationError("source url cannot be null")
        try:
            source.url = canonicalize_url(data.url)
        except ValueError as exc:
            raise ResearchValidationError(str(exc)) from exc
    await session.flush()
    return source


async def list_scoring_configs(session: AsyncSession) -> list[ScoringConfig]:
    return list(
        await session.scalars(
            select(ScoringConfig).order_by(ScoringConfig.name, ScoringConfig.version)
        )
    )


async def create_scoring_config(session: AsyncSession, data: ScoringConfigCreate) -> ScoringConfig:
    existing = await session.scalar(
        select(ScoringConfig.id).where(
            ScoringConfig.name == data.name,
            ScoringConfig.version == data.version,
        )
    )
    if existing is not None:
        raise ResearchConflict("this scoring configuration version already exists")
    if data.active:
        await session.execute(update(ScoringConfig).values(active=False))
    config = ScoringConfig(
        name=data.name,
        version=data.version,
        weights=data.weights.as_storage(),
        near_duplicate_threshold=data.near_duplicate_threshold,
        active=data.active,
    )
    session.add(config)
    await session.flush()
    return config


async def get_scoring_config(
    session: AsyncSession, config_id: uuid.UUID | None = None
) -> ScoringConfig:
    if config_id is not None:
        config = await session.get(ScoringConfig, config_id)
    else:
        config = await session.scalar(
            select(ScoringConfig)
            .where(ScoringConfig.active.is_(True))
            .order_by(ScoringConfig.updated_at.desc())
        )
    if config is None:
        raise ResearchNotFound("no active scoring configuration exists")
    return config


def _weights_from_config(config: ScoringConfig) -> ScoringWeights:
    try:
        return ScoringWeights.model_validate(config.weights)
    except ValueError as exc:
        raise ResearchValidationError("stored scoring configuration is invalid") from exc


async def list_documents(
    session: AsyncSession, *, include_duplicates: bool = False
) -> list[RawDocument]:
    query = select(RawDocument)
    if not include_duplicates:
        query = query.where(RawDocument.duplicate_of_id.is_(None))
    return list(
        await session.scalars(query.order_by(RawDocument.retrieved_at.desc(), RawDocument.id))
    )


async def require_document(session: AsyncSession, document_id: uuid.UUID) -> RawDocument:
    document = await session.get(RawDocument, document_id)
    if document is None:
        raise ResearchNotFound("research document not found")
    return document


async def ingest_document(
    session: AsyncSession,
    data: DocumentIngest,
    *,
    duplicate_threshold: Decimal | None = None,
) -> IngestedDocument:
    source = None
    if data.source_id is not None:
        source = await require_source(session, data.source_id)

    try:
        canonical_url = canonicalize_url(data.url)
    except ValueError as exc:
        raise ResearchValidationError(str(exc)) from exc

    existing = await session.scalar(
        select(RawDocument).where(RawDocument.canonical_url == canonical_url)
    )
    if existing is not None:
        return IngestedDocument(existing, "canonical_duplicate")

    if source is not None and data.external_id is not None:
        existing = await session.scalar(
            select(RawDocument).where(
                RawDocument.source_id == source.id,
                RawDocument.external_id == data.external_id,
            )
        )
        if existing is not None:
            return IngestedDocument(existing, "canonical_duplicate")

    normalized = normalize_content(data.content)
    if not normalized:
        raise ResearchValidationError("document content cannot be blank")
    digest = content_hash(normalized)
    existing = await session.scalar(
        select(RawDocument)
        .where(
            RawDocument.content_hash == digest,
            RawDocument.duplicate_of_id.is_(None),
        )
        .order_by(RawDocument.created_at)
    )
    if existing is not None:
        return IngestedDocument(existing, "content_duplicate")

    if duplicate_threshold is None:
        config = await get_scoring_config(session)
        duplicate_threshold = config.near_duplicate_threshold

    duplicate_of: RawDocument | None = None
    candidates = await session.scalars(
        select(RawDocument)
        .where(RawDocument.duplicate_of_id.is_(None))
        .order_by(RawDocument.retrieved_at.desc())
        .limit(MAX_SIMILARITY_CANDIDATES)
    )
    best_similarity = 0.0
    for candidate in candidates:
        similarity = token_similarity(normalized, candidate.content)
        if similarity > best_similarity:
            best_similarity = similarity
            duplicate_of = candidate
    is_near_duplicate = (
        duplicate_of is not None and Decimal(str(best_similarity)) >= duplicate_threshold
    )

    credibility = data.credibility
    if credibility is None:
        credibility = source.default_credibility if source else Decimal("0.500")
    document = RawDocument(
        source_id=source.id if source else None,
        external_id=data.external_id,
        url=data.url,
        canonical_url=canonical_url,
        title=data.title.strip(),
        author=data.author.strip() if data.author else None,
        content=normalized,
        language=data.language,
        published_at=data.published_at,
        retrieved_at=data.retrieved_at or utcnow(),
        content_hash=digest,
        credibility=credibility,
        raw_metadata=data.raw_metadata,
        duplicate_of_id=duplicate_of.id if is_near_duplicate and duplicate_of else None,
        embedding=data.embedding,
        embedding_model=data.embedding_model,
    )
    session.add(document)
    await session.flush()
    return IngestedDocument(document, "near_duplicate" if is_near_duplicate else "created")


async def refresh_source(session: AsyncSession, source_id: uuid.UUID) -> tuple[int, int, int]:
    source = await require_source(session, source_id)
    if not source.enabled:
        raise ResearchValidationError("research source is disabled")
    if source.kind != "rss":
        raise ResearchValidationError(f"unsupported research source kind: {source.kind}")
    try:
        documents = await RSSSource(source.url).fetch()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise ResearchValidationError(f"source refresh failed: {exc}") from exc

    config = await get_scoring_config(session)
    created = 0
    duplicates = 0
    for item in documents:
        result = await ingest_document(
            session,
            DocumentIngest(
                source_id=source.id,
                external_id=item.external_id,
                url=item.url,
                title=item.title,
                author=item.author,
                content=item.content,
                language=item.language,
                published_at=item.published_at,
                credibility=source.default_credibility,
                raw_metadata=item.raw_metadata,
            ),
            duplicate_threshold=config.near_duplicate_threshold,
        )
        if result.outcome == "created":
            created += 1
        else:
            duplicates += 1
    source.last_retrieved_at = utcnow()
    await session.flush()
    return len(documents), created, duplicates


async def list_topics(session: AsyncSession) -> list[TopicCandidate]:
    return list(
        await session.scalars(
            select(TopicCandidate)
            .options(selectinload(TopicCandidate.document_links))
            .order_by(TopicCandidate.total_score.desc(), TopicCandidate.created_at.desc())
        )
    )


async def require_topic(session: AsyncSession, topic_id: uuid.UUID) -> TopicCandidate:
    topic = await session.scalar(
        select(TopicCandidate)
        .where(TopicCandidate.id == topic_id)
        .options(selectinload(TopicCandidate.document_links))
    )
    if topic is None:
        raise ResearchNotFound("topic candidate not found")
    return topic


async def _canonical_document_ids(
    session: AsyncSession, document_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    canonical: list[uuid.UUID] = []
    for document_id in document_ids:
        document = await require_document(session, document_id)
        resolved = document.duplicate_of_id or document.id
        if resolved not in canonical:
            canonical.append(resolved)
    return canonical


async def create_topic(session: AsyncSession, data: TopicCreate) -> TopicCandidate:
    config = await get_scoring_config(session, data.scoring_config_id)
    total = calculate_total_score(data.scores, _weights_from_config(config))
    document_ids = await _canonical_document_ids(session, data.document_ids)
    cluster_key = normalize_cluster_key(data.cluster_key or data.title)
    if not cluster_key:
        raise ResearchValidationError("topic cluster key cannot be blank")
    topic = TopicCandidate(
        cluster_key=cluster_key,
        title=data.title.strip(),
        summary=data.summary.strip(),
        status=data.status,
        freshness=data.scores.freshness,
        relevance=data.scores.relevance,
        novelty=data.scores.novelty,
        momentum=data.scores.momentum,
        credibility=data.scores.credibility,
        authority_fit=data.scores.authority_fit,
        insight_potential=data.scores.insight_potential,
        platform_fit=data.scores.platform_fit.as_storage(),
        total_score=total,
        scoring_config_id=config.id,
        scored_at=utcnow(),
        embedding=data.embedding,
        embedding_model=data.embedding_model,
    )
    topic.document_links = [TopicDocument(document_id=document_id) for document_id in document_ids]
    session.add(topic)
    await session.flush()
    return topic


async def extract_topics(
    session: AsyncSession,
    llm: LLMClient,
    *,
    run_id: uuid.UUID,
    request: TopicExtractionRequest,
) -> list[TopicCandidate]:
    profile = await require_primary_profile(session)
    settings = await get_user_settings(session)
    day_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    spent_today = await session.scalar(
        select(func.coalesce(func.sum(LLMCall.cost_usd), Decimal("0"))).where(
            LLMCall.created_at >= day_start
        )
    )
    if Decimal(spent_today or 0) >= settings.daily_llm_budget_usd:
        raise ResearchValidationError("daily LLM budget is exhausted")

    if request.document_ids is not None:
        document_ids = await _canonical_document_ids(session, request.document_ids)
        documents = [await require_document(session, document_id) for document_id in document_ids]
    else:
        documents = list(
            await session.scalars(
                select(RawDocument)
                .where(RawDocument.duplicate_of_id.is_(None))
                .order_by(RawDocument.retrieved_at.desc())
                .limit(20)
            )
        )
    interests = list(
        await session.scalars(
            select(Interest)
            .where(Interest.profile_id == profile.id, Interest.enabled.is_(True))
            .order_by(Interest.weight.desc(), Interest.name)
        )
    )
    try:
        result = await TopicExtractor(llm).extract(documents, interests)
    except ValueError as exc:
        raise ResearchValidationError(str(exc)) from exc

    run = Run(id=run_id)
    session.add(run)
    await session.flush()
    await log_llm_call(session, run, result)

    allowed_ids = {document.id for document in documents}
    config = await get_scoring_config(session)
    weights = _weights_from_config(config)
    clustered: dict[str, tuple[TopicSuggestion, Decimal, list[uuid.UUID]]] = {}
    for suggestion in result.parsed.topics:
        cluster_key = normalize_cluster_key(suggestion.cluster_key)
        if not cluster_key or not set(suggestion.document_ids).issubset(allowed_ids):
            continue
        total = calculate_total_score(suggestion.scores, weights)
        existing = clustered.get(cluster_key)
        if existing is None:
            clustered[cluster_key] = (suggestion, total, list(suggestion.document_ids))
            continue
        best_suggestion, best_total, collected_ids = existing
        for document_id in suggestion.document_ids:
            if document_id not in collected_ids:
                collected_ids.append(document_id)
        if total > best_total:
            clustered[cluster_key] = (suggestion, total, collected_ids)
        else:
            clustered[cluster_key] = (best_suggestion, best_total, collected_ids)

    topics: list[TopicCandidate] = []
    for cluster_key, (suggestion, _total, document_ids) in clustered.items():
        topic = await create_topic(
            session,
            TopicCreate(
                cluster_key=cluster_key,
                title=suggestion.title,
                summary=suggestion.summary,
                document_ids=document_ids,
                scores=suggestion.scores,
                scoring_config_id=config.id,
            ),
        )
        topic.extraction_run_id = run.id
        topic.extraction_prompt_version = (
            f"{TOPIC_EXTRACTION_PROMPT_NAME}/{TOPIC_EXTRACTION_PROMPT_VERSION}"
        )
        topics.append(topic)
    await session.flush()
    return sorted(topics, key=lambda topic: topic.total_score, reverse=True)


async def rescore_topic(
    session: AsyncSession, topic_id: uuid.UUID, data: TopicRescore
) -> TopicCandidate:
    topic = await require_topic(session, topic_id)
    config = await get_scoring_config(session, data.scoring_config_id)
    topic.freshness = data.scores.freshness
    topic.relevance = data.scores.relevance
    topic.novelty = data.scores.novelty
    topic.momentum = data.scores.momentum
    topic.credibility = data.scores.credibility
    topic.authority_fit = data.scores.authority_fit
    topic.insight_potential = data.scores.insight_potential
    topic.platform_fit = data.scores.platform_fit.as_storage()
    topic.total_score = calculate_total_score(data.scores, _weights_from_config(config))
    topic.scoring_config_id = config.id
    topic.scored_at = utcnow()
    await session.flush()
    return topic


async def get_evidence_pack(session: AsyncSession, topic_id: uuid.UUID) -> EvidencePack:
    await require_topic(session, topic_id)
    pack = await session.scalar(
        select(EvidencePack)
        .where(EvidencePack.topic_id == topic_id)
        .options(selectinload(EvidencePack.claims).selectinload(Claim.sources))
    )
    if pack is None:
        raise ResearchNotFound("evidence pack not found")
    return pack


async def put_evidence_pack(
    session: AsyncSession, topic_id: uuid.UUID, data: EvidencePackPut
) -> EvidencePack:
    topic = await require_topic(session, topic_id)
    allowed_documents = {link.document_id for link in topic.document_links}
    referenced_documents = {source.document_id for claim in data.claims for source in claim.sources}
    if not referenced_documents.issubset(allowed_documents):
        raise ResearchValidationError(
            "evidence sources must reference documents linked to the topic"
        )

    existing_id = await session.scalar(
        select(EvidencePack.id).where(EvidencePack.topic_id == topic_id)
    )
    if existing_id is not None:
        await session.execute(delete(EvidencePack).where(EvidencePack.id == existing_id))
        await session.flush()

    pack = EvidencePack(topic_id=topic_id, thesis=data.thesis.strip())
    for claim_data in data.claims:
        claim = Claim(
            statement=claim_data.statement.strip(),
            confidence=claim_data.confidence,
            verification_status=claim_data.verification_status,
        )
        claim.sources = [
            EvidenceSource(
                document_id=source.document_id,
                excerpt=source.excerpt.strip(),
                locator=source.locator,
                supports=source.supports,
            )
            for source in claim_data.sources
        ]
        pack.claims.append(claim)
    session.add(pack)
    await session.flush()
    return pack
