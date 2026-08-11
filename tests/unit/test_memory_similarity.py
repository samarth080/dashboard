import pytest

from src.memory.similarity import cosine_similarity, score_pair, verdict_for


def test_cosine_similarity_of_identical_vectors_is_one():
    assert cosine_similarity([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_clamps_negatives_to_zero():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_cosine_similarity_upper_bound_survives_float_rounding():
    # Exact float arithmetic on identical-but-not-unit vectors can round
    # dot / (norm * norm) to a hair above 1.0 (e.g. 1.0000000000000002).
    # The result must still respect the documented [0, 1] contract.
    assert cosine_similarity([0.1] * 10, [0.1] * 10) <= 1.0


def test_cosine_similarity_rejects_mismatched_dimensions():
    with pytest.raises(ValueError, match="different dimensions"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_similarity_rejects_empty_vectors():
    with pytest.raises(ValueError, match="empty"):
        cosine_similarity([], [])


def test_cosine_similarity_of_zero_vector_is_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_identical_text_scores_one_without_embeddings():
    components = score_pair(
        candidate_text="Evidence first, always.",
        neighbour_text="Evidence   first, always.",
    )
    assert components.lexical == 1.0
    assert components.score == 1.0


def test_unrelated_text_scores_low():
    components = score_pair(
        candidate_text="Kubernetes operators reconcile desired state.",
        neighbour_text="Sourdough needs a mature starter.",
    )
    assert components.score < 0.1
    assert components.semantic is None


def test_score_takes_the_max_of_lexical_and_semantic():
    # Different words, so lexical is near zero, but the vectors agree.
    components = score_pair(
        candidate_text="alpha beta gamma",
        neighbour_text="delta epsilon zeta",
        candidate_embedding=[1.0, 0.0],
        neighbour_embedding=[1.0, 0.0],
    )
    assert components.lexical < 0.1
    assert components.semantic == pytest.approx(1.0)
    assert components.score == pytest.approx(1.0)


def test_strong_lexical_signal_is_not_diluted_by_weak_semantic():
    components = score_pair(
        candidate_text="one two three four five",
        neighbour_text="one two three four five",
        candidate_embedding=[1.0, 0.0],
        neighbour_embedding=[0.0, 1.0],
    )
    assert components.score == 1.0


def test_verdict_bands():
    assert verdict_for(0.95, warn_threshold=0.7, block_threshold=0.85) == "block"
    assert verdict_for(0.85, warn_threshold=0.7, block_threshold=0.85) == "block"
    assert verdict_for(0.7, warn_threshold=0.7, block_threshold=0.85) == "warn"
    assert verdict_for(0.4, warn_threshold=0.7, block_threshold=0.85) == "clear"


def test_verdict_rejects_inverted_thresholds():
    with pytest.raises(ValueError, match="cannot exceed"):
        verdict_for(0.5, warn_threshold=0.9, block_threshold=0.6)
