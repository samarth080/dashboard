"""Contract shared by every embedding provider implementation (mock or real).

Mirrors `LLMClient` deliberately: the same two rules hold. Providers never
persist, and every result carries accurate usage metadata, so embedding spend
lands in `llm_calls` alongside generation spend instead of going untracked.
"""

import hashlib
import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel

from src.llm.protocol import LLMResult
from src.research.dedup import tokenize


class EmbeddingResult(BaseModel):
    """Vectors plus the usage metadata needed to cost-log the call.

    Shaped like `StructuredResult` (payload + `usage`) so `log_llm_call`
    accepts it without forking its logic. `usage.text` is empty because an
    embedding call returns no text.
    """

    vectors: list[list[float]]
    usage: LLMResult


class EmbeddingProvider(Protocol):
    """Contract every embedding provider must satisfy.

    - Return accurate usage metadata on every call.
    - Raise on failure rather than returning a placeholder vector; a silently
      wrong vector would corrupt duplicate detection instead of failing it.
    - Never persist anything. The caller owns persistence.
    - Return exactly one vector per input text, **in input order**. This is
      the load-bearing invariant of any batch embed API — callers zip
      `vectors` against their input list by position, not by content. Real
      providers return an explicit index field precisely because wire order
      is not guaranteed; an implementation wrapping one must restore input
      order before returning.
    - Chunk to the underlying provider's batch/input-size limits itself; the
      caller is not expected to know them. If an implementation splits one
      `embed()` call into multiple provider requests, it must aggregate
      `usage` across them: sum `input_tokens`, `output_tokens`, and
      `cost_usd`; report `latency_ms` as wall-clock time for the whole call,
      not the sum of the parts.
    - `embed([])` behavior is implementation-defined. Most real providers
      reject an empty batch, so callers must not rely on a permissive mock
      accepting one.
    - `usage.model` is authoritative for what gets stored as
      `embedding_model`, not the model name the caller configured — a real
      provider may resolve an alias (e.g. "latest") to a concrete version.
      Vectors must only ever be compared within the same stored model
      string; a vector from one model is not in the same space as a vector
      from another.
    """

    @property
    def model(self) -> str: ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...


class MockEmbedder:
    """Deterministic, credential-free `EmbeddingProvider`.

    Hashes tokens into a fixed-width bag-of-words vector. It cannot detect a
    genuine paraphrase that shares no words with the original (false
    negative). More dangerously, hash collisions inflate the similarity of
    genuinely unrelated long texts (false positive): at typical LinkedIn-post
    length, two documents with zero shared vocabulary still land in the
    0.15-0.5 cosine range purely from bucket collisions, and the inflation
    grows with the number of distinct tokens in each document. Duplicate
    thresholds must never be calibrated against this embedder — only against
    a real embedding model — or that collision noise gets read as evidence of
    duplication. It exists to exercise the pipeline end to end without
    credentials, not to stand in for a real embedding model's semantics.
    """

    dimensions = 1024
    prompt_version = "embedding/mock-embed-v1"

    def __init__(self, *, model: str = "mock-embed-v1", latency_ms: int = 1) -> None:
        self._model = model
        self._latency_ms = latency_ms

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        vectors = [self._vector(text) for text in texts]
        input_tokens = sum(len(tokenize(text)) for text in texts)
        return EmbeddingResult(
            vectors=vectors,
            usage=LLMResult(
                text="",
                model=self._model,
                prompt_version=self.prompt_version,
                input_tokens=input_tokens,
                output_tokens=0,
                latency_ms=self._latency_ms,
                cost_usd=Decimal("0"),
            ),
        )

    def _vector(self, text: str) -> list[float]:
        buckets = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            buckets[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in buckets))
        if norm == 0.0:
            return buckets
        return [value / norm for value in buckets]
