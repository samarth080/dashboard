"""HTTP surface for M1 Personal Brain data and voice analysis."""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.dependencies import get_llm_client
from src.brain import service
from src.brain.schemas import (
    CareerProfileRead,
    CareerProfileUpsert,
    InterestCreate,
    InterestRead,
    InterestUpdate,
    ProfileRead,
    ProfileUpsert,
    UserSettingsRead,
    UserSettingsUpsert,
    VoiceProfileRead,
    WritingSampleCreate,
    WritingSampleRead,
)
from src.db.session import get_session
from src.llm.protocol import LLMClient

router = APIRouter(tags=["personal-brain"])


@router.get("/profile", response_model=ProfileRead)
async def get_profile(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.UserProfile:
    return await service.require_primary_profile(session)


@router.put("/profile", response_model=ProfileRead)
async def put_profile(
    payload: ProfileUpsert,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.UserProfile:
    profile = await service.save_profile(session, payload)
    await session.commit()
    return profile


@router.get("/profile/career", response_model=CareerProfileRead)
async def get_career_profile(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.CareerProfile:
    return await service.get_career_profile(session)


@router.put("/profile/career", response_model=CareerProfileRead)
async def put_career_profile(
    payload: CareerProfileUpsert,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.CareerProfile:
    career = await service.save_career_profile(session, payload)
    await session.commit()
    return career


@router.get("/interests", response_model=list[InterestRead])
async def get_interests(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[service.Interest]:
    return await service.list_interests(session)


@router.post("/interests", response_model=InterestRead, status_code=status.HTTP_201_CREATED)
async def post_interest(
    payload: InterestCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.Interest:
    interest = await service.create_interest(session, payload)
    await session.commit()
    return interest


@router.patch("/interests/{interest_id}", response_model=InterestRead)
async def patch_interest(
    interest_id: uuid.UUID,
    payload: InterestUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.Interest:
    interest = await service.update_interest(session, interest_id, payload)
    await session.commit()
    return interest


@router.delete("/interests/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_interest(
    interest_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    await service.delete_interest(session, interest_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings", response_model=UserSettingsRead)
async def get_settings(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.UserSettings:
    settings = await service.get_user_settings(session)
    await session.commit()
    return settings


@router.put("/settings", response_model=UserSettingsRead)
async def put_settings(
    payload: UserSettingsUpsert,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.UserSettings:
    settings = await service.save_user_settings(session, payload)
    await session.commit()
    return settings


@router.get("/voice", response_model=VoiceProfileRead)
async def get_voice(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.VoiceProfile:
    return await service.get_voice_profile(session)


@router.get("/voice/samples", response_model=list[WritingSampleRead])
async def get_voice_samples(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[service.WritingSample]:
    return await service.list_writing_samples(session)


@router.post(
    "/voice/samples",
    response_model=WritingSampleRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_voice_sample(
    payload: WritingSampleCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> service.WritingSample:
    sample = await service.create_writing_sample(session, payload)
    await session.commit()
    return sample


@router.delete("/voice/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_voice_sample(
    sample_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    await service.delete_writing_sample(session, sample_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/voice/analyze", response_model=VoiceProfileRead)
async def post_voice_analysis(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    llm: LLMClient = Depends(get_llm_client),  # noqa: B008
) -> service.VoiceProfile:
    voice = await service.analyze_voice(
        session,
        llm,
        run_id=uuid.UUID(request.state.run_id),
    )
    await session.commit()
    return voice
