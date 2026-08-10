# M0: Repository Foundation — Design

Date: 2026-08-11
Status: Approved

## Purpose

Establish the monorepo skeleton for the Personal Career + Content + Network
Intelligence Engine. This milestone delivers no domain logic (profile,
content, jobs, network, etc.) — those arrive in M1+. M0's job is to produce a
working, testable, observable foundation that later milestones build on
without rework.

## Success criteria

- `docker compose up` brings up postgres (pgvector), redis, api, worker, and
  web, and they can talk to each other.
- `alembic upgrade head` applies cleanly against a fresh database.
- `GET /api/health` returns 200, confirms DB connectivity, and includes a
  run_id.
- The Next.js app boots, renders a nav shell with placeholder pages for every
  top-level section (Today/Content/Research/Network/Jobs/Applications/
  Analytics/Automations/Settings), and one page calls `/api/health` and
  displays the result.
- A Celery `ping` task round-trips through Redis and is covered by an
  integration test.
- `MockLLM` implements the `LLMClient` protocol and is covered by a unit
  test; a call through it is persisted to `llm_calls` linked to a `runs` row.
- `ruff`, `pyright`, and `pytest` all pass; `pre-commit` runs them on commit.

## Out of scope

- Any domain table beyond `runs` and `llm_calls`.
- Any API route beyond `/api/health`.
- Real LLM provider clients (OpenAI/Anthropic) — added when a later
  milestone has an actual caller.
- Any content/job/network/CRM code.
- CI pipeline. Checks (`ruff`, `pyright`, `pytest`) run locally via
  `pre-commit`; wiring them to a hosted runner is deferred until the repo
  has a remote.

## Repository layout

```
apps/web/                  # Next.js skeleton: nav shell, health-check page
services/api/               # FastAPI app entrypoint, routing, DI wiring
services/worker/            # Celery worker entrypoint
src/
  core/                      # settings, logging, run-id context
  llm/                       # LLMClient Protocol, MockLLM, call logging
  db/                        # SQLAlchemy 2 engine/session, Base
tests/
  unit/ integration/
alembic/
docs/
docker-compose.yml
pyproject.toml (single non-packaged uv project)
```

## Components

### `core.settings`
`pydantic-settings` `Settings` object reading from `.env`. Single source of
truth for DB URL, Redis URL, LLM provider keys (absent/optional in
mock-only mode), and feature flags. `.env.example` ships with placeholders
only.

### `core.logging`
Structured JSON logging. A `run_id` contextvar is generated per request/task
and injected into every log line via middleware (API) and a Celery signal
(worker).

### `db`
SQLAlchemy 2 async engine + session factory, declarative `Base`. Alembic
configured against it. First migration creates:

- `runs` — `id`, `run_id` (uuid), `created_at`. Cross-cutting table that
  every later milestone's audit/tracking tables will FK into, per the
  project's audit-logging requirement.
- `llm_calls` — `id`, `run_id` (FK → runs), `model`, `prompt_version`,
  `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`, `created_at`.

### `llm`
`LLMClient` Protocol with `generate(...)` and `structured(...)` methods,
both returning an `LLMResult` carrying the text plus its own usage metadata
(model, prompt_version, tokens, latency, cost). `MockLLM` implements the
protocol with deterministic, templated output and no network calls,
reporting `cost_usd=0`.

Persistence is a separate concern: a `log_llm_call(session, run, result)`
helper writes an `LLMResult` to `llm_calls`. Clients do not own a DB
session — they produce results, callers decide whether to persist them.
Together these prove the abstraction and the cost-tracking pipeline work
before any real provider is wired up.

### `services/api`
FastAPI app. One real route: `GET /api/health` — checks DB connectivity via
a trivial query, returns `{status, run_id}`. CORS configured to allow
`apps/web`'s origin.

### `services/worker`
Celery app wired to Redis as broker + backend. One demo task, `ping`,
returning `"pong"` — proves worker↔broker↔backend connectivity end-to-end.

### `apps/web`
Next.js + TypeScript. Nav shell with the following routes, each a
"coming soon" placeholder: Today, Content, Research, Network, Jobs,
Applications, Analytics, Automations, Settings. The Today page additionally
calls `/api/health` client-side and renders the response, proving the
frontend↔backend wire.

### Docker Compose
Services: `postgres` (pgvector-enabled image), `redis`, `api`, `worker`,
`web`. The `api` container runs `alembic upgrade head` before starting
uvicorn, so `docker compose up` yields a fully migrated, working stack with
no manual steps.

The Postgres image ships pgvector, but migration `0001` does not run
`CREATE EXTENSION vector` — M0 has no embedding columns. The extension gets
enabled by the migration that introduces the first vector column (M2 or
M4). Do not assume it is active before then.

### Tooling
A single non-packaged uv project (`[tool.uv] package = false`) at the repo
root manages all Python deps. `src/` and `services/` import as plain
packages via `uv run` from the root — no per-service manifests, no uv
workspace members, since nothing in this project is separately
distributable. `ruff` for lint, `pyright` for types, `pytest` for tests.
`pre-commit` runs ruff + pyright + a fast pytest subset on commit.

## Testing plan

**Unit**
- Settings load correctly from env / `.env.example` shape.
- `run_id` contextvar propagates into a log record.
- The Celery `task_prerun` handler sets a `run_id` before a task body runs.
- `MockLLM.generate` / `.structured` return well-formed output matching the
  protocol's expected shape.

**Integration**
- Alembic migration applies cleanly against a real (dockerized) Postgres.
- `GET /api/health` returns 200 with a passing DB check, against a real DB.
- Celery `ping` task round-trips through a real Redis instance.
- A `MockLLM` call persists a row to `llm_calls` correctly linked to a
  `runs` row.

**Explicitly not covered yet:** prompt regression, security/policy, and
reliability test categories — nothing exists at that layer until M1+.

## Risks / open questions

- None blocking. First real design decision with alternatives to weigh
  (task queue: Redis+Celery vs Temporal) is already resolved by the
  project's stated default (Redis+Celery unless durability strongly
  justifies Temporal — not the case yet).
