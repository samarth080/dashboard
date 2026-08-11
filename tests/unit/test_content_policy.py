import pytest

from src.content.policy import AutomationPolicy, PublicAction


def test_public_action_requires_explicit_approval_by_default() -> None:
    decision = AutomationPolicy().evaluate(PublicAction(platform="linkedin"), required_level=1)

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.required_level == 1


def test_explicit_approval_only_authorizes_the_local_policy_decision() -> None:
    decision = AutomationPolicy().evaluate(
        PublicAction(platform="x"),
        required_level=2,
        approval_decision="approved",
    )

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert "local approval" in decision.reason


def test_invalid_approval_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 3"):
        AutomationPolicy().evaluate(PublicAction(platform="x"), required_level=0)
