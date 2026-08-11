# Architecture

Personal Career + Content + Network Intelligence Engine.

This document describes what exists today and the boundaries later milestones
are expected to build within. It is not a description of the finished system —
see `ROADMAP.md` for that.

## Current state

Milestones **M0 (Repository Foundation)**, **M1 (Personal Brain)**, and **M2
(Research Engine)** are complete. The system has editable personal context,
safe public-feed ingestion, normalized and deduplicated documents, clustered
and ranked research topics, and source-grounded evidence packs. Content
generation, jobs, and network features have not started.

## Shape of the system

```
apps/web/          Next.js + TypeScript dashboard
services/api/      FastAPI HTTP service
services/worker/   Celery worker (Redis broker + result backend)
src/               Shared library code, imported by both services
  core/              settings, structured logging, run_id context
  brain/             profile, interests, memory, settings, voice workflow
  db/                SQLAlchemy 2 async engine/session, models
  llm/               LLM protocol, prompt registry, MockLLM, call persistence
  research/          sources, normalization, dedup, extraction, ranking, evidence
prompts/            Versioned prompt files
alembic/           Migrations
tests/             unit/ and integration/
```

`services/` and `apps/` are entry points. `src/` is the library they share.
Dependencies point one way: `services/` imports `src/`, never the reverse.

## Packaging

A single **non-packaged uv project** (`[tool.uv] package = false`) with one
`pyproject.toml` at the root. `src/` and `services/` import as plain packages
via `uv run` from the repo root.

This is deliberately *not* a uv workspace. Workspaces exist to publish multiple
distributable packages; nothing here is separately distributable, and per-service
manifests would add lockfile coordination for no benefit. Revisit only if a
component genuinely needs to ship on its own.

## Configuration

`src/core/settings.py` is the single source of configuration truth — a
`pydantic-settings` `Settings` object read from environment and `.env`, exposed
via a cached `get_settings()`.

Nothing else reads `os.environ` directly. Adding config means adding a field
here, not scattering lookups.

`UserSettings` is deliberately separate. It stores editable product preferences
such as timezone, locale, daily LLM budget, approval level, and whether memory
is enabled. Environment configuration describes how the process runs; user
settings describe how the product should behave.

## Observability: the run_id thread

Every unit of work carries a `run_id` that appears in every log line it emits,
so work can be traced end to end across services.

- **HTTP**: middleware in `services/api/main.py` generates one per request,
  exposes it as the `X-Run-Id` response header, and scopes it with
  `run_context()`.
- **Background tasks**: a Celery `task_prerun` signal in
  `services/worker/celery_app.py` binds a fresh one per task execution.
- **Logs**: `JSONFormatter` emits `timestamp`, `level`, `logger`, `message`,
  `run_id`, any `extra={...}` fields, and the full traceback when
  `logger.exception()` is used.

Use `run_context()` (a context manager that restores the previous value) rather
than bare `set_run_id()` wherever the work has a scope. `set_run_id()` exists
for the Celery signal, which has no scope to wrap.

## Database

PostgreSQL via SQLAlchemy 2 async (asyncpg). Migrations are Alembic; **every**
schema change requires one.

The M0 audit/cost tables are:

- **`runs`** — the audit anchor. `id` is a UUID primary key, and it is the same
  value that appears as `run_id` in logs, so a log line can be joined directly
  to its database row. Later milestones' tracking tables should foreign-key
  into this.
- **`llm_calls`** — model usage and cost per run: model, prompt version, input
  and output tokens, latency, cost. Foreign-keys to `runs.id` (indexed).

Migration `0002_personal_brain` adds:

- **`user_profiles`**, **`career_profiles`**, and **`user_settings`** — the
  editable single-user source of truth. One-to-one records use unique profile
  foreign keys.
- **`interests`** — configurable weighted nodes with an optional self-referential
  parent. Display names are preserved while normalized names prevent duplicate
  case variants. The service rejects hierarchy cycles.
- **`writing_samples`** and **`voice_profiles`** — confirmed source text and its
  derived, versioned voice analysis.
- **`memory_records`** — inspectable key/value memory scoped to one of seven
  explicit domains, with provenance, confidence, and an enabled flag.

Migration `0003_research_engine` enables pgvector and adds:

- **`research_sources`** and **`raw_documents`** — configured feeds and immutable
  normalized payloads with canonical URL, content hash, credibility, metadata,
  duplicate lineage, and optional provider-tagged embeddings.
- **`scoring_configs`**, **`topic_candidates`**, and **`topic_documents`** —
  versioned ranking policy, persisted score components, extraction run/prompt
  provenance, deterministic cluster keys, and source-document membership.
- **`evidence_packs`**, **`claims`**, and **`evidence_sources`** — topic theses,
  explicit verification status, and exact document-backed excerpts.

### Conventions later milestones must follow

- **Timestamps are `timestamptz`**, never naive. Use
  `DateTime(timezone=True)` with both a Python default (`utcnow()`) and
  `server_default=func.now()`, so inserts that bypass the ORM still work. This
  system ingests dates from many timezones; naive timestamps are a silent-bug
  source.
- **Money is `Decimal`**, never `float`. `Numeric` columns return `Decimal`, and
  mixing the two raises `TypeError`.
- **Index your foreign keys.** Postgres does not do it for you.

### Engine lifecycle

`get_engine()` and `get_sessionmaker()` build lazily and are cached. Importing
`src.db.session` therefore has no side effects, tests can retarget the database
by clearing the caches, and a forked worker builds its own pool rather than
inheriting the parent's sockets.

pgvector is enabled by migration `0003` before its first columns are created.
Embeddings remain nullable and store their model identifier. The vector columns
are dimension-unconstrained because no provider has been selected; similarity
queries must compare only rows from the same embedding model/vector space.

## Personal Brain

`src/brain/service.py` owns domain rules and stays transaction-neutral; API
routes commit mutations. The primary profile uses a unique `profile_key` of
`primary`, making today's single-user assumption explicit without hard-coding a
person's identity.

Interests are arbitrary user data—there is no built-in niche taxonomy. Parent
nodes must belong to the same profile, and both direct and indirect cycles are
rejected before persistence.

Memory is intentionally bounded. M1 provides storage and seven explicit domain
labels (Personal, Voice, Content, Research, Relationship, Career, Performance),
not an autonomous memory-writing loop. Later milestones own the rules for their
domains.

Writing samples require affirmative `confirmed_user_provided=true` validation.
Voice analysis reads only those stored samples, enforces a per-task character
limit and the user's daily LLM budget, then stores the structured profile and
prompt version. The structured LLM usage row is linked to a `Run` whose UUID is
the same `X-Run-Id` returned by the request.

### HTTP surface

- `GET /api/health`
- `GET|PUT /api/profile`
- `GET|PUT /api/profile/career`
- `GET|POST /api/interests`
- `PATCH|DELETE /api/interests/{interest_id}`
- `GET|PUT /api/settings`
- `GET /api/voice`
- `GET|POST /api/voice/samples`
- `DELETE /api/voice/samples/{sample_id}`
- `POST /api/voice/analyze`

Profile-dependent routes return `404` until the primary profile exists. Domain
validation failures use `422`, and normalized-name conflicts use `409`.

## Research Engine

`ContentSource` adapters return normalized values and never persist directly.
`RSSSource` parses RSS 2.x and Atom fixture XML with the standard library. Live
fetches accept only public HTTP(S) destinations, revalidate redirects, enforce a
10-second timeout, cap responses at 2 MB, and reject addresses that resolve to
non-public IP space.

Ingestion canonicalizes scheme/host/path/query, removes known tracking
parameters and fragments, normalizes Unicode/whitespace, then checks canonical
URL, exact SHA-256 content hash, and configurable word-shingle Jaccard
similarity. Exact duplicates return the canonical row; near-duplicates are kept
for provenance with `duplicate_of_id` and excluded from default topic inputs.

Topic extraction uses `research-topic-extraction/v1` and the shared
`LLMClient`. Suggestions may only cite supplied document UUIDs. Within an
extraction call, normalized cluster keys collapse overlapping suggestions and
merge their document membership. Ranking is a Decimal weighted mean whose
weights and near-duplicate threshold come from the active `ScoringConfig`; the
scorer contains no default product weights.

Evidence packs enforce the key provenance boundary: a source must be linked to
the topic, and a claim cannot be marked supported without at least one
supporting excerpt.

### Research HTTP surface

- `GET|POST /api/research/sources`
- `PATCH /api/research/sources/{source_id}`
- `POST /api/research/sources/{source_id}/refresh`
- `GET|POST /api/research/documents`
- `GET /api/research/documents/{document_id}`
- `GET|POST /api/research/scoring-configs`
- `POST /api/research/extract`
- `GET|POST /api/research/topics`
- `GET /api/research/topics/{topic_id}`
- `POST /api/research/topics/{topic_id}/rescore`
- `GET|PUT /api/research/topics/{topic_id}/evidence`

## LLM abstraction

`src/llm/protocol.py` defines `LLMClient`, the contract every provider
implements:

- `generate(prompt, *, prompt_version) -> LLMResult`
- `structured[T](prompt, *, prompt_version, schema: type[T]) -> StructuredResult[T]`

Two rules hold for all implementations:

1. **Clients never persist anything.** They return results; callers decide
   whether to write them. Persistence lives in `log_llm_call()`
   (`src/llm/persistence.py`), which flushes to obtain a primary key and leaves
   the transaction to the caller.
2. **Every result carries accurate usage metadata** — model, prompt version,
   tokens, latency, cost — because cost tracking depends on it. `structured()`
   returns `StructuredResult` (parsed value *plus* usage) precisely so structured
   calls are cost-loggable; a bare parsed object would put a hole in the
   cost-tracking table.

`MockLLM` is the only implementation today. It is deterministic, makes no
network calls, reports zero cost, accepts an injectable canned response, and can
satisfy schemas with required fields — so complete workflows are testable
without credentials. A real provider remains deferred until credentialed model
quality is explicitly needed and its budget behavior can be tested.

Prompts live under `prompts/<name>/<version>.md` and are loaded through the
path-safe registry in `src/llm/prompts.py`. Callers store a logical version such
as `voice-analysis/v1` or `research-topic-extraction/v1` in both `llm_calls` and
the derived record; prompt strings do not live in routes or workflow code.

## Background processing

Celery over Redis, chosen per the project default. Interfaces should stay
narrow enough that the queue implementation can be replaced (e.g. by Temporal)
if durable workflow semantics are ever genuinely needed.

## Testing

- **Unit** (`tests/unit/`) — no containers required; runs on every commit via
  pre-commit.
- **Integration** (`tests/integration/`) — needs Postgres and Redis.

Two properties are enforced by the integration harness and are easy to break
accidentally:

- **Tests never touch the dev database.** A session fixture retargets the engine
  at `TEST_DATABASE_URL` and aborts the run outright if it matches
  `DATABASE_URL`.
- **Tests cannot leak state.** `db_session` binds to an outer connection-level
  transaction with `join_transaction_mode="create_savepoint"`, so even a test
  that calls `commit()` is rolled back. `test_db_isolation.py` guards this.

A third property is enforced by an autouse fixture: the async engine is disposed
after every test, because asyncpg binds connections to the event loop that
opened them while pytest-asyncio gives each test a fresh loop.
`test_db_event_loop_isolation.py` guards this.

`test_migration.py` runs Alembic's `compare_metadata` against the live database
and fails if models and migrations have drifted — the main defence against
hand-written migrations falling out of sync.

## Local stack

`docker compose up` starts postgres (pgvector image), redis, api, worker, and
web. The api container runs `alembic upgrade head` before starting uvicorn, so
the stack comes up migrated with no manual step.

## Deliberately deferred

Recorded so they are decisions rather than oversights:

- **Real LLM providers** — the protocol and a complete mock-backed workflow
  exist; credentialed providers remain deferred until their quality is needed
  and budget/error behavior can be tested safely.
- **CI pipeline** — checks run locally via pre-commit. Add when the repo has a
  remote.
- **Auth / multi-tenancy** — single-user local tool for now.
- **Platform integrations** — see `docs/platform-capabilities.md`. Nothing is
  implemented against LinkedIn, X, or job boards until capabilities are verified
  against official documentation.
