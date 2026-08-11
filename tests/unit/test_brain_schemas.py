from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.brain.schemas import (
    InterestCreate,
    MemoryUpsert,
    UserSettingsUpsert,
    WritingSampleCreate,
)


def test_writing_sample_requires_affirmative_user_confirmation() -> None:
    with pytest.raises(ValidationError):
        WritingSampleCreate(
            content="This is intentionally long enough to be a valid writing sample for analysis.",
            confirmed_user_provided=False,  # pyright: ignore[reportArgumentType]
        )


def test_settings_reject_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="unknown IANA timezone"):
        UserSettingsUpsert(timezone="Mars/Olympus_Mons")


def test_interest_name_is_cleaned_and_weight_is_decimal() -> None:
    interest = InterestCreate(name="  Fintech  ", weight=Decimal("0.750"))
    assert interest.name == "Fintech"
    assert interest.weight == Decimal("0.750")


def test_memory_domain_is_closed_and_explicit() -> None:
    with pytest.raises(ValidationError):
        MemoryUpsert(
            domain="misc",  # pyright: ignore[reportArgumentType]
            key="example",
            value={"text": "value"},
            source="test",
        )
