"""Domain rules for content memory.

Transaction-neutral, matching M1 through M3: this module flushes so callers can
read generated keys, but never commits. Routes own the transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Run
from src.llm.embeddings import EmbeddingProvider
from src.llm.persistence import log_llm_call
from src.memory.analytics import AnalyticsProvider
from src.memory.models import DuplicateCheck, DuplicateConfig, PostMetricSnapshot, PostRecord
from src.memory.schemas import (
    DuplicateConfigCreate,
    DuplicateNeighbour,
    PostRecordCreate,
    PostRecordUpdate,
)
from src.memory.similarity import DuplicateVerdict, score_pair, verdict_for
from src.research.dedup import content_hash, normalize_content


class ContentMemoryError(Exception):
    # Deliberately not named MemoryError: that is a Python builtin.
    status_code = 400


class ContentMemoryNotFound(ContentMemoryError):
    status_code = 404


class ContentMemoryConflict(ContentMemoryError):
    status_code = 409


class ContentMemoryValidationError(ContentMemoryError):
    status_code = 422


class DuplicateEvaluation:
    """Result of one duplicate evaluation, before it is persisted."""

    def __init__(
        self,
        *,
        verdict: DuplicateVerdict,
        top_similarity: float,
        nearest_post_record_id: uuid.UUID | None,
        neighbours: list[DuplicateNeighbour],
        config_version: str,
    ) -> None:
        self.verdict = verdict
        self.top_similarity = top_similarity
        self.nearest_post_record_id = nearest_post_record_id
        self.neighbours = neighbours
        self.config_version = config_version


async def _ensure_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        run = Run(id=run_id)
        session.add(run)
        await session.flush()
    return run


async def _embed(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    text: str,
    run_id: uuid.UUID | None,
) -> tuple[list[float], str]:
    result = await embedder.embed([text])
    if run_id is not None:
        run = await _ensure_run(session, run_id)
        await log_llm_call(session, run, result)
    return result.vectors[0], result.usage.model


async def get_active_duplicate_config(session: AsyncSession) -> DuplicateConfig:
    config = (
        await session.execute(select(DuplicateConfig).where(DuplicateConfig.active.is_(True)))
    ).scalar_one_or_none()
    if config is None:
        raise ContentMemoryConflict(
            "no active duplicate configuration exists; create one before approving content"
        )
    return config


async def list_duplicate_configs(session: AsyncSession) -> list[DuplicateConfig]:
    result = await session.execute(
        select(DuplicateConfig).order_by(DuplicateConfig.created_at.desc())
    )
    return list(result.scalars().all())


async def create_duplicate_config(
    session: AsyncSession, data: DuplicateConfigCreate
) -> DuplicateConfig:
    existing = (
        await session.execute(
            select(DuplicateConfig).where(DuplicateConfig.version == data.version)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ContentMemoryConflict(f"duplicate configuration {data.version!r} already exists")
    if data.active:
        for current in (await session.execute(select(DuplicateConfig))).scalars().all():
            current.active = False
    config = DuplicateConfig(
        version=data.version,
        warn_threshold=data.warn_threshold,
        block_threshold=data.block_threshold,
        cross_platform_check=data.cross_platform_check,
        lookback_days=data.lookback_days,
        active=data.active,
    )
    session.add(config)
    await session.flush()
    return config


async def list_post_records(session: AsyncSession) -> list[PostRecord]:
    result = await session.execute(
        select(PostRecord)
        .options(selectinload(PostRecord.snapshots))
        .order_by(PostRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def require_post_record(session: AsyncSession, post_id: uuid.UUID) -> PostRecord:
    result = await session.execute(
        select(PostRecord)
        .options(selectinload(PostRecord.snapshots))
        .where(PostRecord.id == post_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ContentMemoryNotFound("post record not found")
    return record


async def create_post_record(
    session: AsyncSession,
    data: PostRecordCreate,
    *,
    embedder: EmbeddingProvider,
    run_id: uuid.UUID | None,
) -> PostRecord:
    """Record a post the user already published elsewhere.

    The service always embeds. Callers cannot supply a vector: an arbitrary
    client-supplied embedding would be stored under a real model's name, match
    the same-model filter during candidate selection, and then raise on the
    dimension mismatch — turning every later duplicate check and approval into
    a 500.
    """
    embedding, embedding_model = await _embed(session, embedder, data.content, run_id)
    record = PostRecord(
        platform=data.platform,
        origin="manual",
        # A manual backfill is by definition already published elsewhere.
        status="published_externally",
        workflow_id=None,
        content=data.content,
        normalized_content=normalize_content(data.content),
        content_hash=content_hash(data.content),
        posted_at=data.posted_at,
        external_url=data.external_url,
        embedding=embedding,
        embedding_model=embedding_model,
    )
    session.add(record)
    await session.flush()
    return record


async def record_workflow_post(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    platform: str,
    content: str,
    embedder: EmbeddingProvider,
    run_id: uuid.UUID | None,
) -> PostRecord:
    """Record an approved workflow draft as history.

    Idempotent: re-approving after a rejection updates the existing row rather
    than adding a second one, which the unique (workflow_id, platform)
    constraint would reject anyway.
    """
    existing = (
        await session.execute(
            select(PostRecord).where(
                PostRecord.workflow_id == workflow_id, PostRecord.platform == platform
            )
        )
    ).scalar_one_or_none()
    embedding, embedding_model = await _embed(session, embedder, content, run_id)
    if existing is not None:
        existing.content = content
        existing.normalized_content = normalize_content(content)
        existing.content_hash = content_hash(content)
        existing.embedding = embedding
        existing.embedding_model = embedding_model
        await session.flush()
        return existing
    record = PostRecord(
        platform=platform,
        origin="workflow",
        # Approval is a local decision. Nothing was published.
        status="approved_unpublished",
        workflow_id=workflow_id,
        content=content,
        normalized_content=normalize_content(content),
        content_hash=content_hash(content),
        embedding=embedding,
        embedding_model=embedding_model,
    )
    session.add(record)
    await session.flush()
    return record


async def update_post_record(
    session: AsyncSession, post_id: uuid.UUID, data: PostRecordUpdate
) -> PostRecord:
    record = await require_post_record(session, post_id)
    # Key off what the caller actually sent, not off None, so an explicit null
    # clears a field instead of being indistinguishable from omitting it.
    provided = data.model_fields_set
    if "status" in provided and data.status is not None:
        record.status = data.status
    if "posted_at" in provided:
        record.posted_at = data.posted_at
    if "external_url" in provided:
        record.external_url = data.external_url
    await session.flush()
    return record


async def delete_post_record(session: AsyncSession, post_id: uuid.UUID) -> None:
    record = await require_post_record(session, post_id)
    if record.origin == "workflow":
        raise ContentMemoryConflict(
            "a workflow-origin post record belongs to its workflow history and cannot be deleted"
        )
    await session.delete(record)
    await session.flush()


async def evaluate_duplicate(
    session: AsyncSession,
    *,
    text: str,
    platform: str,
    config: DuplicateConfig,
    embedder: EmbeddingProvider,
    exclude_workflow_id: uuid.UUID | None,
    run_id: uuid.UUID | None = None,
) -> DuplicateEvaluation:
    """Score `text` against post history under `config`.

    Candidates are prefiltered in SQL and scored in Python. Postgres cannot
    index these vectors without a fixed dimension, so a database-side nearest
    neighbour query would scan anyway while making the lexical signal
    impossible to blend.
    """
    embedding, embedding_model = await _embed(session, embedder, text, run_id)

    query = select(PostRecord)
    if not config.cross_platform_check:
        query = query.where(PostRecord.platform == platform)
    if exclude_workflow_id is not None:
        # A workflow must not block itself with its own recorded post.
        query = query.where(
            (PostRecord.workflow_id.is_(None)) | (PostRecord.workflow_id != exclude_workflow_id)
        )
    if config.lookback_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=config.lookback_days)
        query = query.where(PostRecord.created_at >= cutoff)

    candidates = list((await session.execute(query)).scalars().all())

    neighbours: list[DuplicateNeighbour] = []
    for candidate in candidates:
        # Only compare vectors from the same model: different models do not
        # share a space, and cosine_similarity raises on a dimension mismatch.
        # Require an actual vector, not just a matching model name: the column
        # is nullable, and a one-sided embedding would silently drop the
        # semantic signal.
        same_space = (
            candidate.embedding is not None and candidate.embedding_model == embedding_model
        )
        components = score_pair(
            candidate_text=text,
            neighbour_text=candidate.content,
            candidate_embedding=embedding if same_space else None,
            neighbour_embedding=candidate.embedding if same_space else None,
        )
        neighbours.append(
            DuplicateNeighbour(
                post_record_id=candidate.id,
                platform=candidate.platform,
                lexical=components.lexical,
                semantic=components.semantic,
                score=components.score,
            )
        )

    neighbours.sort(key=lambda item: item.score, reverse=True)
    top = neighbours[0] if neighbours else None
    top_score = top.score if top else 0.0
    verdict = verdict_for(
        top_score,
        warn_threshold=float(config.warn_threshold),
        block_threshold=float(config.block_threshold),
    )
    return DuplicateEvaluation(
        verdict=verdict,
        top_similarity=top_score,
        nearest_post_record_id=top.post_record_id if top else None,
        # Keep the ten nearest: enough to explain the verdict without storing
        # the entire corpus in every check row.
        neighbours=neighbours[:10],
        config_version=config.version,
    )


async def persist_duplicate_check(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    platform: str,
    evaluation: DuplicateEvaluation,
    overridden: bool,
    override_reason: str | None,
    run_id: uuid.UUID | None,
) -> DuplicateCheck:
    check = DuplicateCheck(
        workflow_id=workflow_id,
        platform=platform,
        config_version=evaluation.config_version,
        verdict=evaluation.verdict,
        top_similarity=Decimal(f"{evaluation.top_similarity:.3f}"),
        nearest_post_record_id=evaluation.nearest_post_record_id,
        components=[item.model_dump(mode="json") for item in evaluation.neighbours],
        overridden=overridden,
        override_reason=override_reason,
        run_id=run_id,
    )
    session.add(check)
    await session.flush()
    return check


async def capture_metrics(
    session: AsyncSession, *, post_id: uuid.UUID, provider: AnalyticsProvider
) -> PostMetricSnapshot:
    record = await require_post_record(session, post_id)
    metrics = await provider.fetch(
        post_id=record.id,
        platform=record.platform,
        posted_at=record.posted_at,
        now=datetime.now(UTC),
        # A real provider needs the platform-side identifier to fetch anything;
        # our own primary key is meaningless to LinkedIn or X.
        external_ref=record.external_url,
    )
    snapshot = PostMetricSnapshot(
        post_record_id=record.id,
        source=provider.name,
        is_mock=provider.is_mock,
        impressions=metrics.impressions,
        reactions=metrics.reactions,
        comments=metrics.comments,
        reposts=metrics.reposts,
        clicks=metrics.clicks,
        follows=metrics.follows,
    )
    # Append rather than session.add: the parent's already-loaded `snapshots`
    # collection would otherwise stay stale for the rest of the session, and a
    # caller that re-reads the record would not see the snapshot it just took.
    record.snapshots.append(snapshot)
    await session.flush()
    return snapshot
