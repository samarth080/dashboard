from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.memory.schemas import DuplicateConfigCreate, PostRecordCreate, PostRecordUpdate


def test_manual_post_requires_content():
    with pytest.raises(ValidationError):
        PostRecordCreate(platform="linkedin", content="")


def test_manual_post_accepts_minimum_fields():
    payload = PostRecordCreate(platform="x", content="A short post about evidence.")
    assert payload.external_url is None


def test_update_rejects_an_empty_payload():
    with pytest.raises(ValidationError, match="at least one field"):
        PostRecordUpdate()


def test_update_accepts_an_explicit_null_as_a_provided_field():
    # None must be distinguishable from "omitted": an explicit null is how a
    # caller clears a previously set value, so it counts as a provided field
    # rather than tripping the empty-payload check above.
    payload = PostRecordUpdate(external_url=None)
    assert "external_url" in payload.model_fields_set
    assert payload.external_url is None


def test_duplicate_config_rejects_warn_above_block():
    with pytest.raises(ValidationError, match="cannot exceed"):
        DuplicateConfigCreate(
            version="v2", warn_threshold=Decimal("0.900"), block_threshold=Decimal("0.800")
        )


def test_duplicate_config_accepts_valid_thresholds():
    config = DuplicateConfigCreate(
        version="v2", warn_threshold=Decimal("0.650"), block_threshold=Decimal("0.900")
    )
    assert config.cross_platform_check is False
    assert config.lookback_days is None
