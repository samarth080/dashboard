"""Transaction-neutral domain operations for Personal Brain data."""

import unicodedata
import uuid
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.brain.models import (
    CareerProfile,
    Interest,
    MemoryRecord,
    UserProfile,
    UserSettings,
    VoiceProfile,
    WritingSample,
)
from src.brain.schemas import (
    CareerProfileUpsert,
    InterestCreate,
    InterestUpdate,
    MemoryUpsert,
    ProfileUpsert,
    UserSettingsUpsert,
    WritingSampleCreate,
)
from src.brain.voice import VOICE_PROMPT_NAME, VOICE_PROMPT_VERSION, VoiceAnalyzer
from src.db.models import LLMCall, Run, utcnow
from src.llm.persistence import log_llm_call
from src.llm.protocol import LLMClient

PRIMARY_PROFILE_KEY = "primary"


class BrainError(Exception):
    status_code = 400


class BrainNotFound(BrainError):
    status_code = 404


class BrainConflict(BrainError):
    status_code = 409


class BrainValidationError(BrainError):
    status_code = 422


async def get_primary_profile(session: AsyncSession) -> UserProfile | None:
    return await session.scalar(
        select(UserProfile).where(UserProfile.profile_key == PRIMARY_PROFILE_KEY)
    )


async def require_primary_profile(session: AsyncSession) -> UserProfile:
    profile = await get_primary_profile(session)
    if profile is None:
        raise BrainNotFound("create the primary profile first")
    return profile


async def save_profile(session: AsyncSession, data: ProfileUpsert) -> UserProfile:
    profile = await get_primary_profile(session)
    values = data.model_dump()
    if profile is None:
        profile = UserProfile(profile_key=PRIMARY_PROFILE_KEY, **values)
        profile.settings = UserSettings()
        session.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)
    await session.flush()
    return profile


async def get_career_profile(session: AsyncSession) -> CareerProfile:
    profile = await require_primary_profile(session)
    career = await session.scalar(
        select(CareerProfile).where(CareerProfile.profile_id == profile.id)
    )
    if career is None:
        raise BrainNotFound("career profile has not been created")
    return career


async def save_career_profile(session: AsyncSession, data: CareerProfileUpsert) -> CareerProfile:
    profile = await require_primary_profile(session)
    career = await session.scalar(
        select(CareerProfile).where(CareerProfile.profile_id == profile.id)
    )
    values = data.model_dump()
    if career is None:
        career = CareerProfile(profile_id=profile.id, **values)
        session.add(career)
    else:
        for field, value in values.items():
            setattr(career, field, value)
    await session.flush()
    return career


async def get_user_settings(session: AsyncSession) -> UserSettings:
    profile = await require_primary_profile(session)
    settings = await session.scalar(
        select(UserSettings).where(UserSettings.profile_id == profile.id)
    )
    if settings is None:
        settings = UserSettings(profile_id=profile.id)
        session.add(settings)
        await session.flush()
    return settings


async def save_user_settings(session: AsyncSession, data: UserSettingsUpsert) -> UserSettings:
    settings = await get_user_settings(session)
    for field, value in data.model_dump().items():
        setattr(settings, field, value)
    await session.flush()
    return settings


def normalize_interest_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold().strip()


async def list_interests(session: AsyncSession) -> list[Interest]:
    profile = await require_primary_profile(session)
    result = await session.scalars(
        select(Interest)
        .where(Interest.profile_id == profile.id)
        .order_by(Interest.name, Interest.id)
    )
    return list(result)


async def _get_interest(
    session: AsyncSession, profile_id: uuid.UUID, interest_id: uuid.UUID
) -> Interest:
    interest = await session.get(Interest, interest_id)
    if interest is None or interest.profile_id != profile_id:
        raise BrainNotFound("interest not found")
    return interest


async def _assert_interest_name_available(
    session: AsyncSession,
    profile_id: uuid.UUID,
    normalized_name: str,
    *,
    excluding_id: uuid.UUID | None = None,
) -> None:
    query = select(Interest.id).where(
        Interest.profile_id == profile_id,
        Interest.normalized_name == normalized_name,
    )
    if excluding_id is not None:
        query = query.where(Interest.id != excluding_id)
    if await session.scalar(query) is not None:
        raise BrainConflict("an interest with this name already exists")


async def _validate_interest_parent(
    session: AsyncSession,
    profile_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    *,
    interest_id: uuid.UUID | None = None,
) -> None:
    if parent_id is None:
        return
    if parent_id == interest_id:
        raise BrainValidationError("an interest cannot be its own parent")

    parent = await _get_interest(session, profile_id, parent_id)
    visited: set[uuid.UUID] = set()
    cursor: Interest | None = parent
    while cursor is not None:
        if cursor.id in visited:
            raise BrainValidationError("the existing interest hierarchy contains a cycle")
        visited.add(cursor.id)
        if cursor.id == interest_id:
            raise BrainValidationError("the selected parent would create an interest cycle")
        if cursor.parent_id is None:
            break
        cursor = await _get_interest(session, profile_id, cursor.parent_id)


async def create_interest(session: AsyncSession, data: InterestCreate) -> Interest:
    profile = await require_primary_profile(session)
    normalized_name = normalize_interest_name(data.name)
    await _assert_interest_name_available(session, profile.id, normalized_name)
    await _validate_interest_parent(session, profile.id, data.parent_id)
    interest = Interest(
        profile_id=profile.id,
        name=data.name,
        normalized_name=normalized_name,
        description=data.description,
        weight=data.weight,
        enabled=data.enabled,
        parent_id=data.parent_id,
    )
    session.add(interest)
    await session.flush()
    return interest


async def update_interest(
    session: AsyncSession, interest_id: uuid.UUID, data: InterestUpdate
) -> Interest:
    profile = await require_primary_profile(session)
    interest = await _get_interest(session, profile.id, interest_id)
    fields = data.model_fields_set

    if "name" in fields:
        if data.name is None:
            raise BrainValidationError("interest name cannot be null")
        normalized_name = normalize_interest_name(data.name)
        await _assert_interest_name_available(
            session, profile.id, normalized_name, excluding_id=interest.id
        )
        interest.name = data.name
        interest.normalized_name = normalized_name
    if "description" in fields:
        interest.description = data.description
    if "weight" in fields:
        if data.weight is None:
            raise BrainValidationError("interest weight cannot be null")
        interest.weight = data.weight
    if "enabled" in fields:
        if data.enabled is None:
            raise BrainValidationError("interest enabled flag cannot be null")
        interest.enabled = data.enabled
    if "parent_id" in fields:
        await _validate_interest_parent(
            session, profile.id, data.parent_id, interest_id=interest.id
        )
        interest.parent_id = data.parent_id

    await session.flush()
    return interest


async def delete_interest(session: AsyncSession, interest_id: uuid.UUID) -> None:
    profile = await require_primary_profile(session)
    interest = await _get_interest(session, profile.id, interest_id)
    await session.delete(interest)
    await session.flush()


async def list_writing_samples(session: AsyncSession) -> list[WritingSample]:
    profile = await require_primary_profile(session)
    result = await session.scalars(
        select(WritingSample)
        .where(WritingSample.profile_id == profile.id)
        .order_by(WritingSample.created_at, WritingSample.id)
    )
    return list(result)


async def create_writing_sample(session: AsyncSession, data: WritingSampleCreate) -> WritingSample:
    profile = await require_primary_profile(session)
    sample = WritingSample(
        profile_id=profile.id,
        title=data.title,
        content=data.content,
        source_label=data.source_label,
        consent_confirmed_at=utcnow(),
    )
    session.add(sample)
    await session.flush()
    return sample


async def delete_writing_sample(session: AsyncSession, sample_id: uuid.UUID) -> None:
    profile = await require_primary_profile(session)
    sample = await session.get(WritingSample, sample_id)
    if sample is None or sample.profile_id != profile.id:
        raise BrainNotFound("writing sample not found")
    await session.delete(sample)
    await session.flush()


async def get_voice_profile(session: AsyncSession) -> VoiceProfile:
    profile = await require_primary_profile(session)
    voice = await session.scalar(select(VoiceProfile).where(VoiceProfile.profile_id == profile.id))
    if voice is None:
        raise BrainNotFound("voice profile has not been analyzed")
    return voice


async def analyze_voice(
    session: AsyncSession,
    llm: LLMClient,
    *,
    run_id: uuid.UUID,
) -> VoiceProfile:
    profile = await require_primary_profile(session)
    settings = await get_user_settings(session)
    day_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    spent_today = await session.scalar(
        select(func.coalesce(func.sum(LLMCall.cost_usd), Decimal("0"))).where(
            LLMCall.created_at >= day_start
        )
    )
    if Decimal(spent_today or 0) >= settings.daily_llm_budget_usd:
        raise BrainValidationError("daily LLM budget is exhausted")

    samples = await list_writing_samples(session)
    if not samples:
        raise BrainValidationError("add a confirmed writing sample before analysis")

    try:
        result = await VoiceAnalyzer(llm).analyze([sample.content for sample in samples])
    except ValueError as exc:
        raise BrainValidationError(str(exc)) from exc

    run = Run(id=run_id)
    session.add(run)
    await session.flush()
    await log_llm_call(session, run, result)

    voice = await session.scalar(select(VoiceProfile).where(VoiceProfile.profile_id == profile.id))
    analysis = result.parsed
    values: dict[str, object] = {
        "summary": analysis.summary,
        "tone_descriptors": analysis.tone_descriptors,
        "sentence_patterns": analysis.sentence_patterns,
        "vocabulary_preferences": analysis.vocabulary_preferences,
        "avoid_phrases": analysis.avoid_phrases,
        "formatting_preferences": analysis.formatting_preferences,
        "signature_traits": analysis.signature_traits,
        "sample_count": len(samples),
        "confidence": Decimal(str(analysis.confidence)),
        "analysis_prompt_version": f"{VOICE_PROMPT_NAME}/{VOICE_PROMPT_VERSION}",
        "analyzed_at": utcnow(),
    }
    if voice is None:
        voice = VoiceProfile(profile_id=profile.id, **values)
        session.add(voice)
    else:
        for field, value in values.items():
            setattr(voice, field, value)
    await session.flush()
    return voice


async def upsert_memory(session: AsyncSession, data: MemoryUpsert) -> MemoryRecord:
    profile = await require_primary_profile(session)
    record = await session.scalar(
        select(MemoryRecord).where(
            MemoryRecord.profile_id == profile.id,
            MemoryRecord.domain == data.domain,
            MemoryRecord.key == data.key,
        )
    )
    values = data.model_dump()
    if record is None:
        record = MemoryRecord(profile_id=profile.id, **values)
        session.add(record)
    else:
        for field, value in values.items():
            setattr(record, field, value)
    await session.flush()
    return record


async def list_memories(session: AsyncSession, *, domain: str | None = None) -> list[MemoryRecord]:
    profile = await require_primary_profile(session)
    query = select(MemoryRecord).where(MemoryRecord.profile_id == profile.id)
    if domain is not None:
        query = query.where(MemoryRecord.domain == domain)
    result = await session.scalars(query.order_by(MemoryRecord.domain, MemoryRecord.key))
    return list(result)
