import uuid

import pytest
from pydantic import ValidationError

from src.content.schemas import AngleType, ContentWorkflowCreate


def test_workflow_supports_every_roadmap_angle() -> None:
    topic_id = uuid.uuid4()
    angle_types: set[AngleType] = {
        "technical",
        "product",
        "business",
        "career",
        "contrarian",
        "tutorial",
        "breakdown",
        "prediction",
        "case_study",
        "comparison",
        "framework",
    }

    for angle_type in angle_types:
        assert (
            ContentWorkflowCreate(topic_id=topic_id, angle_type=angle_type).angle_type == angle_type
        )


def test_workflow_rejects_duplicate_platforms() -> None:
    with pytest.raises(ValidationError, match="platforms must be unique"):
        ContentWorkflowCreate(topic_id=uuid.uuid4(), platforms=["x", "x"])
