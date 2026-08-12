"""HTTP surface for M3 content workflows and local approval."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.dependencies import get_embedder, get_llm_client
from src.content import service
from src.content.models import ContentWorkflow
from src.content.schemas import (
    ApprovalDecisionInput,
    ContentWorkflowCreate,
    ContentWorkflowRead,
    EditableArtifactStage,
    ManualArtifactPut,
)
from src.db.session import get_session
from src.llm.embeddings import EmbeddingProvider
from src.llm.protocol import LLMClient
from src.memory import service as memory_service
from src.memory.models import DuplicateCheck
from src.memory.schemas import DuplicateCheckRead

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/workflows", response_model=list[ContentWorkflowRead])
async def get_workflows(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ContentWorkflow]:
    return await service.list_workflows(session)


@router.post(
    "/workflows",
    response_model=ContentWorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_workflow(
    payload: ContentWorkflowCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ContentWorkflow:
    workflow = await service.create_workflow(session, payload)
    await session.commit()
    return workflow


@router.get("/workflows/{workflow_id}", response_model=ContentWorkflowRead)
async def get_workflow(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ContentWorkflow:
    return await service.require_workflow(session, workflow_id)


@router.get(
    "/workflows/{workflow_id}/duplicate-checks",
    response_model=list[DuplicateCheckRead],
)
async def get_duplicate_checks(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[DuplicateCheck]:
    """Every duplicate verdict this workflow has received, newest first.

    Lives under /content rather than /memory because a check only exists in
    the context of a workflow's approval. `require_workflow` runs first so an
    unknown id is a 404 rather than an empty list that reads like "no checks".
    """
    await service.require_workflow(session, workflow_id)
    return await memory_service.list_duplicate_checks(session, workflow_id=workflow_id)


@router.post("/workflows/{workflow_id}/run", response_model=ContentWorkflowRead)
async def post_workflow_run(
    workflow_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> ContentWorkflow:
    workflow = await service.run_workflow(
        session,
        llm,
        workflow_id=workflow_id,
        run_id=uuid.UUID(request.state.run_id),
    )
    await session.commit()
    return workflow


@router.put("/workflows/{workflow_id}/artifacts/{stage}", response_model=ContentWorkflowRead)
async def put_artifact(
    workflow_id: uuid.UUID,
    stage: EditableArtifactStage,
    payload: ManualArtifactPut,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ContentWorkflow:
    workflow = await service.put_manual_artifact(
        session,
        workflow_id=workflow_id,
        stage=stage,
        data=payload,
        run_id=uuid.UUID(request.state.run_id),
    )
    await session.commit()
    return workflow


@router.post("/workflows/{workflow_id}/approval", response_model=ContentWorkflowRead)
async def post_approval(
    workflow_id: uuid.UUID,
    payload: ApprovalDecisionInput,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embedder: EmbeddingProvider = Depends(get_embedder),  # noqa: B008
) -> ContentWorkflow:
    try:
        workflow = await service.decide_approval(
            session,
            workflow_id=workflow_id,
            data=payload,
            run_id=uuid.UUID(request.state.run_id),
            embedder=embedder,
        )
    except service.DuplicateBlocked:
        # Commit the recorded duplicate check before the 409 unwinds the
        # request; nothing else was mutated, and a refusal with no stored
        # evidence of why is not inspectable.
        await session.commit()
        raise
    await session.commit()
    return workflow
