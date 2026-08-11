# Personal Career + Content + Network Intelligence Engine

A local-first system for building an editable personal context and, over later
milestones, using it to support research, content, career, and relationship
workflows without unsafe automation.

## Current status

- **M0 — Repository Foundation:** complete
- **M1 — Personal Brain:** complete
- **M2 — Research Engine:** complete
- **M3 — Content Engine:** complete in the current working tree
- **Next:** M4 — Content Memory
- **External integrations:** blocked until capabilities are verified against
  current official documentation

M1 provides a primary profile, career direction, user preferences, a weighted
interest hierarchy, seven explicit memory domains, confirmed writing samples,
and versioned voice analysis. M2 adds safe RSS/Atom ingestion, document
normalization and deduplication, structured topic extraction and clustering,
configurable ranking, pgvector storage, and evidence packs. M3 adds a persisted
evidence-to-draft pipeline, deterministic fact checking, explainable quality
evaluation, separate LinkedIn/X adaptations, append-only manual revisions, and
local approval. The working product surfaces are `/settings`, `/research`, and
`/content`.

## Quick start

Prerequisites: Docker, Python 3.12+, `uv`, and Node.js 20+.

```bash
cp .env.example .env
uv sync
docker compose up --build
```

Open:

- Dashboard: `http://localhost:3000`
- Personal Brain: `http://localhost:3000/settings`
- Research workspace: `http://localhost:3000/research`
- Content studio: `http://localhost:3000/content`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

The API container applies Alembic migrations before starting. Development uses
`MockLLM`, so no provider credentials are required. Content stages use
conservative evidence-first fallbacks when the mock returns no copy; those
fallbacks exercise the workflow but are not a substitute for a real model.

## First-use flow

1. Open `/settings` and save the Identity section.
2. Add career targets and product preferences.
3. Create weighted interests, optionally assigning parent interests.
4. Add writing samples only after confirming they were explicitly provided for
   analysis.
5. Run voice analysis. The workflow uses the versioned
   `voice-analysis/v1` prompt and logs usage against the request `run_id`.
6. Open `/research`, register a public RSS/Atom feed or ingest a document, then
   create or extract ranked topics and attach evidence excerpts.
7. Open `/content`, create a workflow from a topic with supported evidence,
   inspect every generated stage, revise the platform drafts, and record local
   approval. Approval does not publish anything.

Public posting, messaging, scraping, job applications, and platform account
connections are not implemented.

## Run services separately

With Postgres and Redis running:

```bash
uv run alembic upgrade head
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
cd apps/web && npm run build
```

Integration tests require distinct `DATABASE_URL` and `TEST_DATABASE_URL`
databases plus Redis. The test harness refuses to run against the development
database and rolls back test writes, including explicit commits.

## Documentation

- [`ROADMAP.md`](ROADMAP.md) — milestone sequence, status, and guardrails
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current implementation and boundaries
- [`HANDOVER.md`](HANDOVER.md) — exact working-tree state and operational notes
- [`docs/platform-capabilities.md`](docs/platform-capabilities.md) — external
  integration verification gate
- [`docs/superpowers/specs/2026-08-11-m1-personal-brain-design.md`](docs/superpowers/specs/2026-08-11-m1-personal-brain-design.md)
  — implemented M1 design
- [`docs/superpowers/plans/2026-08-11-m1-personal-brain.md`](docs/superpowers/plans/2026-08-11-m1-personal-brain.md)
  — completed M1 implementation checklist
- [`docs/superpowers/specs/2026-08-11-m2-research-engine-design.md`](docs/superpowers/specs/2026-08-11-m2-research-engine-design.md)
  — implemented M2 design
- [`docs/superpowers/plans/2026-08-11-m2-research-engine.md`](docs/superpowers/plans/2026-08-11-m2-research-engine.md)
  — completed M2 implementation checklist
- [`docs/superpowers/specs/2026-08-11-m3-content-engine-design.md`](docs/superpowers/specs/2026-08-11-m3-content-engine-design.md)
  — implemented M3 design
- [`docs/superpowers/plans/2026-08-11-m3-content-engine.md`](docs/superpowers/plans/2026-08-11-m3-content-engine.md)
  — completed M3 implementation checklist
- [`docs/superpowers/specs/2026-08-12-m4-content-memory-design.md`](docs/superpowers/specs/2026-08-12-m4-content-memory-design.md)
  — approved M4 design, not yet implemented

The M0 design and plan under `docs/superpowers/` are historical records. The
roadmap, architecture, and handover are authoritative for current behavior.
