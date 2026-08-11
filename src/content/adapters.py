"""Platform-native content adapters; these never call platform APIs."""

from collections.abc import Sequence
from typing import Protocol


class PlatformContentAdapter(Protocol):
    platform: str
    prompt_name: str

    def fallback(self, thesis: str, claims: Sequence[str]) -> str: ...


class LinkedInContentAdapter:
    platform = "linkedin"
    prompt_name = "content-linkedin-adaptation"

    def fallback(self, thesis: str, claims: Sequence[str]) -> str:
        body = "\n\n".join(claims)
        closing = "What would you add or challenge?"
        return f"{thesis}\n\n{body}\n\n{closing}" if body else f"{thesis}\n\n{closing}"


def _wrap_words(text: str, limit: int = 230) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in text.split():
        added = len(word) + (1 if current else 0)
        if current and length + added > limit:
            chunks.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += added
    if current:
        chunks.append(" ".join(current))
    return chunks


class XContentAdapter:
    platform = "x"
    prompt_name = "content-x-adaptation"

    def fallback(self, thesis: str, claims: Sequence[str]) -> str:
        raw_posts: list[str] = []
        for value in (thesis, *claims):
            raw_posts.extend(_wrap_words(value))
        if len(raw_posts) <= 1:
            return raw_posts[0] if raw_posts else ""
        total = len(raw_posts)
        return "\n\n".join(
            f"{index}/{total} {post}" for index, post in enumerate(raw_posts, start=1)
        )
