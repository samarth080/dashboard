"""HTTP surface for M4 content memory."""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.dependencies import get_embedder
from src.db.session import get_session
from src.llm.embeddings import EmbeddingProvider
from src.memory import service
from src.memory.analytics import MockAnalyticsProvider
from src.memory.models import DuplicateConfig, PostMetricSnapshot, PostRecord
from src.memory.schemas import (
    DuplicateConfigCreate,
    DuplicateConfigRead,
    DuplicatePreviewRequest,
    DuplicatePreviewResponse,
    PostMetricSnapshotRead,
    PostRecordCreate,
    PostRecordRead,
    PostRecordUpdate,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/posts", response_model=list[PostRecordRead])
async def get_posts(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[PostRecord]:
    return await service.list_post_records(session)


@router.post("/posts", response_model=PostRecordRead, status_code=status.HTTP_201_CREATED)
async def post_post(
    payload: PostRecordCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embedder: EmbeddingProvider = Depends(get_embedder),  # noqa: B008
) -> PostRecord:
    record = await service.create_post_record(
        session, payload, embedder=embedder, run_id=uuid.UUID(request.state.run_id)
    )
    await session.commit()
    # Re-read so the response carries the eagerly loaded snapshots collection
    # the read schema declares.
    return await service.require_post_record(session, record.id)


@router.get("/posts/{post_id}", response_model=PostRecordRead)
async def get_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostRecord:
    return await service.require_post_record(session, post_id)


@router.patch("/posts/{post_id}", response_model=PostRecordRead)
async def patch_post(
    post_id: uuid.UUID,
    payload: PostRecordUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostRecord:
    record = await service.update_post_record(session, post_id, payload)
    await session.commit()
    return record


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    await service.delete_post_record(session, post_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/posts/{post_id}/metrics", response_model=list[PostMetricSnapshotRead])
async def get_metrics(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[PostMetricSnapshot]:
    record = await service.require_post_record(session, post_id)
    return list(record.snapshots)


@router.post(
    "/posts/{post_id}/metrics",
    response_model=PostMetricSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_metrics(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostMetricSnapshot:
    snapshot = await service.capture_metrics(
        session, post_id=post_id, provider=MockAnalyticsProvider()
    )
    await session.commit()
    return snapshot


@router.get("/duplicate-configs", response_model=list[DuplicateConfigRead])
async def get_duplicate_configs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[DuplicateConfig]:
    return await service.list_duplicate_configs(session)


@router.post(
    "/duplicate-configs",
    response_model=DuplicateConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_duplicate_config(
    payload: DuplicateConfigCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DuplicateConfig:
    config = await service.create_duplicate_config(session, payload)
    await session.commit()
    return config


@router.post("/duplicate-check", response_model=DuplicatePreviewResponse)
async def post_duplicate_check(
    payload: DuplicatePreviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embedder: EmbeddingProvider = Depends(get_embedder),  # noqa: B008
) -> DuplicatePreviewResponse:
    config = await service.get_active_duplicate_config(session)
    evaluation = await service.evaluate_duplicate(
        session,
        text=payload.content,
        platform=payload.platform,
        config=config,
        embedder=embedder,
        exclude_workflow_id=None,
        run_id=uuid.UUID(request.state.run_id),
    )
    # A preview writes no verdict, but the embedding call it made is real
    # spend and is logged against the run; commit so that cost is not lost.
    await session.commit()
    return DuplicatePreviewResponse(
        verdict=evaluation.verdict,
        config_version=evaluation.config_version,
        top_similarity=evaluation.top_similarity,
        neighbours=evaluation.neighbours,
    )
