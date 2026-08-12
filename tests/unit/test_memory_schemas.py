from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.memory.schemas import DuplicateConfigCreate, PostRecordCreate, PostRecordUpdate


def test_manual_post_requires_content():
    with pytest.raises(ValidationError):
        PostRecordCreate(platform="linkedin", content="")


def test_manual_post_accepts_minimum_fields():
    payload = PostRecordCreate(platform="x", content="A short post about evidence.")
    assert payload.status == "published_externally"
    assert payload.external_url is None


def test_embedding_and_model_must_be_provided_together():
    with pytest.raises(ValidationError, match="together"):
        PostRecordCreate(
            platform="linkedin", content="Body text", embedding=[0.1, 0.2], embedding_model=None
        )
    with pytest.raises(ValidationError, match="together"):
        PostRecordCreate(
            platform="linkedin", content="Body text", embedding=None, embedding_model="some-model"
        )


def test_supplied_embedding_pair_is_accepted():
    payload = PostRecordCreate(
        platform="linkedin",
        content="Body text",
        embedding=[0.1, 0.2],
        embedding_model="mock-embed-v1",
    )
    assert payload.embedding_model == "mock-embed-v1"


def test_update_rejects_an_empty_payload():
    with pytest.raises(ValidationError, match="at least one field"):
        PostRecordUpdate()


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
