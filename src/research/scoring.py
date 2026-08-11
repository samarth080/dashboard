"""Reproducible Decimal-based topic scoring with database-supplied weights."""

from decimal import ROUND_HALF_UP, Decimal

from src.research.schemas import ScoringWeights, TopicScores

SCORE_QUANTUM = Decimal("0.0001")


def calculate_total_score(scores: TopicScores, weights: ScoringWeights) -> Decimal:
    components = scores.components()
    weight_values = weights.as_decimals()
    denominator = sum(weight_values.values(), start=Decimal("0"))
    if denominator <= 0:
        raise ValueError("scoring weight sum must be positive")
    numerator = sum(
        (components[name] * weight_values[name] for name in weight_values),
        start=Decimal("0"),
    )
    return (numerator / denominator).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
