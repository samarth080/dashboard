from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.brain.schemas import MemoryUpsert, ProfileUpsert
from src.brain.service import list_memories, save_profile, upsert_memory


@pytest.mark.asyncio
async def test_memory_upsert_is_scoped_by_explicit_domain(db_session: AsyncSession) -> None:
    await save_profile(db_session, ProfileUpsert(display_name="Memory Tester"))
    first = await upsert_memory(
        db_session,
        MemoryUpsert(
            domain="career",
            key="target-role",
            value={"roles": ["Founder"]},
            source="user-profile",
            confidence=Decimal("1.000"),
        ),
    )
    second = await upsert_memory(
        db_session,
        MemoryUpsert(
            domain="career",
            key="target-role",
            value={"roles": ["Product Engineer"]},
            source="user-edit",
            confidence=Decimal("0.900"),
        ),
    )

    assert second.id == first.id
    memories = await list_memories(db_session, domain="career")
    assert len(memories) == 1
    assert memories[0].value == {"roles": ["Product Engineer"]}
    assert memories[0].confidence == Decimal("0.900")
