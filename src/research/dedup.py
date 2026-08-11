"""Deterministic text normalization, hashing, and near-duplicate similarity."""

import hashlib
import re
import unicodedata

_TOKEN = re.compile(r"[\w'-]+", re.UNICODE)


def normalize_content(content: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", content).split())


def content_hash(content: str) -> str:
    normalized = normalize_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _shingles(content: str, *, size: int = 3) -> set[tuple[str, ...]]:
    tokens = [token.casefold() for token in _TOKEN.findall(normalize_content(content))]
    if not tokens:
        return set()
    if len(tokens) < size:
        return {tuple(tokens)}
    return {tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def token_similarity(left: str, right: str) -> float:
    """Return word-trigram Jaccard similarity in the inclusive range [0, 1]."""
    left_shingles = _shingles(left)
    right_shingles = _shingles(right)
    if not left_shingles and not right_shingles:
        return 1.0
    if not left_shingles or not right_shingles:
        return 0.0
    return len(left_shingles & right_shingles) / len(left_shingles | right_shingles)
