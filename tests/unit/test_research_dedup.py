from src.research.dedup import content_hash, normalize_content, token_similarity


def test_content_hash_uses_normalized_unicode_and_whitespace() -> None:
    assert normalize_content("  a\n\n  useful   note ") == "a useful note"
    assert content_hash("a   useful note") == content_hash("a useful\nnote")


def test_token_similarity_detects_near_duplicate_text() -> None:
    original = "Design bounded agent workflows with explicit steps and persisted results."
    near_copy = (
        "Design bounded agent workflows with explicit steps and persisted results. "
        "This sentence is extra."
    )
    unrelated = "Markets opened lower while the central bank discussed interest rates."
    assert token_similarity(original, near_copy) > 0.6
    assert token_similarity(original, unrelated) == 0
