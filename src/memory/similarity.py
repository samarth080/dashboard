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

from src.research.dedup import token_similarity

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

    An empty vector raises for the same reason, but an all-zero vector is a
    valid embedding and returns 0.0 rather than dividing by zero: the M4
    embedder (Task 2's MockEmbedder) returns a zero vector for empty text, and
    that case must score as "no signal", not crash.

    The lower bound is clamped to 0.0 because anti-correlated vectors are not
    evidence of duplication — a negative cosine should read the same as "no
    similarity", not "similarity below zero". The upper bound is clamped to
    1.0 to absorb floating-point rounding: exact arithmetic on non-unit
    vectors can push `dot / (norm * norm)` a hair past 1.0, which would
    otherwise violate this function's own [0, 1] contract.
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
    return min(1.0, max(0.0, dot / (left_norm * right_norm)))


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

    `semantic` is computed only when both embeddings are present. A one-sided
    or absent embedding is not an error: post history rows may have a NULL
    vector (e.g. embedding backfill hasn't run yet), and such a row is scored
    lexically only, by design, rather than rejected.
    """
    lexical = token_similarity(candidate_text, neighbour_text)
    semantic: float | None = None
    if candidate_embedding is not None and neighbour_embedding is not None:
        semantic = cosine_similarity(candidate_embedding, neighbour_embedding)
    score = lexical if semantic is None else max(lexical, semantic)
    return SimilarityComponents(lexical=lexical, semantic=semantic, score=score)


def verdict_for(score: float, *, warn_threshold: float, block_threshold: float) -> DuplicateVerdict:
    """Map a score to a verdict against externally supplied thresholds.

    Bands are inclusive at the lower edge: a score exactly equal to
    `block_threshold` blocks, and a score exactly equal to `warn_threshold`
    warns. A threshold is a promise ("at this level or above, act"), and an
    exclusive edge would silently let the boundary value itself through.

    Threshold ordering is validated here even though the database constraint
    and the request schema also validate it: a pure function should not trust
    its caller, and this one is cheap enough to check unconditionally.
    """
    if warn_threshold > block_threshold:
        raise ValueError("warn threshold cannot exceed block threshold")
    if score >= block_threshold:
        return "block"
    if score >= warn_threshold:
        return "warn"
    return "clear"
