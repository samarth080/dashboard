# M4: Content Memory — Design

Date: 2026-08-12
Status: Approved, not implemented

## Purpose

Give the system a memory of what has already been said. M3 can produce a
well-grounded draft that is nearly identical to a post from six weeks ago and
has no way to notice. M4 records post history, embeds it, and refuses to let a
near-duplicate reach approval without an explicit, recorded human override.

M4 also establishes the analytics schema and a mock provider so performance
history begins accumulating now, rather than leaving M9 to start from an empty
table.

Publishing remains deferred. M4 introduces no platform API, no scheduler, and
no autonomous loop.

## Success criteria

- Approving an M3 workflow for a platform records a `PostRecord` for that
  platform, and re-approval does not create a second one.
- The user can manually record posts already published elsewhere, so duplicate
  detection has a corpus before any workflow is approved.
- The service embeds every post it writes and tags it with the producing model.
  Similarity is only ever computed between vectors from the same model.
- Similarity thresholds live in a versioned database row. The engine contains
  no default thresholds.
- A candidate above the block threshold cannot be approved without an explicit
  override carrying a written reason; both the verdict and the override are
  persisted and inspectable.
- Every duplicate verdict stores its lexical and semantic sub-scores and the
  nearest post, so the decision is explainable rather than a bare number.
- Metric snapshots are append-only and tagged as mock; no snapshot is ever
  overwritten.
- Unit, integration, migration-drift, lint, type, and web-build checks pass.

## Boundaries

- No social platform API, account connection, scheduling, or publishing. Those
  remain behind the M7 capability gate.
- No autonomous metric polling. Snapshot capture is user-triggered; M8 owns
  orchestration.
- No engagement-based ranking, recommendation, or model training. M4 stores
  performance data; M9 interprets it.
- `memory_records` is not touched. The M1 Content and Performance domains stay
  available for the deferred recall workflow.
- No real embedding or analytics provider is credentialed. Deterministic mocks
  remain the local default.

## Post history

`PostRecord` is one row per post per platform. Two origins produce it:

- `workflow` — created when an M3 platform approval becomes `approved`. Status
  is `approved_unpublished`. Nothing was published; the name says so.
- `manual` — user backfill of content already published elsewhere, with an
  optional external URL and posted-at date. Status is `published_externally`.

A unique constraint on `(workflow_id, platform)` makes workflow-origin creation
idempotent across re-approval. Postgres treats NULLs as distinct in unique
constraints, so manual rows, which carry a null `workflow_id`, are unaffected.

Stored text is normalized and hashed with the existing `src/research/dedup.py`
helpers, so exact-duplicate detection is free and consistent with M2.

## Embedding provider

`src/llm/embeddings.py` defines the contract, beside `protocol.py`, because it
is provider infrastructure rather than memory domain logic:

```python
class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...
    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...
```

Two rules carry over unchanged from `LLMClient`:

1. Providers never persist. They return results; callers decide what to write.
2. Every result carries accurate usage metadata — model, tokens, latency, and
   `Decimal` cost — so embedding spend is cost-loggable.

Embedding calls log to the existing `llm_calls` table with `prompt_version` set
to a logical identifier such as `embedding/mock-embed-v1` and `output_tokens`
of zero. No parallel cost table is introduced; `llm_calls` needs no schema
change.

`MockEmbedder` is deterministic, makes no network call, reports zero cost, and
returns an L2-normalized 1024-dimension hashed bag-of-words vector.

**Its limitations are real and must be documented alongside MockLLM's.** They
run in both directions. Because it hashes tokens, it measures vocabulary
overlap and cannot detect a genuine paraphrase that shares no words with the
original. And because distinct tokens collide into a fixed number of buckets,
it also reports overlap that does not exist, increasingly so as documents
lengthen.

The bucket count is what governs that second failure. Measured on text with
zero shared vocabulary, 256 buckets produced a cosine of 0.63 at 400 distinct
tokens — a typical post length, and close enough to the seeded 0.70 warn
threshold to cause false blocks, since scoring combines with `max`. At 1024
buckets the same pair scores 0.27 while paraphrase detection is unchanged, so
1024 is the floor, not a preference.

Duplicate thresholds must therefore never be calibrated against this embedder.
It validates the pipeline, not the semantics. Meaningful semantic detection
requires a real provider, which the protocol allows without changing any M4
logic.

Vector columns stay dimension-unconstrained, matching M2. No ANN index is
possible until a provider fixes the dimension, which is acceptable at
single-user corpus size.

## Duplicate detection

`src/memory/similarity.py` holds pure functions with no session and no I/O, so
the entire scoring engine is unit-testable without containers.

- `cosine_similarity(a, b)` raises `ValueError` on dimension mismatch rather
  than returning a meaningless number, and clamps negative results to `0.0`.
- `score_pair(...)` returns `SimilarityComponents` with `lexical`,
  `semantic | None`, and a combined `score`.

The combination rule is `max(lexical, semantic)`, not a weighted mean. Either
signal alone is sufficient evidence: a copy-paste scores 1.0 lexically, a
reworded post scores high semantically, and averaging would dilute each strong
signal with the other's weakness. Both sub-scores are persisted so a verdict can
always be explained.

Exact-duplicate text needs no special case: `content_hash` is a digest of the
same normalized text the tokenizer reads, so identical content already scores
1.0 lexically. `content_hash` earns its place as a stored column for cheap SQL
equality, not as a branch in the scorer.

A post record with no stored vector is scored lexically only. That is a
deliberate fallback, not a failure, so `score_pair` computes a semantic score
only when both sides supply an embedding.

Word-trigram Jaccard collapses to all-or-nothing below three tokens, so very
short posts — X posts especially — get a weak lexical signal and lean on the
semantic one.

Candidate selection filters to:

- the same `embedding_model`, because comparing across vector spaces is
  meaningless and raises at query time;
- the same platform, unless the active config enables `cross_platform_check`;
- within `lookback_days`, when configured;
- excluding post records belonging to the candidate's own workflow, or a
  workflow would block itself.

`cross_platform_check` defaults to false. Posting the same idea to LinkedIn and
X is normal practice, not duplication.

The compared text is the latest platform adaptation artifact for the platform
being approved, and the corpus is `post_records` only. Drafts belonging to other
in-flight workflows are not history and are never candidates.

Retrieval is a SQL prefilter followed by in-Python scoring. Postgres cannot
index these vectors without a fixed dimension, so a database-side nearest
neighbour query would sequentially scan anyway while making the lexical signal
impossible to blend and the engine harder to test.

### Thresholds and verdicts

`DuplicateConfig` is versioned in the database with an active flag, mirroring
`scoring_configs`. It holds `warn_threshold` and `block_threshold` as `Numeric`,
`cross_platform_check`, and optional `lookback_days`. The engine has no default
thresholds, exactly as the M2 scorer has no default weights.

Migration `0005` seeds version 1 as active with `warn_threshold` `0.70`,
`block_threshold` `0.85`, `cross_platform_check` false, and no lookback bound.
Seeding puts the starting policy in data the user can edit, which is not the
same as hard-coding it in the scorer. If no active config exists, the check
cannot be evaluated and approval raises `ContentConflict` rather than silently
treating the candidate as clear.

- `score >= block_threshold` → `block`
- `score >= warn_threshold` → `warn`
- otherwise → `clear`

`warn` surfaces the nearest posts and proceeds. `block` refuses approval.

## Integration with M3

M4 touches `src/content/service.py` at exactly one seam: `decide_approval`,
immediately after the existing grounding check.

1. Run the duplicate check and persist a `DuplicateCheck` row.
2. On `block`, raise `ContentConflict` unless the request carries
   `duplicate_override` with a non-empty `override_reason`. The check row
   records `overridden` and the reason either way.
3. When a platform approval becomes `approved`, create that platform's
   `PostRecord`, embedding its content through the configured provider.

The roadmap guardrail — never auto-publish something highly similar — holds:
auto-publishing does not exist, and any override is an explicit human act
recorded against a run in the audit trail.

## Analytics

`AnalyticsProvider` exposes `fetch(post) -> PostMetrics`.
`MockAnalyticsProvider` derives a plausible growth curve deterministically from
the post id and its age, so repeated calls for the same post and age are stable,
and stamps `is_mock=True` on every snapshot it produces.

`PostMetricSnapshot` rows are append-only and never updated, matching the
project's rule that raw records are not mutated. M9 can therefore reconstruct
how a post accumulated engagement rather than seeing only a final total.

Metrics a provider does not report are stored as `null`, never `0`. A zero that
means "unknown" would silently corrupt any later analysis.

Capture is user-triggered. No scheduler or polling loop is introduced.

## Data model

Migration `0005_content_memory` adds:

- **`post_records`** — `platform`, `content`, `normalized_content`,
  `content_hash`, `origin` (`workflow`/`manual`), nullable `workflow_id`,
  `status` (`approved_unpublished`/`published_externally`), nullable
  `posted_at` and `external_url`, paired `embedding` and `embedding_model`,
  timestamps. Unique `(workflow_id, platform)`.

  The embedding columns are nullable at the schema level, matching M2 and
  keeping a provider outage from blocking a write, but the service always
  embeds on write. A row without a vector is scored lexically only.
- **`post_metric_snapshots`** — indexed `post_record_id`, `captured_at`,
  `source`, `is_mock`, and nullable `impressions`, `reactions`, `comments`,
  `reposts`, `clicks`, `follows`.
- **`duplicate_configs`** — unique `version`, `active`, `Numeric`
  `warn_threshold` and `block_threshold`, `cross_platform_check`,
  nullable `lookback_days`.
- **`duplicate_checks`** — `workflow_id`, `platform`, `config_version`,
  `verdict` (`clear`/`warn`/`block`), `Numeric` `top_similarity`, nullable
  `nearest_post_record_id`, `components` JSON of per-neighbour sub-scores,
  `overridden`, `override_reason`, and `run_id`.

Enumerated columns use check constraints, timestamps are `timestamptz`,
thresholds and scores are `Numeric`, and every foreign key is indexed, per the
architecture conventions.

## Modules

A new `src/memory/` package, parallel to `src/research/` and `src/content/`:

| File | Purpose |
| --- | --- |
| `models.py` | `PostRecord`, `PostMetricSnapshot`, `DuplicateConfig`, `DuplicateCheck` |
| `schemas.py` | Pydantic request and response types |
| `similarity.py` | Pure scoring functions, no I/O |
| `service.py` | Transaction-neutral domain rules |
| `analytics.py` | `AnalyticsProvider` protocol and `MockAnalyticsProvider` |

`src/content/service.py` is already 772 lines. M4 adds its logic in
`src/memory/`, not there, and calls into it from the single approval seam.

Services commit; the service layer stays transaction-neutral, matching M1
through M3.

## API

New routes in `services/api/routes/memory.py`:

- `GET|POST /api/memory/posts`
- `GET|PATCH|DELETE /api/memory/posts/{post_id}`
- `GET|POST /api/memory/posts/{post_id}/metrics`
- `GET|POST /api/memory/duplicate-configs`
- `POST /api/memory/duplicate-check`

Modified:

- `POST /api/content/workflows/{workflow_id}/approval` accepts optional
  `duplicate_override` and `override_reason`.

Validation failures return `422`, missing records `404`, and conflicts `409`.
Conflicts cover a blocked approval without an override and an attempt to delete
a workflow-origin post record, which belongs to its workflow's history.

## Web

- `/content` gains a duplicate panel on the approval step showing the verdict,
  nearest posts, both sub-scores, and the override control with its required
  reason.
- The existing `/analytics` stub route becomes the post history and metric
  snapshot view, including manual backfill.

## Testing

Unit:

- cosine similarity, including the dimension-mismatch raise and negative clamp
- lexical reuse of `dedup.py` and the `max` combination rule
- verdict banding against configured thresholds
- `MockEmbedder` determinism, normalization, and dimension
- `MockAnalyticsProvider` determinism and metric bounds
- paired `embedding`/`embedding_model` validation
- override requires a non-empty reason

Integration:

- `0005` applies from empty and metadata drift is empty
- approval creates a post record; re-approval does not duplicate it
- a blocked candidate refuses approval, and an override succeeds and persists
- same-workflow exclusion and `cross_platform_check` in both states
- snapshots are append-only across repeated capture
- 1024-dimension vector round-trip through pgvector

## Deferred

- A real embedding provider, and any ANN index requiring a fixed dimension.
- Real platform analytics, which is gated behind M7 capability verification.
- Engagement-driven recommendation and learning, which is M9.
- Autonomous memory recall into content generation, which remains deliberately
  unscheduled per the architecture.
