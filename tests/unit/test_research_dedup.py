import unicodedata

from src.research.dedup import content_hash, normalize_content, token_similarity, tokenize


def test_content_hash_uses_normalized_unicode_and_whitespace() -> None:
    assert normalize_content("  a\n\n  useful   note ") == "a useful note"
    assert content_hash("a   useful note") == content_hash("a useful\nnote")


def test_tokenize_case_folds_and_normalizes_unicode_and_whitespace() -> None:
    # M4's embedder shares this tokenizer with M2's shingling, so both of
    # these properties matter beyond dedup: case folding and NFKC/whitespace
    # normalization must hold for any downstream consumer.
    assert tokenize("SHIP\n\nFAST") == ["ship", "fast"]
    composed = "café"  # single codepoint "é"
    decomposed = unicodedata.normalize("NFD", composed)  # "e" + combining acute accent
    assert composed != decomposed  # sanity: the two inputs really differ byte-for-byte
    assert tokenize(composed) == tokenize(decomposed)


def test_tokenize_retains_apostrophes_and_hyphens() -> None:
    assert tokenize("don't stop-start") == ["don't", "stop-start"]


def test_token_similarity_detects_near_duplicate_text() -> None:
    original = "Design bounded agent workflows with explicit steps and persisted results."
    near_copy = (
        "Design bounded agent workflows with explicit steps and persisted results. "
        "This sentence is extra."
    )
    unrelated = "Markets opened lower while the central bank discussed interest rates."
    assert token_similarity(original, near_copy) > 0.6
    assert token_similarity(original, unrelated) == 0
