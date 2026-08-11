# M4 Content Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the system a memory of what it has already said, so a near-duplicate draft cannot reach approval without an explicit, recorded human override.

**Architecture:** A new `src/memory/` package holds post history, a pure similarity engine, and a mock analytics provider. `src/llm/embeddings.py` adds an `EmbeddingProvider` protocol beside the existing `LLMClient`, with a deterministic `MockEmbedder`. M3 is touched at exactly one seam — `decide_approval` — which runs the duplicate check and records the resulting post.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, pgvector, FastAPI, Pydantic v2, pytest/pytest-asyncio, Next.js 15 (App Router, client components, plain `fetch`).

**Design:** `docs/superpowers/specs/2026-08-12-m4-content-memory-design.md`

---

## Naming warning, read before Task 7

**Do not name the service exception `MemoryError`.** That is a Python builtin, and shadowing it will produce confusing failures far from the definition. This plan uses `ContentMemoryError`, `ContentMemoryNotFound`, `ContentMemoryConflict`, and `ContentMemoryValidationError` throughout.

## File structure

| File | Responsibility |
| --- | --- |
| `src/research/dedup.py` | *(modify)* export a public `tokenize()` both M2 and M4 share |
| `src/llm/embeddings.py` | *(create)* `EmbeddingProvider` protocol, `EmbeddingResult`, `MockEmbedder` |
| `src/llm/persistence.py` | *(modify)* accept `EmbeddingResult` so embedding spend is cost-logged |
| `src/memory/similarity.py` | *(create)* pure scoring: cosine, pair scoring, verdict banding. No I/O |
| `src/memory/models.py` | *(create)* `PostRecord`, `PostMetricSnapshot`, `DuplicateConfig`, `DuplicateCheck` |
| `src/memory/schemas.py` | *(create)* Pydantic request/response types |
| `src/memory/analytics.py` | *(create)* `AnalyticsProvider` protocol, `MockAnalyticsProvider` |
| `src/memory/service.py` | *(create)* transaction-neutral domain rules |
| `src/content/service.py` | *(modify)* one seam in `decide_approval` |
| `src/content/schemas.py` | *(modify)* override fields on `ApprovalDecisionInput` |
| `services/api/routes/memory.py` | *(create)* HTTP surface |
| `services/api/main.py` | *(modify)* register router, error handler, embedder |
| `alembic/versions/0005_content_memory.py` | *(create)* schema + seeded config |
| `alembic/env.py` | *(modify)* register M4 models |
| `apps/web/app/content/DuplicatePanel.tsx` | *(create)* verdict panel; `page.tsx` is already 737 lines |
| `apps/web/app/analytics/page.tsx` | *(modify)* replace the stub with post history |

---

### Task 1: Shared tokenizer and the pure similarity engine

**Files:**
- Modify: `src/research/dedup.py`
- Create: `src/memory/__init__.py`, `src/memory/similarity.py`
- Test: `tests/unit/test_memory_similarity.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory_similarity.py`:

```python
import pytest

from src.memory.similarity import cosine_similarity, score_pair, verdict_for


def test_cosine_similarity_of_identical_vectors_is_one():
    assert cosine_similarity([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_clamps_negatives_to_zero():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory_similarity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory'`

- [ ] **Step 3: Add a public tokenizer to `src/research/dedup.py`**

Both M2 shingling and the M4 embedder need the same tokenization. Replace the body of `_shingles` so it reuses a new public helper rather than duplicating the regex. Add after `content_hash`:

```python
def tokenize(content: str) -> list[str]:
    """Return normalized, case-folded word tokens."""
    return [token.casefold() for token in _TOKEN.findall(normalize_content(content))]
```

Then change the first line of `_shingles` from:

```python
    tokens = [token.casefold() for token in _TOKEN.findall(normalize_content(content))]
```

to:

```python
    tokens = tokenize(content)
```

- [ ] **Step 4: Create the package and the similarity engine**

Create `src/memory/__init__.py` as an empty file.

Create `src/memory/similarity.py`:

```python
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

    Identical text needs no special case: it already scores 1.0 lexically.
    A semantic score is computed only when both sides supply an embedding; a
    post record with no stored vector is scored lexically only, by design.
    """
    lexical = token_similarity(candidate_text, neighbour_text)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_memory_similarity.py tests/unit/ -v`
Expected: PASS, and the existing M2 dedup tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/memory/__init__.py src/memory/similarity.py src/research/dedup.py tests/unit/test_memory_similarity.py
git commit -m "feat(memory): add pure duplicate similarity engine"
```

---

### Task 2: EmbeddingProvider protocol and MockEmbedder

**Files:**
- Create: `src/llm/embeddings.py`
- Modify: `src/llm/persistence.py`
- Test: `tests/unit/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_embeddings.py`:

```python
import math
from decimal import Decimal

import pytest

from src.llm.embeddings import MockEmbedder
from src.memory.similarity import cosine_similarity


@pytest.mark.asyncio
async def test_embed_returns_one_vector_per_text():
    result = await MockEmbedder().embed(["first text", "second text"])
    assert len(result.vectors) == 2
    assert all(len(vector) == MockEmbedder.dimensions for vector in result.vectors)


@pytest.mark.asyncio
async def test_vectors_are_l2_normalized():
    result = await MockEmbedder().embed(["normalization matters here"])
    norm = math.sqrt(sum(value * value for value in result.vectors[0]))
    assert norm == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embedding_is_deterministic():
    first = await MockEmbedder().embed(["exactly the same input"])
    second = await MockEmbedder().embed(["exactly the same input"])
    assert first.vectors == second.vectors


@pytest.mark.asyncio
async def test_shared_vocabulary_scores_higher_than_unrelated_text():
    result = await MockEmbedder().embed(
        [
            "evidence grounded content pipelines",
            "evidence grounded content workflows",
            "sourdough bread starter hydration",
        ]
    )
    related = cosine_similarity(result.vectors[0], result.vectors[1])
    unrelated = cosine_similarity(result.vectors[0], result.vectors[2])
    assert related > unrelated


@pytest.mark.asyncio
async def test_empty_text_produces_a_zero_vector():
    result = await MockEmbedder().embed([""])
    assert set(result.vectors[0]) == {0.0}


@pytest.mark.asyncio
async def test_usage_metadata_is_cost_loggable():
    result = await MockEmbedder().embed(["four small tokens here"])
    assert result.usage.model == "mock-embed-v1"
    assert result.usage.prompt_version == "embedding/mock-embed-v1"
    assert result.usage.input_tokens == 4
    assert result.usage.output_tokens == 0
    assert result.usage.cost_usd == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.llm.embeddings'`

- [ ] **Step 3: Write the implementation**

Create `src/llm/embeddings.py`:

```python
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
    """

    @property
    def model(self) -> str: ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...


class MockEmbedder:
    """Deterministic, credential-free `EmbeddingProvider`.

    Hashes tokens into a fixed-width bag-of-words vector, so it measures
    *vocabulary overlap* only. It cannot detect a genuine paraphrase that
    shares no words with the original. It exercises the pipeline end to end
    without credentials; it is not a substitute for a real embedding model,
    and duplicate detection is only as semantic as the provider behind it.
    """

    dimensions = 256
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
```

- [ ] **Step 4: Teach `log_llm_call` about embedding results**

In `src/llm/persistence.py`, change the import line:

```python
from src.llm.protocol import LLMResult, StructuredResult
```

to:

```python
from src.llm.embeddings import EmbeddingResult
from src.llm.protocol import LLMResult, StructuredResult
```

Change the signature:

```python
async def log_llm_call(
    session: AsyncSession, run: Run, result: LLMResult | StructuredResult | EmbeddingResult
) -> LLMCall:
```

Change the usage-extraction line:

```python
    usage = result.usage if isinstance(result, StructuredResult) else result
```

to:

```python
    usage = result.usage if isinstance(result, StructuredResult | EmbeddingResult) else result
```

Add this sentence to the existing docstring, after the paragraph about accepting both call kinds:

```
    Embedding calls (EmbeddingResult) log through the same path so embedding
    spend is tracked in one place rather than a parallel table.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_embeddings.py -v && uv run pyright`
Expected: PASS, and pyright reports 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/llm/embeddings.py src/llm/persistence.py tests/unit/test_embeddings.py
git commit -m "feat(llm): add EmbeddingProvider protocol and deterministic MockEmbedder"
```

---

### Task 3: Memory ORM models

**Files:**
- Create: `src/memory/models.py`
- Modify: `alembic/env.py`

- [ ] **Step 1: Write the models**

Create `src/memory/models.py`:

```python
"""ORM models for post history, duplicate policy, and performance snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.models import utcnow

POST_PLATFORMS = ("linkedin", "x")
POST_ORIGINS = ("workflow", "manual")
POST_STATUSES = ("approved_unpublished", "published_externally")
DUPLICATE_VERDICTS = ("clear", "warn", "block")


class MemoryTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        server_default=func.now(),
    )


class PostRecord(MemoryTimestampMixin, Base):
    """One post, per platform. Never implies anything was published by us."""

    __tablename__ = "post_records"
    __table_args__ = (
        # NULL workflow_id rows (manual backfill) are distinct in Postgres, so
        # this constrains workflow-origin rows only and makes re-approval
        # idempotent without touching manual history.
        UniqueConstraint("workflow_id", "platform", name="uq_post_records_workflow_platform"),
        CheckConstraint("platform IN ('linkedin', 'x')", name="ck_post_records_platform"),
        CheckConstraint("origin IN ('workflow', 'manual')", name="ck_post_records_origin"),
        CheckConstraint(
            "status IN ('approved_unpublished', 'published_externally')",
            name="ck_post_records_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_workflows.id", ondelete="SET NULL"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_url: Mapped[str | None] = mapped_column(String(2048))
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
    embedding_model: Mapped[str | None] = mapped_column(String(160), index=True)

    snapshots: Mapped[list[PostMetricSnapshot]] = relationship(
        back_populates="post_record",
        cascade="all, delete-orphan",
        order_by="PostMetricSnapshot.captured_at",
    )


class PostMetricSnapshot(MemoryTimestampMixin, Base):
    """Append-only performance sample. Never updated in place.

    Unreported metrics stay NULL rather than 0: a zero that means "unknown"
    would silently corrupt any later analysis.
    """

    __tablename__ = "post_metric_snapshots"
    __table_args__ = (
        CheckConstraint("source IN ('mock', 'manual')", name="ck_post_metric_snapshots_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    impressions: Mapped[int | None] = mapped_column(Integer)
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    reposts: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    follows: Mapped[int | None] = mapped_column(Integer)

    post_record: Mapped[PostRecord] = relationship(back_populates="snapshots")


class DuplicateConfig(MemoryTimestampMixin, Base):
    """Versioned duplicate policy. The engine holds no default thresholds."""

    __tablename__ = "duplicate_configs"
    __table_args__ = (
        UniqueConstraint("version", name="uq_duplicate_configs_version"),
        CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 1 AND "
            "block_threshold >= 0 AND block_threshold <= 1 AND "
            "warn_threshold <= block_threshold",
            name="ck_duplicate_configs_thresholds",
        ),
        CheckConstraint(
            "lookback_days IS NULL OR lookback_days > 0",
            name="ck_duplicate_configs_lookback",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    warn_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    block_threshold: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    cross_platform_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lookback_days: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class DuplicateCheck(MemoryTimestampMixin, Base):
    """Persisted, inspectable verdict for one workflow/platform check."""

    __tablename__ = "duplicate_checks"
    __table_args__ = (
        CheckConstraint("platform IN ('linkedin', 'x')", name="ck_duplicate_checks_platform"),
        CheckConstraint(
            "verdict IN ('clear', 'warn', 'block')", name="ck_duplicate_checks_verdict"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    top_similarity: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    nearest_post_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("post_records.id", ondelete="SET NULL"), index=True
    )
    components: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )
```

- [ ] **Step 2: Register the models with Alembic**

In `alembic/env.py`, add this import after the `src.db` import line, keeping alphabetical order with the existing registration imports:

```python
from src.memory import models as memory_models  # noqa: F401  register M4 models
```

- [ ] **Step 3: Verify the models import cleanly**

Run: `uv run python -c "from src.memory import models; print(sorted(models.Base.metadata.tables))"`
Expected: the printed list includes `duplicate_checks`, `duplicate_configs`, `post_metric_snapshots`, and `post_records`.

- [ ] **Step 4: Commit**

```bash
git add src/memory/models.py alembic/env.py
git commit -m "feat(memory): add post history, duplicate policy, and snapshot models"
```

---

### Task 4: Migration 0005 with seeded policy

**Files:**
- Create: `alembic/versions/0005_content_memory.py`
- Test: `tests/integration/test_migration.py` (existing drift test covers this)

- [ ] **Step 1: Write the migration**

Create `alembic/versions/0005_content_memory.py`:

```python
"""Add M4 post history, duplicate policy, and performance snapshots.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "post_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="SET NULL"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("external_url", sa.String(2048)),
        sa.Column("embedding", VECTOR()),
        sa.Column("embedding_model", sa.String(160)),
        *_timestamps(),
        sa.UniqueConstraint("workflow_id", "platform", name="uq_post_records_workflow_platform"),
        sa.CheckConstraint("platform IN ('linkedin', 'x')", name="ck_post_records_platform"),
        sa.CheckConstraint("origin IN ('workflow', 'manual')", name="ck_post_records_origin"),
        sa.CheckConstraint(
            "status IN ('approved_unpublished', 'published_externally')",
            name="ck_post_records_status",
        ),
    )
    op.create_index("ix_post_records_platform", "post_records", ["platform"])
    op.create_index("ix_post_records_origin", "post_records", ["origin"])
    op.create_index("ix_post_records_workflow_id", "post_records", ["workflow_id"])
    op.create_index("ix_post_records_content_hash", "post_records", ["content_hash"])
    op.create_index("ix_post_records_embedding_model", "post_records", ["embedding_model"])

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "post_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("post_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("impressions", sa.Integer()),
        sa.Column("reactions", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("reposts", sa.Integer()),
        sa.Column("clicks", sa.Integer()),
        sa.Column("follows", sa.Integer()),
        *_timestamps(),
        sa.CheckConstraint("source IN ('mock', 'manual')", name="ck_post_metric_snapshots_source"),
    )
    op.create_index(
        "ix_post_metric_snapshots_post_record_id", "post_metric_snapshots", ["post_record_id"]
    )

    op.create_table(
        "duplicate_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("warn_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column("block_threshold", sa.Numeric(4, 3), nullable=False),
        sa.Column("cross_platform_check", sa.Boolean(), nullable=False),
        sa.Column("lookback_days", sa.Integer()),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("version", name="uq_duplicate_configs_version"),
        sa.CheckConstraint(
            "warn_threshold >= 0 AND warn_threshold <= 1 AND "
            "block_threshold >= 0 AND block_threshold <= 1 AND "
            "warn_threshold <= block_threshold",
            name="ck_duplicate_configs_thresholds",
        ),
        sa.CheckConstraint(
            "lookback_days IS NULL OR lookback_days > 0",
            name="ck_duplicate_configs_lookback",
        ),
    )
    op.create_index("ix_duplicate_configs_active", "duplicate_configs", ["active"])

    op.create_table(
        "duplicate_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("config_version", sa.String(80), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("top_similarity", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "nearest_post_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("post_records.id", ondelete="SET NULL"),
        ),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("overridden", sa.Boolean(), nullable=False),
        sa.Column("override_reason", sa.Text()),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL")
        ),
        *_timestamps(),
        sa.CheckConstraint("platform IN ('linkedin', 'x')", name="ck_duplicate_checks_platform"),
        sa.CheckConstraint(
            "verdict IN ('clear', 'warn', 'block')", name="ck_duplicate_checks_verdict"
        ),
    )
    op.create_index("ix_duplicate_checks_workflow_id", "duplicate_checks", ["workflow_id"])
    op.create_index(
        "ix_duplicate_checks_nearest_post_record_id",
        "duplicate_checks",
        ["nearest_post_record_id"],
    )
    op.create_index("ix_duplicate_checks_run_id", "duplicate_checks", ["run_id"])

    # Seed the starting policy as data the user can edit. This is not the same
    # as hard-coding thresholds in the scorer: the engine still reads whatever
    # row is active, and has no fallback of its own.
    op.execute(
        """
        INSERT INTO duplicate_configs (
            id, version, warn_threshold, block_threshold,
            cross_platform_check, lookback_days, active, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), 'v1', 0.700, 0.850, false, NULL, true, now(), now()
        )
        """
    )


def downgrade() -> None:
    op.drop_table("duplicate_checks")
    op.drop_table("duplicate_configs")
    op.drop_table("post_metric_snapshots")
    op.drop_table("post_records")
```

- [ ] **Step 2: Apply the migration**

Run: `uv run alembic upgrade head`
Expected: completes without error, ending at revision `0005`.

- [ ] **Step 3: Verify no model/migration drift**

Run: `uv run pytest tests/integration/test_migration.py -v`
Expected: PASS. If drift is reported, the migration and `src/memory/models.py` disagree — fix the migration to match the models, not the reverse.

- [ ] **Step 4: Verify a fresh database migrates from empty**

Run:

```bash
uv run alembic downgrade base && uv run alembic upgrade head
```

Expected: both complete without error.

- [ ] **Step 5: Verify the seeded config exists and is active**

Run:

```bash
uv run python -c "
import asyncio
from sqlalchemy import select
from src.db.session import get_sessionmaker
from src.memory.models import DuplicateConfig

async def main():
    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(DuplicateConfig))).scalars().all()
        print([(r.version, str(r.warn_threshold), str(r.block_threshold), r.active) for r in rows])

asyncio.run(main())
"
```

Expected: `[('v1', '0.700', '0.850', True)]`

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/0005_content_memory.py
git commit -m "feat(memory): add migration 0005 with seeded duplicate policy"
```

---

### Task 5: Memory schemas

**Files:**
- Create: `src/memory/schemas.py`
- Test: `tests/unit/test_memory_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from src.memory.schemas import DuplicateConfigCreate, PostRecordCreate, PostRecordUpdate


def test_manual_post_requires_content():
    with pytest.raises(ValidationError):
        PostRecordCreate(platform="linkedin", content="")


def test_manual_post_accepts_minimum_fields():
    payload = PostRecordCreate(platform="x", content="A short post about evidence.")
    assert payload.status == "published_externally"
    assert payload.external_url is None


def test_embedding_and_model_must_be_provided_together():
    with pytest.raises(ValidationError, match="together"):
        PostRecordCreate(
            platform="linkedin", content="Body text", embedding=[0.1, 0.2], embedding_model=None
        )
    with pytest.raises(ValidationError, match="together"):
        PostRecordCreate(
            platform="linkedin", content="Body text", embedding=None, embedding_model="some-model"
        )


def test_supplied_embedding_pair_is_accepted():
    payload = PostRecordCreate(
        platform="linkedin",
        content="Body text",
        embedding=[0.1, 0.2],
        embedding_model="mock-embed-v1",
    )
    assert payload.embedding_model == "mock-embed-v1"


def test_update_rejects_an_empty_payload():
    with pytest.raises(ValidationError, match="at least one field"):
        PostRecordUpdate()


def test_duplicate_config_rejects_warn_above_block():
    with pytest.raises(ValidationError, match="cannot exceed"):
        DuplicateConfigCreate(version="v2", warn_threshold="0.900", block_threshold="0.800")


def test_duplicate_config_accepts_valid_thresholds():
    config = DuplicateConfigCreate(version="v2", warn_threshold="0.650", block_threshold="0.900")
    assert config.cross_platform_check is False
    assert config.lookback_days is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory.schemas'`

- [ ] **Step 3: Write the schemas**

Create `src/memory/schemas.py`:

```python
"""Validated API schemas for content memory."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PostPlatform = Literal["linkedin", "x"]
PostOrigin = Literal["workflow", "manual"]
PostStatus = Literal["approved_unpublished", "published_externally"]
Verdict = Literal["clear", "warn", "block"]


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PostRecordCreate(BaseModel):
    """Manual backfill of a post already published elsewhere."""

    platform: PostPlatform
    content: str = Field(min_length=1, max_length=100_000)
    status: PostStatus = "published_externally"
    posted_at: datetime | None = None
    external_url: str | None = Field(default=None, max_length=2048)
    embedding: list[float] | None = Field(default=None, max_length=16_000)
    embedding_model: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def embedding_has_model(self) -> "PostRecordCreate":
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("embedding and embedding_model must be provided together")
        return self


class PostRecordUpdate(BaseModel):
    status: PostStatus | None = None
    posted_at: datetime | None = None
    external_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PostRecordUpdate":
        if self.status is None and self.posted_at is None and self.external_url is None:
            raise ValueError("provide at least one field to update")
        return self


class PostMetricSnapshotRead(ORMResponse):
    id: uuid.UUID
    captured_at: datetime
    source: str
    is_mock: bool
    impressions: int | None
    reactions: int | None
    comments: int | None
    reposts: int | None
    clicks: int | None
    follows: int | None


class PostRecordRead(ORMResponse):
    id: uuid.UUID
    platform: str
    origin: str
    status: str
    workflow_id: uuid.UUID | None
    content: str
    content_hash: str
    posted_at: datetime | None
    external_url: str | None
    embedding_model: str | None
    snapshots: list[PostMetricSnapshotRead]
    created_at: datetime
    updated_at: datetime


class DuplicateConfigCreate(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    warn_threshold: Decimal = Field(ge=0, le=1)
    block_threshold: Decimal = Field(ge=0, le=1)
    cross_platform_check: bool = False
    lookback_days: int | None = Field(default=None, gt=0)
    active: bool = True

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "DuplicateConfigCreate":
        if self.warn_threshold > self.block_threshold:
            raise ValueError("warn threshold cannot exceed block threshold")
        return self


class DuplicateConfigRead(ORMResponse):
    id: uuid.UUID
    version: str
    warn_threshold: Decimal
    block_threshold: Decimal
    cross_platform_check: bool
    lookback_days: int | None
    active: bool
    created_at: datetime


class DuplicateNeighbour(BaseModel):
    post_record_id: uuid.UUID
    platform: str
    lexical: float
    semantic: float | None
    score: float


class DuplicateCheckRead(ORMResponse):
    id: uuid.UUID
    workflow_id: uuid.UUID
    platform: str
    config_version: str
    verdict: str
    top_similarity: Decimal
    nearest_post_record_id: uuid.UUID | None
    components: list[dict[str, object]]
    overridden: bool
    override_reason: str | None
    created_at: datetime


class DuplicatePreviewRequest(BaseModel):
    """Ad-hoc check of arbitrary text, before a workflow exists."""

    platform: PostPlatform
    content: str = Field(min_length=1, max_length=100_000)


class DuplicatePreviewResponse(BaseModel):
    verdict: Verdict
    config_version: str
    top_similarity: float
    neighbours: list[DuplicateNeighbour]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_memory_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/schemas.py tests/unit/test_memory_schemas.py
git commit -m "feat(memory): add validated content memory schemas"
```

---

### Task 6: Analytics provider

**Files:**
- Create: `src/memory/analytics.py`
- Test: `tests/unit/test_memory_analytics.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_memory_analytics.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.memory.analytics import MockAnalyticsProvider


@pytest.mark.asyncio
async def test_metrics_are_deterministic_for_the_same_post_and_age():
    post_id = uuid.uuid4()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    now = datetime(2026, 8, 6, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    first = await provider.fetch(post_id=post_id, platform="linkedin", posted_at=posted_at, now=now)
    second = await provider.fetch(
        post_id=post_id, platform="linkedin", posted_at=posted_at, now=now
    )
    assert first == second


@pytest.mark.asyncio
async def test_different_posts_get_different_metrics():
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    now = datetime(2026, 8, 6, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    first = await provider.fetch(
        post_id=uuid.uuid4(), platform="linkedin", posted_at=posted_at, now=now
    )
    second = await provider.fetch(
        post_id=uuid.uuid4(), platform="linkedin", posted_at=posted_at, now=now
    )
    assert first.impressions != second.impressions


@pytest.mark.asyncio
async def test_impressions_grow_with_age():
    post_id = uuid.uuid4()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    provider = MockAnalyticsProvider()
    young = await provider.fetch(
        post_id=post_id, platform="x", posted_at=posted_at, now=posted_at + timedelta(days=1)
    )
    old = await provider.fetch(
        post_id=post_id, platform="x", posted_at=posted_at, now=posted_at + timedelta(days=30)
    )
    assert old.impressions > young.impressions


@pytest.mark.asyncio
async def test_engagement_never_exceeds_impressions():
    provider = MockAnalyticsProvider()
    posted_at = datetime(2026, 8, 1, tzinfo=UTC)
    for _ in range(25):
        metrics = await provider.fetch(
            post_id=uuid.uuid4(),
            platform="linkedin",
            posted_at=posted_at,
            now=posted_at + timedelta(days=7),
        )
        # The mock always reports every metric; assert that before arithmetic
        # so this stays type-safe under pyright.
        assert metrics.impressions is not None
        assert metrics.reactions is not None
        assert metrics.comments is not None
        assert metrics.reposts is not None
        assert metrics.clicks is not None
        engagement = metrics.reactions + metrics.comments + metrics.reposts
        assert engagement <= metrics.impressions
        assert metrics.clicks <= metrics.impressions


@pytest.mark.asyncio
async def test_a_post_with_no_posted_at_is_treated_as_brand_new():
    provider = MockAnalyticsProvider()
    metrics = await provider.fetch(
        post_id=uuid.uuid4(),
        platform="x",
        posted_at=None,
        now=datetime(2026, 8, 6, tzinfo=UTC),
    )
    assert metrics.impressions >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_memory_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory.analytics'`

- [ ] **Step 3: Write the implementation**

Create `src/memory/analytics.py`:

```python
"""Contract for post performance providers, plus a deterministic mock.

M4 stores performance data; it does not interpret it. Ranking, recommendation,
and any learning from engagement belong to M9.
"""

import hashlib
import math
import uuid
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class PostMetrics(BaseModel):
    """One performance sample.

    A real provider that does not report a metric must leave it None. A zero
    standing in for "unknown" would silently corrupt later analysis.
    """

    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    clicks: int | None = None
    follows: int | None = None


class AnalyticsProvider(Protocol):
    """Contract every analytics provider must satisfy.

    Implementations never persist; the caller writes the snapshot. Real
    platform providers stay behind the M7 capability gate.
    """

    @property
    def name(self) -> str: ...

    @property
    def is_mock(self) -> bool: ...

    async def fetch(
        self,
        *,
        post_id: uuid.UUID,
        platform: str,
        posted_at: datetime | None,
        now: datetime,
    ) -> PostMetrics: ...


class MockAnalyticsProvider:
    """Deterministic, credential-free `AnalyticsProvider`.

    Derives a plausible growth curve from the post id and its age, so repeated
    calls for the same post and age return identical numbers. These figures are
    invented. They exist so the schema and UI can be exercised, and every
    snapshot they produce is tagged `is_mock`.
    """

    name = "mock"
    is_mock = True

    async def fetch(
        self,
        *,
        post_id: uuid.UUID,
        platform: str,
        posted_at: datetime | None,
        now: datetime,
    ) -> PostMetrics:
        seed = int.from_bytes(hashlib.sha256(post_id.bytes).digest()[:8], "big")
        age_days = 0.0 if posted_at is None else max(0.0, (now - posted_at).total_seconds() / 86400)
        # Reach saturates rather than growing without bound.
        base = 200 + seed % 800
        impressions = int(base * math.log1p(age_days) + base / 4)
        engagement_rate = 0.02 + (seed % 30) / 1000
        engaged = int(impressions * engagement_rate)
        reactions = int(engaged * 0.7)
        comments = int(engaged * 0.2)
        reposts = engaged - reactions - comments
        return PostMetrics(
            impressions=impressions,
            reactions=reactions,
            comments=comments,
            reposts=reposts,
            clicks=int(impressions * 0.01),
            follows=int(engaged * 0.05),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_memory_analytics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/analytics.py tests/unit/test_memory_analytics.py
git commit -m "feat(memory): add analytics provider protocol and deterministic mock"
```

---

### Task 7: Memory service — post records, config, and duplicate evaluation

**Files:**
- Create: `src/memory/service.py`
- Test: `tests/integration/test_memory_service.py`

Remember the naming warning at the top of this plan: the error base class is `ContentMemoryError`, never `MemoryError`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_memory_service.py`:

```python
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.embeddings import MockEmbedder
from src.memory import service
from src.memory.schemas import DuplicateConfigCreate, PostRecordCreate
from src.memory.service import ContentMemoryConflict, ContentMemoryNotFound


@pytest.mark.asyncio
async def test_seeded_config_is_active(db_session: AsyncSession):
    config = await service.get_active_duplicate_config(db_session)
    assert config.version == "v1"
    assert config.warn_threshold == Decimal("0.700")
    assert config.block_threshold == Decimal("0.850")


@pytest.mark.asyncio
async def test_create_manual_post_embeds_and_hashes(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content="Evidence beats opinion every time."),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    assert record.origin == "manual"
    assert record.content_hash
    assert record.embedding_model == "mock-embed-v1"
    assert record.embedding is not None


@pytest.mark.asyncio
async def test_supplied_embedding_is_kept_instead_of_recomputed(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(
            platform="x",
            content="Caller supplied a vector.",
            embedding=[0.5, 0.5],
            embedding_model="caller-model",
        ),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    assert record.embedding_model == "caller-model"
    assert record.embedding is not None
    assert len(record.embedding) == 2


@pytest.mark.asyncio
async def test_identical_text_is_blocked(db_session: AsyncSession):
    text = "A staged content pipeline keeps every intermediate artifact inspectable."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "block"
    assert evaluation.top_similarity == pytest.approx(1.0)
    assert evaluation.nearest_post_record_id is not None


@pytest.mark.asyncio
async def test_unrelated_text_is_clear(db_session: AsyncSession):
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content="Kubernetes operators reconcile state."),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text="Sourdough hydration changes the crumb structure entirely.",
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"


@pytest.mark.asyncio
async def test_other_platform_is_ignored_by_default(db_session: AsyncSession):
    text = "One idea, posted to exactly one platform."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="x", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"


@pytest.mark.asyncio
async def test_cross_platform_check_sees_the_other_platform(db_session: AsyncSession):
    text = "One idea, checked across both platforms this time."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="x", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="cross-v1",
            warn_threshold="0.700",
            block_threshold="0.850",
            cross_platform_check=True,
        ),
    )
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "block"


@pytest.mark.asyncio
async def test_activating_a_config_deactivates_the_previous_one(db_session: AsyncSession):
    await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="v2", warn_threshold="0.600", block_threshold="0.800", active=True
        ),
    )
    active = await service.get_active_duplicate_config(db_session)
    assert active.version == "v2"


@pytest.mark.asyncio
async def test_duplicate_config_version_must_be_unique(db_session: AsyncSession):
    with pytest.raises(ContentMemoryConflict, match="already exists"):
        await service.create_duplicate_config(
            db_session,
            DuplicateConfigCreate(version="v1", warn_threshold="0.600", block_threshold="0.800"),
        )


@pytest.mark.asyncio
async def test_missing_post_record_raises_not_found(db_session: AsyncSession):
    with pytest.raises(ContentMemoryNotFound):
        await service.require_post_record(db_session, uuid.uuid4())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_memory_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory.service'`

- [ ] **Step 3: Write the service**

Create `src/memory/service.py`:

```python
"""Domain rules for content memory.

Transaction-neutral, matching M1 through M3: this module flushes so callers can
read generated keys, but never commits. Routes own the transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Run
from src.llm.embeddings import EmbeddingProvider
from src.llm.persistence import log_llm_call
from src.memory.analytics import AnalyticsProvider
from src.memory.models import DuplicateCheck, DuplicateConfig, PostMetricSnapshot, PostRecord
from src.memory.schemas import (
    DuplicateConfigCreate,
    DuplicateNeighbour,
    PostRecordCreate,
    PostRecordUpdate,
)
from src.memory.similarity import DuplicateVerdict, score_pair, verdict_for
from src.research.dedup import content_hash, normalize_content


class ContentMemoryError(Exception):
    # Deliberately not named MemoryError: that is a Python builtin.
    status_code = 400


class ContentMemoryNotFound(ContentMemoryError):
    status_code = 404


class ContentMemoryConflict(ContentMemoryError):
    status_code = 409


class ContentMemoryValidationError(ContentMemoryError):
    status_code = 422


class DuplicateEvaluation:
    """Result of one duplicate evaluation, before it is persisted."""

    def __init__(
        self,
        *,
        verdict: DuplicateVerdict,
        top_similarity: float,
        nearest_post_record_id: uuid.UUID | None,
        neighbours: list[DuplicateNeighbour],
        config_version: str,
    ) -> None:
        self.verdict = verdict
        self.top_similarity = top_similarity
        self.nearest_post_record_id = nearest_post_record_id
        self.neighbours = neighbours
        self.config_version = config_version


async def _ensure_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        run = Run(id=run_id)
        session.add(run)
        await session.flush()
    return run


async def _embed(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    text: str,
    run_id: uuid.UUID | None,
) -> tuple[list[float], str]:
    result = await embedder.embed([text])
    if run_id is not None:
        run = await _ensure_run(session, run_id)
        await log_llm_call(session, run, result)
    return result.vectors[0], result.usage.model


async def get_active_duplicate_config(session: AsyncSession) -> DuplicateConfig:
    config = (
        await session.execute(select(DuplicateConfig).where(DuplicateConfig.active.is_(True)))
    ).scalar_one_or_none()
    if config is None:
        raise ContentMemoryConflict(
            "no active duplicate configuration exists; create one before approving content"
        )
    return config


async def list_duplicate_configs(session: AsyncSession) -> list[DuplicateConfig]:
    result = await session.execute(
        select(DuplicateConfig).order_by(DuplicateConfig.created_at.desc())
    )
    return list(result.scalars().all())


async def create_duplicate_config(
    session: AsyncSession, data: DuplicateConfigCreate
) -> DuplicateConfig:
    existing = (
        await session.execute(
            select(DuplicateConfig).where(DuplicateConfig.version == data.version)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ContentMemoryConflict(f"duplicate configuration {data.version!r} already exists")
    if data.active:
        for current in (await session.execute(select(DuplicateConfig))).scalars().all():
            current.active = False
    config = DuplicateConfig(
        version=data.version,
        warn_threshold=data.warn_threshold,
        block_threshold=data.block_threshold,
        cross_platform_check=data.cross_platform_check,
        lookback_days=data.lookback_days,
        active=data.active,
    )
    session.add(config)
    await session.flush()
    return config


async def list_post_records(session: AsyncSession) -> list[PostRecord]:
    result = await session.execute(
        select(PostRecord)
        .options(selectinload(PostRecord.snapshots))
        .order_by(PostRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def require_post_record(session: AsyncSession, post_id: uuid.UUID) -> PostRecord:
    result = await session.execute(
        select(PostRecord)
        .options(selectinload(PostRecord.snapshots))
        .where(PostRecord.id == post_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ContentMemoryNotFound("post record not found")
    return record


async def create_post_record(
    session: AsyncSession,
    data: PostRecordCreate,
    *,
    embedder: EmbeddingProvider,
    run_id: uuid.UUID | None,
) -> PostRecord:
    """Record a post the user already published elsewhere."""
    if data.embedding is not None and data.embedding_model is not None:
        embedding, embedding_model = data.embedding, data.embedding_model
    else:
        embedding, embedding_model = await _embed(session, embedder, data.content, run_id)
    record = PostRecord(
        platform=data.platform,
        origin="manual",
        status=data.status,
        workflow_id=None,
        content=data.content,
        normalized_content=normalize_content(data.content),
        content_hash=content_hash(data.content),
        posted_at=data.posted_at,
        external_url=data.external_url,
        embedding=embedding,
        embedding_model=embedding_model,
    )
    session.add(record)
    await session.flush()
    return record


async def record_workflow_post(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    platform: str,
    content: str,
    embedder: EmbeddingProvider,
    run_id: uuid.UUID | None,
) -> PostRecord:
    """Record an approved workflow draft as history.

    Idempotent: re-approving after a rejection updates the existing row rather
    than adding a second one, which the unique (workflow_id, platform)
    constraint would reject anyway.
    """
    existing = (
        await session.execute(
            select(PostRecord).where(
                PostRecord.workflow_id == workflow_id, PostRecord.platform == platform
            )
        )
    ).scalar_one_or_none()
    embedding, embedding_model = await _embed(session, embedder, content, run_id)
    if existing is not None:
        existing.content = content
        existing.normalized_content = normalize_content(content)
        existing.content_hash = content_hash(content)
        existing.embedding = embedding
        existing.embedding_model = embedding_model
        await session.flush()
        return existing
    record = PostRecord(
        platform=platform,
        origin="workflow",
        # Approval is a local decision. Nothing was published.
        status="approved_unpublished",
        workflow_id=workflow_id,
        content=content,
        normalized_content=normalize_content(content),
        content_hash=content_hash(content),
        embedding=embedding,
        embedding_model=embedding_model,
    )
    session.add(record)
    await session.flush()
    return record


async def update_post_record(
    session: AsyncSession, post_id: uuid.UUID, data: PostRecordUpdate
) -> PostRecord:
    record = await require_post_record(session, post_id)
    if data.status is not None:
        record.status = data.status
    if data.posted_at is not None:
        record.posted_at = data.posted_at
    if data.external_url is not None:
        record.external_url = data.external_url
    await session.flush()
    return record


async def delete_post_record(session: AsyncSession, post_id: uuid.UUID) -> None:
    record = await require_post_record(session, post_id)
    if record.origin == "workflow":
        raise ContentMemoryConflict(
            "a workflow-origin post record belongs to its workflow history and cannot be deleted"
        )
    await session.delete(record)
    await session.flush()


async def evaluate_duplicate(
    session: AsyncSession,
    *,
    text: str,
    platform: str,
    config: DuplicateConfig,
    embedder: EmbeddingProvider,
    exclude_workflow_id: uuid.UUID | None,
    run_id: uuid.UUID | None = None,
) -> DuplicateEvaluation:
    """Score `text` against post history under `config`.

    Candidates are prefiltered in SQL and scored in Python. Postgres cannot
    index these vectors without a fixed dimension, so a database-side nearest
    neighbour query would scan anyway while making the lexical signal
    impossible to blend.
    """
    embedding, embedding_model = await _embed(session, embedder, text, run_id)

    query = select(PostRecord)
    if not config.cross_platform_check:
        query = query.where(PostRecord.platform == platform)
    if exclude_workflow_id is not None:
        # A workflow must not block itself with its own recorded post.
        query = query.where(
            (PostRecord.workflow_id.is_(None)) | (PostRecord.workflow_id != exclude_workflow_id)
        )
    if config.lookback_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=config.lookback_days)
        query = query.where(PostRecord.created_at >= cutoff)

    candidates = list((await session.execute(query)).scalars().all())

    neighbours: list[DuplicateNeighbour] = []
    for candidate in candidates:
        # Only compare vectors from the same model: different models do not
        # share a space, and cosine_similarity raises on a dimension mismatch.
        # Require an actual vector, not just a matching model name: the column
        # is nullable, and a one-sided embedding would silently drop the
        # semantic signal.
        same_space = (
            candidate.embedding is not None and candidate.embedding_model == embedding_model
        )
        components = score_pair(
            candidate_text=text,
            neighbour_text=candidate.content,
            candidate_embedding=embedding if same_space else None,
            neighbour_embedding=candidate.embedding if same_space else None,
        )
        neighbours.append(
            DuplicateNeighbour(
                post_record_id=candidate.id,
                platform=candidate.platform,
                lexical=components.lexical,
                semantic=components.semantic,
                score=components.score,
            )
        )

    neighbours.sort(key=lambda item: item.score, reverse=True)
    top = neighbours[0] if neighbours else None
    top_score = top.score if top else 0.0
    verdict = verdict_for(
        top_score,
        warn_threshold=float(config.warn_threshold),
        block_threshold=float(config.block_threshold),
    )
    return DuplicateEvaluation(
        verdict=verdict,
        top_similarity=top_score,
        nearest_post_record_id=top.post_record_id if top else None,
        # Keep the ten nearest: enough to explain the verdict without storing
        # the entire corpus in every check row.
        neighbours=neighbours[:10],
        config_version=config.version,
    )


async def persist_duplicate_check(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    platform: str,
    evaluation: DuplicateEvaluation,
    overridden: bool,
    override_reason: str | None,
    run_id: uuid.UUID | None,
) -> DuplicateCheck:
    check = DuplicateCheck(
        workflow_id=workflow_id,
        platform=platform,
        config_version=evaluation.config_version,
        verdict=evaluation.verdict,
        top_similarity=Decimal(f"{evaluation.top_similarity:.3f}"),
        nearest_post_record_id=evaluation.nearest_post_record_id,
        components=[item.model_dump(mode="json") for item in evaluation.neighbours],
        overridden=overridden,
        override_reason=override_reason,
        run_id=run_id,
    )
    session.add(check)
    await session.flush()
    return check


async def capture_metrics(
    session: AsyncSession, *, post_id: uuid.UUID, provider: AnalyticsProvider
) -> PostMetricSnapshot:
    record = await require_post_record(session, post_id)
    metrics = await provider.fetch(
        post_id=record.id,
        platform=record.platform,
        posted_at=record.posted_at,
        now=datetime.now(UTC),
    )
    snapshot = PostMetricSnapshot(
        post_record_id=record.id,
        source=provider.name,
        is_mock=provider.is_mock,
        impressions=metrics.impressions,
        reactions=metrics.reactions,
        comments=metrics.comments,
        reposts=metrics.reposts,
        clicks=metrics.clicks,
        follows=metrics.follows,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_memory_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/service.py tests/integration/test_memory_service.py
git commit -m "feat(memory): add post history and duplicate evaluation service"
```

---

### Task 8: Wire the duplicate gate into M3 approval

**Files:**
- Modify: `src/content/schemas.py`
- Modify: `src/content/service.py` (`decide_approval`, around line 722)
- Test: `tests/integration/test_content_duplicate_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_content_duplicate_gate.py`. It reuses the workflow-building helper already in the M3 integration suite:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.memory.models import DuplicateCheck, PostRecord
from tests.integration.test_content_api import content_client, create_grounded_topic  # noqa: F401


async def approve_workflow(client: AsyncClient, suffix: str) -> tuple[str, str]:
    """Drive a workflow to ready_for_approval and return (workflow_id, linkedin text).

    `create_grounded_topic` returns (topic_id, claim_id) — the workflow endpoint
    resolves the evidence pack from the topic itself, so no pack id is sent.
    """
    topic_id, _claim_id = await create_grounded_topic(client, suffix)
    created = await client.post(
        "/api/content/workflows",
        json={
            "topic_id": topic_id,
            "angle_type": "framework",
            "platforms": ["linkedin"],
        },
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    run = await client.post(f"/api/content/workflows/{workflow_id}/run")
    assert run.status_code == 200, run.text
    workflow = run.json()
    assert workflow["status"] == "ready_for_approval", workflow["status"]
    adaptation = max(
        (a for a in workflow["artifacts"] if a["stage"] == "linkedin_adaptation"),
        key=lambda a: a["revision"],
    )
    return workflow_id, adaptation["content"]


@pytest.mark.asyncio
async def test_approval_records_a_post_and_a_clear_check(
    content_client: AsyncClient, db_session: AsyncSession
):
    workflow_id, _ = await approve_workflow(content_client, "gate-clear")
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert response.status_code == 200, response.text

    records = (
        (await db_session.execute(select(PostRecord).where(PostRecord.workflow_id == workflow_id)))
        .scalars()
        .all()
    )
    assert len(records) == 1
    assert records[0].origin == "workflow"
    assert records[0].status == "approved_unpublished"

    checks = (
        (
            await db_session.execute(
                select(DuplicateCheck).where(DuplicateCheck.workflow_id == workflow_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(checks) == 1
    assert checks[0].verdict == "clear"


@pytest.mark.asyncio
async def test_reapproval_does_not_duplicate_the_post_record(
    content_client: AsyncClient, db_session: AsyncSession
):
    workflow_id, _ = await approve_workflow(content_client, "gate-idempotent")
    for _ in range(2):
        response = await content_client.post(
            f"/api/content/workflows/{workflow_id}/approval",
            json={"platform": "linkedin", "decision": "approved", "actor": "user"},
        )
        assert response.status_code == 200, response.text
    records = (
        (await db_session.execute(select(PostRecord).where(PostRecord.workflow_id == workflow_id)))
        .scalars()
        .all()
    )
    assert len(records) == 1


@pytest.mark.asyncio
async def test_near_duplicate_is_blocked_then_allowed_with_an_override(
    content_client: AsyncClient, db_session: AsyncSession
):
    first_id, text = await approve_workflow(content_client, "gate-first")
    approved = await content_client.post(
        f"/api/content/workflows/{first_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text

    # Record the same text again so the second workflow has a true duplicate to
    # find that does not belong to its own workflow.
    manual = await content_client.post(
        "/api/memory/posts", json={"platform": "linkedin", "content": text}
    )
    assert manual.status_code == 201, manual.text

    second_id, _ = await approve_workflow(content_client, "gate-second")
    blocked = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert blocked.status_code == 409
    assert "duplicate" in blocked.json()["detail"].lower()

    overridden = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={
            "platform": "linkedin",
            "decision": "approved",
            "actor": "user",
            "duplicate_override": True,
            "override_reason": "Intentional follow-up in a series.",
        },
    )
    assert overridden.status_code == 200, overridden.text

    check = (
        (
            await db_session.execute(
                select(DuplicateCheck)
                .where(DuplicateCheck.workflow_id == second_id)
                .order_by(DuplicateCheck.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert check is not None
    assert check.overridden is True
    assert check.override_reason == "Intentional follow-up in a series."


@pytest.mark.asyncio
async def test_override_without_a_reason_is_rejected(content_client: AsyncClient):
    workflow_id, _ = await approve_workflow(content_client, "gate-noreason")
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={
            "platform": "linkedin",
            "decision": "approved",
            "actor": "user",
            "duplicate_override": True,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejection_does_not_record_a_post(
    content_client: AsyncClient, db_session: AsyncSession
):
    workflow_id, _ = await approve_workflow(content_client, "gate-reject")
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "rejected", "actor": "user"},
    )
    assert response.status_code == 200, response.text
    records = (
        (await db_session.execute(select(PostRecord).where(PostRecord.workflow_id == workflow_id)))
        .scalars()
        .all()
    )
    assert records == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_content_duplicate_gate.py -v`
Expected: FAIL — the `/api/memory/posts` route does not exist yet and no post records are written. This task and Task 9 together make it pass; run it again at the end of Task 9.

- [ ] **Step 3: Add override fields to the approval input**

In `src/content/schemas.py`, replace the `ApprovalDecisionInput` class (line 87) with:

```python
class ApprovalDecisionInput(BaseModel):
    platform: Platform
    decision: Literal["approved", "rejected"]
    actor: str = Field(default="user", min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=10_000)
    duplicate_override: bool = False
    override_reason: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def override_requires_a_reason(self) -> "ApprovalDecisionInput":
        if self.duplicate_override and not (self.override_reason or "").strip():
            raise ValueError("override_reason is required when duplicate_override is set")
        return self
```

Update the import at the top of the file from:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

to:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
```

- [ ] **Step 4: Wire the gate into `decide_approval`**

In `src/content/service.py`, add these imports alongside the existing ones:

```python
from src.llm.embeddings import EmbeddingProvider
from src.memory import service as memory_service
```

In `decide_approval`, change the signature to accept the embedder:

```python
async def decide_approval(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    data: ApprovalDecisionInput,
    run_id: uuid.UUID,
    embedder: EmbeddingProvider,
) -> ContentWorkflow:
```

Then, immediately after the existing grounding check block that ends with:

```python
    if not findings or any(finding["status"] != "supported" for finding in findings):
        raise ContentConflict("latest platform adaptation has not passed grounding checks")
    run = await _ensure_run(session, run_id)
```

insert the duplicate gate:

```python
    # M4 duplicate gate. Runs only for approvals: a rejection needs no
    # duplicate opinion, and must not write history.
    if data.decision == "approved":
        config = await memory_service.get_active_duplicate_config(session)
        evaluation = await memory_service.evaluate_duplicate(
            session,
            text=latest_adaptation.content,
            platform=data.platform,
            config=config,
            embedder=embedder,
            exclude_workflow_id=workflow.id,
            run_id=run.id,
        )
        blocked = evaluation.verdict == "block" and not data.duplicate_override
        await memory_service.persist_duplicate_check(
            session,
            workflow_id=workflow.id,
            platform=data.platform,
            evaluation=evaluation,
            overridden=evaluation.verdict == "block" and data.duplicate_override,
            override_reason=data.override_reason if data.duplicate_override else None,
            run_id=run.id,
        )
        if blocked:
            raise ContentConflict(
                "this draft is a near-duplicate of an existing post "
                f"(similarity {evaluation.top_similarity:.2f}); "
                "approve again with duplicate_override and a reason to proceed"
            )
```

Finally, after the block that sets `workflow.status` at the end of the function, and before `await session.flush()`, record the post:

```python
    if data.decision == "approved":
        await memory_service.record_workflow_post(
            session,
            workflow_id=workflow.id,
            platform=data.platform,
            content=latest_adaptation.content,
            embedder=embedder,
            run_id=run.id,
        )
```

- [ ] **Step 5: Pass the embedder from the route**

In `services/api/dependencies.py`, add:

```python
from src.llm.embeddings import EmbeddingProvider


def get_embedder(request: Request) -> EmbeddingProvider:
    return request.app.state.embedder
```

In `services/api/main.py`, after the `app.state.llm_client = MockLLM()` line, add:

```python
app.state.embedder = MockEmbedder()
```

and add the import:

```python
from src.llm.embeddings import MockEmbedder
```

In `services/api/routes/content.py`, update the approval handler to inject the embedder. Change its import line to include `get_embedder`:

```python
from services.api.dependencies import get_embedder, get_llm_client
```

add:

```python
from src.llm.embeddings import EmbeddingProvider
```

and update the approval endpoint body so the call passes `embedder=embedder`, adding this parameter to the handler signature:

```python
embedder: EmbeddingProvider = (Depends(get_embedder),)  # noqa: B008
```

- [ ] **Step 6: Verify**

Run: `uv run pytest tests/integration/test_content_api.py -v`
Expected: PASS — the existing M3 approval tests still pass with the gate in place.

- [ ] **Step 7: Commit**

```bash
git add src/content/service.py src/content/schemas.py services/api/dependencies.py services/api/main.py services/api/routes/content.py
git commit -m "feat(content): gate approval on the M4 duplicate check"
```

---

### Task 9: HTTP surface

**Files:**
- Create: `services/api/routes/memory.py`
- Modify: `services/api/main.py`
- Test: `tests/integration/test_memory_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_memory_api.py`:

```python
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.db.session import get_session


@pytest_asyncio.fixture
async def memory_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_create_and_list_manual_posts(memory_client: AsyncClient):
    created = await memory_client.post(
        "/api/memory/posts",
        json={
            "platform": "linkedin",
            "content": "Shipping beats polishing, most of the time.",
            "external_url": "https://example.com/posts/1",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["origin"] == "manual"
    assert body["embedding_model"] == "mock-embed-v1"

    listed = await memory_client.get("/api/memory/posts")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())


@pytest.mark.asyncio
async def test_manual_post_can_be_updated_and_deleted(memory_client: AsyncClient):
    created = await memory_client.post(
        "/api/memory/posts", json={"platform": "x", "content": "A short note."}
    )
    post_id = created.json()["id"]

    updated = await memory_client.patch(
        f"/api/memory/posts/{post_id}", json={"external_url": "https://example.com/x/1"}
    )
    assert updated.status_code == 200
    assert updated.json()["external_url"] == "https://example.com/x/1"

    deleted = await memory_client.delete(f"/api/memory/posts/{post_id}")
    assert deleted.status_code == 204

    missing = await memory_client.get(f"/api/memory/posts/{post_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_empty_update_is_rejected(memory_client: AsyncClient):
    created = await memory_client.post(
        "/api/memory/posts", json={"platform": "x", "content": "Another note."}
    )
    response = await memory_client.patch(f"/api/memory/posts/{created.json()['id']}", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_metric_snapshots_are_append_only(memory_client: AsyncClient):
    created = await memory_client.post(
        "/api/memory/posts",
        json={
            "platform": "linkedin",
            "content": "Measured over time.",
            "posted_at": "2026-08-01T00:00:00Z",
        },
    )
    post_id = created.json()["id"]
    for _ in range(3):
        captured = await memory_client.post(f"/api/memory/posts/{post_id}/metrics")
        assert captured.status_code == 201, captured.text
        assert captured.json()["is_mock"] is True

    snapshots = await memory_client.get(f"/api/memory/posts/{post_id}/metrics")
    assert snapshots.status_code == 200
    assert len(snapshots.json()) == 3


@pytest.mark.asyncio
async def test_duplicate_preview_reports_a_verdict(memory_client: AsyncClient):
    text = "Evidence packs make a draft auditable rather than merely fluent."
    await memory_client.post("/api/memory/posts", json={"platform": "linkedin", "content": text})
    preview = await memory_client.post(
        "/api/memory/duplicate-check", json={"platform": "linkedin", "content": text}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["verdict"] == "block"
    assert body["config_version"] == "v1"
    assert body["neighbours"]


@pytest.mark.asyncio
async def test_duplicate_configs_can_be_listed_and_created(memory_client: AsyncClient):
    listed = await memory_client.get("/api/memory/duplicate-configs")
    assert listed.status_code == 200
    assert any(item["version"] == "v1" for item in listed.json())

    created = await memory_client.post(
        "/api/memory/duplicate-configs",
        json={
            "version": "strict-v1",
            "warn_threshold": "0.500",
            "block_threshold": "0.700",
            "active": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["active"] is True


@pytest.mark.asyncio
async def test_duplicate_config_version_conflict_returns_409(memory_client: AsyncClient):
    response = await memory_client.post(
        "/api/memory/duplicate-configs",
        json={"version": "v1", "warn_threshold": "0.500", "block_threshold": "0.700"},
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_memory_api.py -v`
Expected: FAIL — all requests return 404 because the router does not exist.

- [ ] **Step 3: Write the routes**

Create `services/api/routes/memory.py`:

```python
"""HTTP surface for M4 content memory."""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.dependencies import get_embedder
from src.db.session import get_session
from src.llm.embeddings import EmbeddingProvider
from src.memory import service
from src.memory.analytics import MockAnalyticsProvider
from src.memory.models import DuplicateConfig, PostMetricSnapshot, PostRecord
from src.memory.schemas import (
    DuplicateConfigCreate,
    DuplicateConfigRead,
    DuplicatePreviewRequest,
    DuplicatePreviewResponse,
    PostMetricSnapshotRead,
    PostRecordCreate,
    PostRecordRead,
    PostRecordUpdate,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/posts", response_model=list[PostRecordRead])
async def get_posts(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[PostRecord]:
    return await service.list_post_records(session)


@router.post("/posts", response_model=PostRecordRead, status_code=status.HTTP_201_CREATED)
async def post_post(
    payload: PostRecordCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embedder: EmbeddingProvider = Depends(get_embedder),  # noqa: B008
) -> PostRecord:
    record = await service.create_post_record(
        session, payload, embedder=embedder, run_id=uuid.UUID(request.state.run_id)
    )
    await session.commit()
    return await service.require_post_record(session, record.id)


@router.get("/posts/{post_id}", response_model=PostRecordRead)
async def get_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostRecord:
    return await service.require_post_record(session, post_id)


@router.patch("/posts/{post_id}", response_model=PostRecordRead)
async def patch_post(
    post_id: uuid.UUID,
    payload: PostRecordUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostRecord:
    record = await service.update_post_record(session, post_id, payload)
    await session.commit()
    return await service.require_post_record(session, record.id)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    await service.delete_post_record(session, post_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/posts/{post_id}/metrics", response_model=list[PostMetricSnapshotRead])
async def get_metrics(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[PostMetricSnapshot]:
    record = await service.require_post_record(session, post_id)
    return list(record.snapshots)


@router.post(
    "/posts/{post_id}/metrics",
    response_model=PostMetricSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_metrics(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PostMetricSnapshot:
    snapshot = await service.capture_metrics(
        session, post_id=post_id, provider=MockAnalyticsProvider()
    )
    await session.commit()
    return snapshot


@router.get("/duplicate-configs", response_model=list[DuplicateConfigRead])
async def get_duplicate_configs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[DuplicateConfig]:
    return await service.list_duplicate_configs(session)


@router.post(
    "/duplicate-configs",
    response_model=DuplicateConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_duplicate_config(
    payload: DuplicateConfigCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DuplicateConfig:
    config = await service.create_duplicate_config(session, payload)
    await session.commit()
    return config


@router.post("/duplicate-check", response_model=DuplicatePreviewResponse)
async def post_duplicate_check(
    payload: DuplicatePreviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    embedder: EmbeddingProvider = Depends(get_embedder),  # noqa: B008
) -> DuplicatePreviewResponse:
    config = await service.get_active_duplicate_config(session)
    evaluation = await service.evaluate_duplicate(
        session,
        text=payload.content,
        platform=payload.platform,
        config=config,
        embedder=embedder,
        exclude_workflow_id=None,
        run_id=uuid.UUID(request.state.run_id),
    )
    await session.commit()
    return DuplicatePreviewResponse(
        verdict=evaluation.verdict,
        config_version=evaluation.config_version,
        top_similarity=evaluation.top_similarity,
        neighbours=evaluation.neighbours,
    )
```

- [ ] **Step 4: Register the router and error handler**

In `services/api/main.py`, add the imports:

```python
from services.api.routes.memory import router as memory_router
from src.memory.service import ContentMemoryError
```

Add the handler after the existing `content_error_handler`:

```python
@app.exception_handler(ContentMemoryError)
async def memory_error_handler(request: Request, exc: ContentMemoryError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "run_id": request.state.run_id},
    )
```

Add the router registration after the content router:

```python
app.include_router(memory_router, prefix="/api")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_memory_api.py tests/integration/test_content_duplicate_gate.py -v`
Expected: PASS — including the Task 8 gate tests, which needed this router.

- [ ] **Step 6: Commit**

```bash
git add services/api/routes/memory.py services/api/main.py tests/integration/test_memory_api.py tests/integration/test_content_duplicate_gate.py
git commit -m "feat(api): add content memory HTTP surface"
```

---

### Task 10: Duplicate panel in the Content workspace

**Files:**
- Create: `apps/web/app/content/DuplicatePanel.tsx`
- Modify: `apps/web/app/content/page.tsx`

`page.tsx` is already 737 lines, so the panel is a separate component rather than more inline JSX.

- [ ] **Step 1: Create the panel component**

Create `apps/web/app/content/DuplicatePanel.tsx`:

```tsx
"use client";

export interface DuplicateNeighbour {
  post_record_id: string;
  platform: string;
  lexical: number;
  semantic: number | null;
  score: number;
}

export interface DuplicatePreview {
  verdict: "clear" | "warn" | "block";
  config_version: string;
  top_similarity: number;
  neighbours: DuplicateNeighbour[];
}

const VERDICT_COLOR: Record<DuplicatePreview["verdict"], string> = {
  clear: "#166534",
  warn: "#b45309",
  block: "#b91c1c",
};

const VERDICT_TEXT: Record<DuplicatePreview["verdict"], string> = {
  clear: "No similar post found in history.",
  warn: "Similar to an existing post. Approval is still allowed.",
  block: "Too similar to an existing post. Approval requires an override reason.",
};

export function DuplicatePanel({
  preview,
  overrideReason,
  onOverrideReasonChange,
}: {
  preview: DuplicatePreview | null;
  overrideReason: string;
  onOverrideReasonChange: (value: string) => void;
}) {
  if (!preview) return null;

  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        marginTop: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 4 }}>Content memory check</h3>
      <p style={{ color: VERDICT_COLOR[preview.verdict], marginTop: 0 }}>
        <strong>{preview.verdict.toUpperCase()}</strong> · similarity{" "}
        {preview.top_similarity.toFixed(2)} · policy {preview.config_version}
      </p>
      <p style={{ color: "#4b5563", marginTop: 0 }}>{VERDICT_TEXT[preview.verdict]}</p>

      {preview.neighbours.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#6b7280" }}>
              <th style={{ padding: "4px 0" }}>Existing post</th>
              <th>Platform</th>
              <th>Lexical</th>
              <th>Semantic</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {preview.neighbours.slice(0, 5).map((item) => (
              <tr key={item.post_record_id} style={{ borderTop: "1px solid #f3f4f6" }}>
                <td style={{ padding: "4px 0" }}>{item.post_record_id.slice(0, 8)}</td>
                <td>{item.platform}</td>
                <td>{item.lexical.toFixed(2)}</td>
                <td>{item.semantic === null ? "—" : item.semantic.toFixed(2)}</td>
                <td>
                  <strong>{item.score.toFixed(2)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {preview.verdict === "block" && (
        <label style={{ display: "block", marginTop: 12 }}>
          <span style={{ display: "block", marginBottom: 4 }}>
            Override reason (required to approve)
          </span>
          <input
            value={overrideReason}
            onChange={(event) => onOverrideReasonChange(event.target.value)}
            placeholder="Why is this near-duplicate intentional?"
            style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 6 }}
          />
        </label>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Wire the panel into the page**

In `apps/web/app/content/page.tsx`, add the import below the existing React import:

```tsx
import { DuplicatePanel, DuplicatePreview } from "./DuplicatePanel";
```

Add state next to the other `useState` declarations in the component:

```tsx
  const [duplicatePreview, setDuplicatePreview] = useState<DuplicatePreview | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
```

Replace the `decide` function (line 329) with a version that previews first and passes the override:

```tsx
  async function previewDuplicate(platform: "linkedin" | "x") {
    if (!selected) return;
    const adaptation = latestArtifacts(selected).find(
      (artifact) => artifact.stage === `${platform}_adaptation`,
    );
    if (!adaptation) return;
    const preview = await request<DuplicatePreview>("/api/memory/duplicate-check", {
      method: "POST",
      body: JSON.stringify({ platform, content: adaptation.content }),
    });
    setDuplicatePreview(preview);
  }

  function decide(platform: "linkedin" | "x", decision: "approved" | "rejected") {
    if (!selected) return;
    const override = duplicatePreview?.verdict === "block" && overrideReason.trim().length > 0;
    void runAction(async () => {
      const updated = await request<Workflow>(
        `/api/content/workflows/${selected.id}/approval`,
        {
          method: "POST",
          body: JSON.stringify({
            platform,
            decision,
            actor: "user",
            reason: decision === "approved" ? "Reviewed in Content workspace." : "Needs revision.",
            duplicate_override: override,
            override_reason: override ? overrideReason.trim() : null,
          }),
        },
      );
      replaceWorkflow(updated);
      setDuplicatePreview(null);
      setOverrideReason("");
      return `${label(platform)} draft ${decision}. No external action was performed.`;
    }, "Approval recorded.");
  }
```

In the approval block (around line 562), add a check button and the panel. Directly after the closing tag of the `approval.map(...)` list, insert:

```tsx
                  <button
                    type="button"
                    onClick={() => void previewDuplicate(selected.approvals[0].platform)}
                    style={{ marginTop: 8 }}
                  >
                    Check content memory
                  </button>
                  <DuplicatePanel
                    preview={duplicatePreview}
                    overrideReason={overrideReason}
                    onOverrideReasonChange={setOverrideReason}
                  />
```

- [ ] **Step 3: Verify the build**

Run: `cd apps/web && npm run build`
Expected: build succeeds and `/content` still compiles.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/content/DuplicatePanel.tsx apps/web/app/content/page.tsx
git commit -m "feat(web): show the content memory duplicate check on approval"
```

---

### Task 11: Analytics page

**Files:**
- Modify: `apps/web/app/analytics/page.tsx`

- [ ] **Step 1: Replace the stub**

Replace the entire contents of `apps/web/app/analytics/page.tsx`:

```tsx
"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Snapshot {
  id: string;
  captured_at: string;
  source: string;
  is_mock: boolean;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  reposts: number | null;
  clicks: number | null;
  follows: number | null;
}

interface PostRecord {
  id: string;
  platform: string;
  origin: string;
  status: string;
  content: string;
  external_url: string | null;
  posted_at: string | null;
  snapshots: Snapshot[];
  created_at: string;
}

export default function AnalyticsPage() {
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ platform: "linkedin", content: "", external_url: "" });

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/memory/posts`);
      if (!response.ok) throw new Error(await response.text());
      setPosts((await response.json()) as PostRecord[]);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load posts.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function addPost(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch(`${API_URL}/api/memory/posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: form.platform,
          content: form.content,
          external_url: form.external_url || null,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      setForm({ platform: "linkedin", content: "", external_url: "" });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to add post.");
    }
  }

  async function capture(postId: string) {
    try {
      const response = await fetch(`${API_URL}/api/memory/posts/${postId}/metrics`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await response.text());
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to capture metrics.");
    }
  }

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <header style={{ marginBottom: 24 }}>
        <p style={{ color: "#6b7280", marginBottom: 4 }}>M4 · Content Memory</p>
        <h1 style={{ margin: 0 }}>Post history</h1>
        <p style={{ color: "#4b5563" }}>
          Approved drafts and manually recorded posts. Metrics come from a deterministic mock
          provider and are not real platform data.
        </p>
      </header>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <form onSubmit={addPost} style={{ marginBottom: 24, display: "grid", gap: 8 }}>
        <h2 style={{ marginBottom: 0 }}>Record a post published elsewhere</h2>
        <select
          value={form.platform}
          onChange={(event) => setForm({ ...form, platform: event.target.value })}
          style={{ padding: 8, maxWidth: 200 }}
        >
          <option value="linkedin">LinkedIn</option>
          <option value="x">X</option>
        </select>
        <textarea
          value={form.content}
          onChange={(event) => setForm({ ...form, content: event.target.value })}
          placeholder="Post text"
          required
          rows={4}
          style={{ padding: 8 }}
        />
        <input
          value={form.external_url}
          onChange={(event) => setForm({ ...form, external_url: event.target.value })}
          placeholder="https://… (optional)"
          style={{ padding: 8 }}
        />
        <button type="submit" style={{ padding: 8, maxWidth: 160 }}>
          Add to history
        </button>
      </form>

      {posts.length === 0 && <p style={{ color: "#6b7280" }}>No posts recorded yet.</p>}

      {posts.map((post) => {
        const latest = post.snapshots[post.snapshots.length - 1];
        return (
          <article
            key={post.id}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              padding: 16,
              marginBottom: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <div>
                <strong>{post.platform === "linkedin" ? "LinkedIn" : "X"}</strong>
                <span style={{ color: "#6b7280" }}>
                  {" "}
                  · {post.origin} · {post.status.replace(/_/g, " ")}
                </span>
              </div>
              <button type="button" onClick={() => void capture(post.id)}>
                Capture mock metrics
              </button>
            </div>
            <p style={{ whiteSpace: "pre-wrap", color: "#111827" }}>{post.content}</p>
            {latest ? (
              <p style={{ color: "#4b5563", fontSize: 14 }}>
                {latest.impressions ?? "—"} impressions · {latest.reactions ?? "—"} reactions ·{" "}
                {latest.comments ?? "—"} comments · {latest.reposts ?? "—"} reposts ·{" "}
                {post.snapshots.length} snapshot(s)
                {latest.is_mock && " · mock data"}
              </p>
            ) : (
              <p style={{ color: "#6b7280", fontSize: 14 }}>No metrics captured yet.</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd apps/web && npm run build`
Expected: build succeeds and `/analytics` is listed with a non-trivial size.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/analytics/page.tsx
git commit -m "feat(web): add post history and mock metrics to the analytics page"
```

---

### Task 12: Documentation and full verification

**Files:**
- Modify: `ARCHITECTURE.md`, `README.md`, `ROADMAP.md`, `HANDOVER.md`

- [ ] **Step 1: Run the full verification suite**

Run:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest && (cd apps/web && npm run build)
```

Expected: all pass. Fix anything that fails before continuing — do not document a milestone as complete on a red suite.

- [ ] **Step 2: Verify a fresh migration from empty**

Run: `uv run alembic downgrade base && uv run alembic upgrade head && uv run pytest tests/integration/test_migration.py -v`
Expected: PASS with empty drift.

- [ ] **Step 3: Update `ARCHITECTURE.md`**

In "Current state", add M4 to the completed list. In the Database section, after the `0004_content_engine` block, add:

```markdown
Migration `0005_content_memory` adds:

- **`post_records`** — post history per platform, from approved workflows or
  manual backfill, with normalized text, content hash, and provider-tagged
  embeddings. A unique `(workflow_id, platform)` pair makes workflow-origin
  creation idempotent.
- **`post_metric_snapshots`** — append-only, mock-tagged performance samples.
  Unreported metrics stay NULL rather than 0.
- **`duplicate_configs`** and **`duplicate_checks`** — versioned warn/block
  thresholds and the persisted, explainable verdict with both sub-scores, the
  nearest post, and any recorded override.
```

Add a "Content Memory" section after "Content Engine":

```markdown
## Content Memory

`src/memory/service.py` owns post history and duplicate policy.
`src/memory/similarity.py` is pure: cosine similarity, lexical Jaccard reused
from M2, and verdict banding, with no session and no thresholds of its own.

Candidate retrieval is a SQL prefilter followed by in-Python scoring. Vectors
are dimension-unconstrained, so Postgres cannot index them; a database-side
nearest-neighbour query would scan anyway while making the lexical signal
impossible to blend. Only vectors from the same embedding model are compared.

The combined score is `max(lexical, semantic)`, not a weighted mean: either
signal alone is sufficient evidence, and averaging would dilute a strong signal.
Both sub-scores are persisted so every verdict is explainable.

`decide_approval` is the only M3 seam. A `block` verdict refuses approval unless
the request carries an override with a written reason, which is persisted on the
check. Approval then records the post. Rejection records nothing.

`MockEmbedder` hashes tokens, so it measures vocabulary overlap and cannot
detect a paraphrase sharing no words with the original. `MockAnalyticsProvider`
invents deterministic figures and tags every snapshot `is_mock`. Neither is a
substitute for a real provider.
```

Add the memory HTTP surface after the content one:

```markdown
### Content memory HTTP surface

- `GET|POST /api/memory/posts`
- `GET|PATCH|DELETE /api/memory/posts/{post_id}`
- `GET|POST /api/memory/posts/{post_id}/metrics`
- `GET|POST /api/memory/duplicate-configs`
- `POST /api/memory/duplicate-check`
```

- [ ] **Step 4: Update `ROADMAP.md`**

Change the M4 status table row to `**Complete**`, and replace the "Next milestone; design approved, implementation not started." line under `## M4 — Content Memory` with a Delivered paragraph:

```markdown
Delivered: post history from approved workflows and manual backfill; an
`EmbeddingProvider` protocol with a deterministic `MockEmbedder` whose spend is
cost-logged through `llm_calls`; versioned warn/block duplicate policy with
explainable lexical and semantic sub-scores; an approval gate that refuses a
near-duplicate without a recorded override reason; append-only mock metric
snapshots; and post history and duplicate surfaces in the web app.
```

- [ ] **Step 5: Update `README.md`**

Change the M4 status line to complete, set "Next" to M5 — Job Engine, add `/analytics` to the surface list, add a first-use step for recording history and checking duplicates, and add the plan link to the documentation index:

```markdown
- [`docs/superpowers/plans/2026-08-12-m4-content-memory.md`](docs/superpowers/plans/2026-08-12-m4-content-memory.md)
  — completed M4 implementation checklist
```

- [ ] **Step 6: Rewrite `HANDOVER.md`**

Update: the date, milestone status (M4 complete, next M5), the migration list through `0005`, the API route list, the verification counts from the actual test output in Step 1 (do not copy the numbers from this plan — run the suite and read them), and the known limitations. Add to limitations:

```markdown
- `MockEmbedder` hashes tokens, so semantic duplicate detection currently
  detects vocabulary overlap only. A reworded post sharing no words with the
  original will not be caught until a real embedding provider is configured.
- Analytics figures are invented by `MockAnalyticsProvider` and tagged
  `is_mock`. No real platform metrics exist.
```

Set the "Next task" section to describe M5 — Job Engine.

- [ ] **Step 7: Commit**

```bash
git add ARCHITECTURE.md README.md ROADMAP.md HANDOVER.md
git commit -m "docs: record M4 content memory as complete"
```

---

## Verification checklist

Run before declaring M4 done. Every item must pass, and the numbers in `HANDOVER.md` must come from this run, not from this plan.

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pyright` — 0 errors
- [ ] `uv run pytest` — all pass
- [ ] `cd apps/web && npm run build`
- [ ] `uv run alembic downgrade base && uv run alembic upgrade head`
- [ ] `uv run pytest tests/integration/test_migration.py` — empty drift
- [ ] A blocked approval returns 409 and succeeds with an override reason
- [ ] No platform API, publishing, or scheduling was introduced
