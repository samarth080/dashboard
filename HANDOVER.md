# Handover

Last updated: 2026-08-13 (Asia/Kolkata)

## Current branch

`m0-foundation`, pushed to `origin` at
`https://github.com/samarth080/dashboard`. Local and remote were level at
`795a8f6` before this documentation commit.

The remote was added during the 2026-08-13 session. It holds no `main` branch —
`m0-foundation` is the only branch, and its name is a leftover from M0 even
though the branch now carries M0 through M4. Renaming it, or opening a PR into
a fresh `main`, is an open housekeeping decision.

Push with `git push origin m0-foundation` and paste a Personal Access Token as
the password when prompted. No credential is stored in `.git/config` or
`~/.git-credentials`, deliberately.

## Checkpoint state

M0, M1, and M2 are included in commit
`4aa5fc1 feat: complete personal brain and research engine`.

M3 and M4 are complete and committed on this branch. M4 ends at
`795a8f6 feat(content): expose a workflow's persisted duplicate verdicts over
HTTP`, which is the last of five fixes applied after a final holistic review of
the milestone — see "Defects found after M4 was first called complete" below.

## Milestone status

- M0 — Repository Foundation: complete
- M1 — Personal Brain: complete
- M2 — Research Engine: complete
- M3 — Content Engine: complete
- M4 — Content Memory: complete
- Next: M5 — Job Engine (not started)

**M4 publishes nothing.** It records post history and refuses to approve a
near-duplicate without a written override. No platform API, scheduler, or
autonomous loop was introduced.

## Latest local runtime check

The development database is migrated through `0005`. Checks performed for this
handover, against a freshly started API process:

- `GET /api/health` returned `200` with `status: ok` and a request `run_id`.
- `GET /openapi.json` listed the M4 routes: `/api/memory/posts`,
  `/api/memory/posts/{post_id}`, `/api/memory/posts/{post_id}/metrics`,
  `/api/memory/duplicate-configs`, and `/api/memory/duplicate-check`.
- `GET /api/memory/duplicate-configs` returned `200` with the seeded `v1`
  policy: warn `0.700`, block `0.850`, cross-platform off, active.
- `GET /api/content/workflows` returned `200`.
- `GET http://localhost:3000/analytics` returned `200`.
- The production Next.js build passed and emitted 10 routes, including
  `/analytics` and `/content`.

The full pipeline was also driven end to end over HTTP: profile → document →
ranked topic → evidence pack → workflow → all ten stages → approval. A second
workflow on the same topic produced an identical draft, was refused with `409`
at similarity `1.00`, rejected a reasonless override with `422`, and was then
approved with a written reason that persisted. Three `duplicate_checks` rows
survived, including the blocked one.

A long-lived API process started before a code change will serve the old
routes. Restart it after pulling — an API predating M4 404s on `/api/memory/*`,
and one predating `795a8f6` 404s on the duplicate-checks route.

### Demo data currently in the dev database

Left in place deliberately so the UI is not empty: two `manual` /
`published_externally` post records with mock metric snapshots, one
`workflow`-origin `approved_unpublished` record whose approval is live, plus
the research document, topic, evidence pack, and two content workflows from the
walkthrough. Safe to delete; nothing depends on it.

The isolated `m0-test-pg` and `m0-test-redis` containers provide Postgres on
`5432` and Redis on `6379`. If the API/web terminal sessions stop, use the
commands below to restart them.

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
- Persisted content workflows for angle, outline, draft, voice transform,
  deterministic fact check, explainable quality evaluation, rewrite, separate
  LinkedIn/X adaptation, and local approval.
- Append-only content artifact revisions with M2 claim mappings and prompt,
  model, cost, and request-run provenance.
- Functional `/content` UI for workflow creation, stage/report inspection,
  manual revisions, and local approve/reject decisions, with a duplicate panel
  shown before approval.
- Content memory: `post_records` per platform from approved workflows or manual
  backfill, a pure similarity engine (`src/memory/similarity.py`), versioned
  warn/block policy, and persisted explainable `duplicate_checks`.
- An `EmbeddingProvider` protocol beside `LLMClient`, with a deterministic
  `MockEmbedder` whose usage is cost-logged through the same `llm_calls` path.
- A duplicate gate at the single M3 seam, `decide_approval`: a `block` verdict
  returns `409` unless the request carries `duplicate_override` and a non-empty
  reason, which is persisted. The blocked check row is committed before the
  `409` so the refusal stays inspectable, and readable afterwards at
  `GET /api/content/workflows/{workflow_id}/duplicate-checks`. Every path that
  revokes a platform approval — rejection, a re-run, a manual edit of the
  platform adaptation — withdraws the workflow-origin post record that a
  previous approval created, so a record exists exactly while the approval
  does. Manual records, the duplicate-check trail, and rows the user has marked
  `published_externally` are never touched.
- `MockAnalyticsProvider` and append-only `post_metric_snapshots`, captured only
  when the user asks. There is no scheduler.
- Functional `/analytics` UI for post history, manual backfill, and mock metric
  capture.
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
- `0004_content_engine`: adds `content_workflows`, `content_artifacts`,
  `content_claim_references`, and `content_approvals`
- `0005_content_memory`: adds `post_records`, `post_metric_snapshots`,
  `duplicate_configs`, and `duplicate_checks`, and seeds the active `v1`
  duplicate policy (warn `0.700`, block `0.850`)

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
- `GET|POST /api/content/workflows`
- `GET /api/content/workflows/{workflow_id}`
- `POST /api/content/workflows/{workflow_id}/run`
- `PUT /api/content/workflows/{workflow_id}/artifacts/{stage}`
- `POST /api/content/workflows/{workflow_id}/approval`
- `GET|POST /api/memory/posts`
- `GET|PATCH|DELETE /api/memory/posts/{post_id}`
- `GET|POST /api/memory/posts/{post_id}/metrics`
- `GET|POST /api/memory/duplicate-configs`
- `POST /api/memory/duplicate-check` (optional `workflow_id` scopes the preview
  to the same corpus the approval gate will score)
- `GET /api/content/workflows/{workflow_id}/duplicate-checks`

## Verification

Counts are from the run made for this handover on 2026-08-13:

- `uv run ruff check .` — "All checks passed!"
- `uv run ruff format --check src services tests` — 93 files already formatted
- `uv run pyright` — 0 errors, 0 warnings, 0 informations
- `uv run pytest -q` — 154 passed in 10.78s
- Unit tests: 90 passing (`tests/unit`)
- Integration tests: 64 passing against Postgres and Redis (`tests/integration`)
- `npm --prefix apps/web run build` — compiled successfully, 12 static pages,
  10 app routes
- `uv run alembic downgrade base && uv run alembic upgrade head` — fresh
  migration from empty through `0005` passing
- `uv run pytest tests/integration/test_migration.py -v` — 3 passed;
  Alembic/model drift empty, pgvector extension enabled

Integration tests require reachable Postgres databases named by `DATABASE_URL`
and `TEST_DATABASE_URL`, plus Redis for the worker round-trip test.

## Defects found after M4 was first called complete

M4 was declared complete once, prematurely, before the final whole-milestone
review had run. That review found two blocking defects that twelve per-task
reviews had missed, because none of them could compare call sites across files.
Recorded here because the lesson generalises to M5.

1. **A post record could outlive the approval that created it.**
   `src/content/service.py` revoked a platform approval in three places but
   withdrew the recorded post in only one. Re-running a workflow or editing a
   platform draft left an orphan, which then blocked *other* workflows and
   forced a user to write an override justifying a duplicate of something never
   approved. The dev database was already carrying one. Fixed by routing all
   three sites through a single `_revoke_approval` helper that resets the
   approval and withdraws the record together, so they cannot drift apart.
2. **Withdrawal destroyed genuinely published records.**
   `remove_workflow_post` filtered on `origin` but not `status`. Once a user
   re-classified a workflow row to `published_externally` via `PATCH`, a later
   rejection deleted it and cascade-deleted its append-only metric snapshots.
   Fixed by also requiring `status == "approved_unpublished"`.

Three follow-ups landed in the same pass: the duplicate preview and the
approval gate scored different corpora, so the panel could show `block` where
the server returned `clear` and silently discard the typed override reason;
`lookback_days` filtered on `created_at`, so backfilled old posts never aged
out, now `COALESCE(posted_at, created_at)`; and persisted verdicts had no HTTP
route despite the docs claiming they stayed inspectable.

**Budget a holistic review at the end of M5, not only per-task reviews.** The
two most serious problems in M4 — collision inflation in `MockEmbedder` and
these orphaned records — were both invisible from inside any single file.

## Open decisions

- **A failed fact check leaves an approval untouched.** In
  `put_manual_artifact`, an edit that fails fact checking returns early without
  resetting approvals, so a previously approved platform keeps its `approved`
  decision and its post record while the latest adaptation is unapproved text.
  The stated invariant still holds — the approval genuinely is `approved` — and
  changing it would alter M3 behaviour that `tests/integration/test_content_api.py`
  asserts. Wants a deliberate decision rather than a drive-by fix.
- **Branch naming.** `m0-foundation` now carries M0 through M4. Rename, or open
  a PR into a fresh `main`.
- **`create_duplicate_config` relies on SQLAlchemy flush ordering** to
  deactivate the previous active row before inserting the new one, which works
  only because UPDATEs are emitted before INSERTs for a table. M2's
  `create_scoring_config` uses an explicit `update(...).values(active=False)`
  that does not depend on unit-of-work ordering. Tested and correct today; one
  line from being robust to a change in flush order.

## Platform capabilities

None verified. M7 remains blocked. The rules and empty verification matrix live
in `docs/platform-capabilities.md`; do not implement LinkedIn, X, or other
platform side effects without current official documentation in that ledger.

## Known limitations

- Single-user and unauthenticated by design.
- `MockLLM` produces structurally valid but not meaningful analysis unless a
  canned response is injected; by default automated extraction recommends no
  topics. Content generation uses conservative evidence-only fallbacks locally,
  but high-quality voice transformation still needs a real model or manual edit.
- `MockEmbedder` hashes tokens into 1024 buckets, so semantic duplicate
  detection fails in both directions until a real embedding provider is
  configured. A reworded post sharing no words with the original will not be
  caught, and collisions inflate similarity between unrelated long texts.
  Do not calibrate duplicate thresholds against it.
- Analytics figures are invented by `MockAnalyticsProvider` and tagged
  `is_mock`. No real platform metrics exist.
- pgvector is enabled and embeddings are stored with their provider model, but
  vectors are dimension-unconstrained and unindexed: duplicate candidates are
  prefiltered in SQL and scored in Python.
- Post history records local approvals and manual backfill only. Nothing is
  published, and `approved_unpublished` is a claim about a live local approval,
  not about a platform. That claim is now enforced: every path that revokes an
  approval withdraws the record, so one exists exactly while its approval does.
- `lookback_days` ages history out by `COALESCE(posted_at, created_at)`, so
  manual backfill is judged by when it was posted rather than when it was
  typed in. It is unset by default, meaning the whole corpus is scored on every
  approval. There is no `LIMIT` on candidate selection; fine at single-user
  scale, unbounded in principle.
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
- Content studio: `http://localhost:3000/content`
- Post history and metrics: `http://localhost:3000/analytics`
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
npm --prefix apps/web run build
uv run alembic downgrade base && uv run alembic upgrade head
uv run pytest tests/integration/test_migration.py -v
```

## Next task

Design M5 Job Engine before implementation: at least two legitimate job-source
adapters behind a `JobSource` protocol, raw payloads stored unmutated alongside
a normalized representation, cross-source deduplication by requisition ID,
canonical URL, company/title/location, description fingerprint, and embedding
similarity, an explainable `JobFitEvaluator` returning matches, gaps, and a
decision, and an application CRM from DISCOVERED through OFFER/REJECTED. No
auto-submission of applications. See `docs/platform-capabilities.md` before
touching any external source.
