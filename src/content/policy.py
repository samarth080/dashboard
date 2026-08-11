"""Local approval policy for future public-facing actions."""

from dataclasses import dataclass
from typing import Literal

PublicPlatform = Literal["linkedin", "x"]


@dataclass(frozen=True)
class PublicAction:
    platform: PublicPlatform
    kind: str = "publish_content"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    required_level: int
    reason: str


class AutomationPolicy:
    def evaluate(
        self,
        action: PublicAction,
        *,
        required_level: int,
        approval_decision: str | None = None,
    ) -> PolicyDecision:
        if required_level not in (1, 2, 3):
            raise ValueError("approval level must be between 1 and 3")
        if approval_decision == "approved":
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                required_level=required_level,
                reason=f"{action.kind} for {action.platform} has explicit local approval",
            )
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            required_level=required_level,
            reason=f"{action.kind} for {action.platform} requires explicit approval",
        )
