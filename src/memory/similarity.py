"""Pure duplicate-scoring functions.

No session, no I/O, and no thresholds: thresholds are policy and live in the
database (`duplicate_configs`), exactly as M2 ranking weights do. Keeping this
module pure is what lets the whole scoring engine be unit-tested without a
container.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.research.dedup import content_hash, token_similarity

DuplicateVerdict = Literal["clear", "warn", "block"]


@dataclass(frozen=True)
class SimilarityComponents:
    """One candidate-vs-neighbour comparison, kept explainable.

    Both sub-scores are retained rather than only the combined number, so a
    verdict can always be shown as "why", not just "how much".
    """

    lexical: float
    semantic: float | None
    score: float


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity clamped to [0, 1].

    Raises on a dimension mismatch rather than returning a meaningless number:
    vectors from different embedding models do not share a space, and silently
    scoring them would make duplicate detection quietly wrong.
    """
    if len(left) != len(right):
        raise ValueError("cannot compare embeddings of different dimensions")
    if not left:
        raise ValueError("cannot compare empty embeddings")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, dot / (left_norm * right_norm))


def score_pair(
    *,
    candidate_text: str,
    neighbour_text: str,
    candidate_embedding: Sequence[float] | None = None,
    neighbour_embedding: Sequence[float] | None = None,
) -> SimilarityComponents:
    """Score one pair, combining the two signals with `max`.

    `max` rather than a weighted mean: a copy-paste scores 1.0 lexically and a
    reworded post scores high semantically, so either signal alone is
    sufficient evidence of duplication. Averaging would dilute each strong
    signal with the other's weakness.
    """
    exact = content_hash(candidate_text) == content_hash(neighbour_text)
    lexical = 1.0 if exact else token_similarity(candidate_text, neighbour_text)
    semantic: float | None = None
    if candidate_embedding is not None and neighbour_embedding is not None:
        semantic = cosine_similarity(candidate_embedding, neighbour_embedding)
    score = lexical if semantic is None else max(lexical, semantic)
    return SimilarityComponents(lexical=lexical, semantic=semantic, score=score)


def verdict_for(score: float, *, warn_threshold: float, block_threshold: float) -> DuplicateVerdict:
    if warn_threshold > block_threshold:
        raise ValueError("warn threshold cannot exceed block threshold")
    if score >= block_threshold:
        return "block"
    if score >= warn_threshold:
        return "warn"
    return "clear"
