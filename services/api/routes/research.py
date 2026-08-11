"""HTTP surface for M2 research sources, documents, topics, and evidence."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.dependencies import get_llm_client
from src.db.session import get_session
from src.llm.protocol import LLMClient
from src.research import service
from src.research.models import (
    EvidencePack,
    RawDocument,
    ResearchSource,
    ScoringConfig,
    TopicCandidate,
)
from src.research.schemas import (
    DocumentIngest,
    EvidencePackPut,
    EvidencePackRead,
    IngestionResult,
    RawDocumentRead,
    RefreshResult,
    ResearchSourceCreate,
    ResearchSourcePatch,
    ResearchSourceRead,
    ScoringConfigCreate,
    ScoringConfigRead,
    TopicCreate,
    TopicExtractionRequest,
    TopicRead,
    TopicRescore,
)

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/sources", response_model=list[ResearchSourceRead])
async def get_sources(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ResearchSource]:
    return await service.list_sources(session)


@router.post(
    "/sources",
    response_model=ResearchSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_source(
    payload: ResearchSourceCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ResearchSource:
    source = await service.create_source(session, payload)
    await session.commit()
    return source


@router.patch("/sources/{source_id}", response_model=ResearchSourceRead)
async def patch_source(
    source_id: uuid.UUID,
    payload: ResearchSourcePatch,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ResearchSource:
    source = await service.patch_source(session, source_id, payload)
    await session.commit()
    return source


@router.post("/sources/{source_id}/refresh", response_model=RefreshResult)
async def refresh_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RefreshResult:
    fetched, created, duplicates = await service.refresh_source(session, source_id)
    await session.commit()
    return RefreshResult(
        source_id=source_id,
        fetched=fetched,
        created=created,
        duplicates=duplicates,
    )


@router.get("/documents", response_model=list[RawDocumentRead])
async def get_documents(
    include_duplicates: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[RawDocument]:
    return await service.list_documents(session, include_duplicates=include_duplicates)


@router.post(
    "/documents",
    response_model=IngestionResult,
    status_code=status.HTTP_201_CREATED,
)
async def post_document(
    payload: DocumentIngest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> IngestionResult:
    result = await service.ingest_document(session, payload)
    await session.commit()
    return IngestionResult(
        document=RawDocumentRead.model_validate(result.document),
        outcome=result.outcome,
    )


@router.get("/documents/{document_id}", response_model=RawDocumentRead)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RawDocument:
    return await service.require_document(session, document_id)


@router.get("/scoring-configs", response_model=list[ScoringConfigRead])
async def get_scoring_configs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ScoringConfig]:
    return await service.list_scoring_configs(session)


@router.post(
    "/scoring-configs",
    response_model=ScoringConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_scoring_config(
    payload: ScoringConfigCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ScoringConfig:
    config = await service.create_scoring_config(session, payload)
    await session.commit()
    return config


@router.get("/topics", response_model=list[TopicRead])
async def get_topics(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[TopicCandidate]:
    return await service.list_topics(session)


@router.post("/extract", response_model=list[TopicRead])
async def post_topic_extraction(
    request: Request,
    payload: TopicExtractionRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> list[TopicCandidate]:
    topics = await service.extract_topics(
        session,
        llm,
        run_id=uuid.UUID(request.state.run_id),
        request=payload,
    )
    await session.commit()
    return topics


@router.post("/topics", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
async def post_topic(
    payload: TopicCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TopicCandidate:
    topic = await service.create_topic(session, payload)
    await session.commit()
    return topic


@router.get("/topics/{topic_id}", response_model=TopicRead)
async def get_topic(
    topic_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TopicCandidate:
    return await service.require_topic(session, topic_id)


@router.post("/topics/{topic_id}/rescore", response_model=TopicRead)
async def post_topic_rescore(
    topic_id: uuid.UUID,
    payload: TopicRescore,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TopicCandidate:
    topic = await service.rescore_topic(session, topic_id, payload)
    await session.commit()
    return topic


@router.get("/topics/{topic_id}/evidence", response_model=EvidencePackRead)
async def get_topic_evidence(
    topic_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> EvidencePack:
    return await service.get_evidence_pack(session, topic_id)


@router.put("/topics/{topic_id}/evidence", response_model=EvidencePackRead)
async def put_topic_evidence(
    topic_id: uuid.UUID,
    payload: EvidencePackPut,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> EvidencePack:
    pack = await service.put_evidence_pack(session, topic_id, payload)
    await session.commit()
    return pack
