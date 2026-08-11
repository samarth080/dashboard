import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.research.schemas import (
    ClaimInput,
    EvidenceSourceInput,
    PlatformFit,
    ScoringWeights,
    TopicScores,
)
from src.research.scoring import calculate_total_score


def equal_weights() -> ScoringWeights:
    one = Decimal("1")
    return ScoringWeights(
        freshness=one,
        relevance=one,
        novelty=one,
        momentum=one,
        credibility=one,
        authority_fit=one,
        insight_potential=one,
        platform_fit=one,
    )


def test_total_score_is_reproducible_decimal_weighted_mean() -> None:
    scores = TopicScores(
        freshness=Decimal("1.0"),
        relevance=Decimal("0.8"),
        novelty=Decimal("0.6"),
        momentum=Decimal("0.4"),
        credibility=Decimal("0.9"),
        authority_fit=Decimal("0.7"),
        insight_potential=Decimal("0.5"),
        platform_fit=PlatformFit(linkedin=Decimal("1.0"), x=Decimal("0.6")),
    )
    assert calculate_total_score(scores, equal_weights()) == Decimal("0.7125")


def test_scoring_weights_reject_all_zero_configuration() -> None:
    zero = Decimal("0")
    with pytest.raises(ValidationError, match="at least one"):
        ScoringWeights(
            freshness=zero,
            relevance=zero,
            novelty=zero,
            momentum=zero,
            credibility=zero,
            authority_fit=zero,
            insight_potential=zero,
            platform_fit=zero,
        )


def test_supported_claim_requires_supporting_source() -> None:
    with pytest.raises(ValidationError, match="supporting source"):
        ClaimInput(
            statement="A claim",
            confidence=Decimal("0.8"),
            verification_status="supported",
            sources=[],
        )

    claim = ClaimInput(
        statement="A claim",
        confidence=Decimal("0.8"),
        verification_status="supported",
        sources=[
            EvidenceSourceInput(
                document_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                excerpt="A sufficiently specific supporting excerpt.",
            )
        ],
    )
    assert claim.verification_status == "supported"
