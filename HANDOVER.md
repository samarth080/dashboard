# Handover

Last updated: 2026-08-11 (Asia/Kolkata)

## Current branch

`m0-foundation`

## Checkpoint state

M0, M1, and M2 are complete and included in repository history. Run
`git log -1 --oneline` for the exact current checkpoint revision.

## Milestone status

- M0 — Repository Foundation: complete
- M1 — Personal Brain: complete
- M2 — Research Engine: complete
- Next: M3 — Content Engine (not started)

## Latest local runtime check

The development database was migrated through `0003`. The API and web app were
also smoke-tested locally during M1:

- `GET http://localhost:8000/api/health` returned `200` with `status: ok` and a
  request `run_id`.
- `GET http://localhost:3000/settings` returned `200` and compiled the Personal
  Brain editor successfully.
- The production Next.js build passed again immediately before the M1/M2
  checkpoint.

The API and web development processes are not currently running. OrbStack was
restarted during M2 verification; the isolated `m0-test-pg` and
`m0-test-redis` containers currently provide Postgres on `5432` and Redis on
`6379`. Use the commands below before opening the UI URLs again.

## What exists

- Top-level `README.md` with quick start, first-use flow, verification commands,
  and the documentation index.
- Shared Python foundation: cached settings, JSON logs with scoped `run_id`,
  async SQLAlchemy sessions, Alembic, and cost-linked LLM protocol/persistence.
- FastAPI health, profile, career, interests, user settings, writing samples,
  and voice-analysis routes.
- Personal Brain models for the primary profile, career, user settings, weighted
  interest hierarchy, seven-domain memory, confirmed writing samples, and the
  derived voice profile.
- Versioned prompt registry and `prompts/voice-analysis/v1.md`.
- Research source/document/topic/evidence models, `ContentSource`, safe RSS/Atom
  retrieval, URL/content/near-duplicate handling, and optional embeddings.
- Versioned `research-topic-extraction/v1` workflow with document-ID validation,
  deterministic cluster collapsing, request-linked LLM usage, and daily-budget
  enforcement.
- Database-versioned Decimal scoring weights and thresholds; the scorer has no
  hard-coded product weights.
- Evidence packs where supported claims require source excerpts from documents
  already linked to the topic.
- Functional `/research` UI for sources, manual ingestion, ranking, extraction,
  topic inspection, and evidence entry.
- Deterministic `MockLLM`, still the development/test default; no credentials
  are required.
- Daily LLM budget check and a 100,000-character per-analysis input limit.
- Next.js nav shell and a functional `/settings` Personal Brain editor.
- Celery/Redis worker with the M0 `ping` task.

## Database

Migrations:

- `0001_initial`: `runs`, `llm_calls`
- `0002_personal_brain`: `user_profiles`, `career_profiles`, `user_settings`,
  `interests`, `writing_samples`, `voice_profiles`, `memory_records`
- `0003_research_engine`: enables `vector`; adds `research_sources`,
  `raw_documents`, `scoring_configs`, `topic_candidates`, `topic_documents`,
  `evidence_packs`, `claims`, and `evidence_sources`

The integration suite applies migrations to `TEST_DATABASE_URL`, refuses to use
the dev URL, isolates commits with an outer transaction, disposes the async
engine between event loops, and compares live schema metadata for drift.

## API routes

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

## Verification

- Ruff lint and format check: passing
- Pyright: passing with zero errors
- Unit tests: 43 passing
- Integration tests: 20 passing against Postgres and Redis
- Next.js production build: passing
- Alembic/model drift: empty
- Fresh migration through `0003`: passing
- pgvector extension and vector round-trip: passing

Integration tests require reachable Postgres databases named by `DATABASE_URL`
and `TEST_DATABASE_URL`, plus Redis for the worker round-trip test.

## Platform capabilities

None verified. M7 remains blocked. The rules and empty verification matrix live
in `docs/platform-capabilities.md`; do not implement LinkedIn, X, or other
platform side effects without current official documentation in that ledger.

## Known limitations

- Single-user and unauthenticated by design.
- `MockLLM` produces structurally valid but not meaningful analysis unless a
  canned response is injected; by default automated extraction recommends no
  topics. Manual document/topic/evidence workflows remain usable.
- pgvector is enabled and embeddings can be stored, but no real embedding
  provider or similarity index is configured yet.
- Memory has explicit storage boundaries but no autonomous ingestion or recall
  workflow.
- No CI pipeline; checks run locally and through pre-commit.

## How to run

### Full stack

```bash
cp .env.example .env
uv sync
docker compose up --build
```

Then open:

- Dashboard: `http://localhost:3000`
- Personal Brain: `http://localhost:3000/settings`
- Research workspace: `http://localhost:3000/research`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

### Run API and web separately

Start Postgres and Redis, apply migrations, then keep the API running in one
terminal:

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep the web app running in a second terminal:

```bash
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

If ports `5432` or `6379` are already owned by older `m0-test-pg` or
`m0-test-redis` containers, reuse or stop those exact containers before starting
the Compose database services.

### Verification commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
cd apps/web && npm run build
```

## Next task

Design M3 as its own milestone before implementation. Preserve explicit
intermediate stages (angle, outline, draft, voice transform, fact check,
quality evaluation, rewrite, and platform adaptation), consume M2 evidence
packs, keep prompts versioned, and require Level 1 approval for public actions.
