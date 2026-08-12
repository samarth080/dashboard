# Roadmap

Last updated: 2026-08-12

Milestones for the Personal Career + Content + Network Intelligence Engine.

Each milestone should leave the system working and testable. A milestone is not
complete until tests pass, lint and types pass, migrations apply, docs are
updated, and `HANDOVER.md` reflects reality.

## Status

| Milestone | Name | Status |
|---|---|---|
| M0 | Repository foundation | **Complete** |
| M1 | Personal Brain | **Complete** |
| M2 | Research Engine | **Complete** |
| M3 | Content Engine | **Complete** |
| M4 | Content Memory | **Complete** |
| M5 | Job Engine | Not started |
| M6 | Network CRM | Not started |
| M7 | Integrations | Blocked on capability verification |
| M8 | Orchestration | Not started |
| M9 | Learning | Not started |

---

## M0 — Repository foundation ✅

Architecture, database, FastAPI, migrations, test infrastructure,
configuration, Docker, observability, handover. No domain logic.

Delivered: single non-packaged uv project; `Settings`; structured JSON logging
with run_id propagation across HTTP and Celery; SQLAlchemy 2 async with lazy
engine; `runs` + `llm_calls` tables with an Alembic migration and a drift test;
`LLMClient` protocol with `MockLLM` and cost persistence; `GET /api/health`;
Celery `ping`; Next.js nav shell; Docker Compose stack; pre-commit running
ruff, ruff-format, pyright, and the unit suite.

## M1 — Personal Brain ✅

Profile, interest graph, voice profile, settings, memory base.

- `UserProfile`, `Interest` (weighted, hierarchical, enabled/disabled),
  `CareerProfile`, `VoiceProfile`
- Memory domains as separate concerns: Personal, Voice, Content, Research,
  Relationship, Career, Performance
- Settings and profile APIs; profile/settings UI
- Voice analysis from writing samples the user explicitly provides

Interest domains must stay configurable — AI, agents, software engineering,
product, startups, finance, fintech, consulting, strategy, marketing, growth,
careers. Nothing about the architecture may assume a single niche.

Delivered: editable primary and career profiles; separate user preferences;
weighted, hierarchical, enabled/disabled interests with duplicate and cycle
guards; explicit Personal/Voice/Content/Research/Relationship/Career/Performance
memory domains; confirmed user-provided writing samples; versioned structured
voice analysis with request-linked usage logging and daily budget enforcement;
profile/settings APIs; and a functional Personal Brain Settings UI.

Design and completed implementation checklist:

- `docs/superpowers/specs/2026-08-11-m1-personal-brain-design.md`
- `docs/superpowers/plans/2026-08-11-m1-personal-brain.md`

## M2 — Research Engine ✅

Design and completed implementation plan:

- `docs/superpowers/specs/2026-08-11-m2-research-engine-design.md`
- `docs/superpowers/plans/2026-08-11-m2-research-engine.md`

Source ingestion → normalization → topic extraction → clustering → ranking →
evidence packs.

- `ContentSource` protocol; RSS and public-source adapters first
- `RawDocument` with source, URL, published/retrieved timestamps, author,
  content hash, credibility metadata
- Deduplication by canonical URL plus content similarity
- `TopicCandidate` scoring — freshness, relevance, novelty, momentum,
  credibility, authority fit, insight potential, per-platform fit
- `EvidencePack` / `Claim` / `EvidenceSource`
- Topic APIs

Scoring weights live in configuration or the database, never hard-coded.
This is where the first embedding column arrives — that migration must
`CREATE EXTENSION vector`.

Delivered: `ContentSource` plus bounded public RSS/Atom retrieval; normalized
raw documents with canonical URLs, hashes, credibility, and metadata;
canonical/exact/near-duplicate handling; optional provider-neutral pgvector
embeddings; versioned structured topic extraction; deterministic cluster
collapsing; database-versioned Decimal ranking weights; topic APIs; evidence
packs with claim/excerpt/document provenance; and a functional Research UI.

## M3 — Content Engine

Design and completed implementation plan:

- `docs/superpowers/specs/2026-08-11-m3-content-engine-design.md`
- `docs/superpowers/plans/2026-08-11-m3-content-engine.md`

Topic → angles → outline → draft → voice transform → fact check → quality
evaluation → rewrite → platform adaptation → approval.

- Explicit stages with persisted intermediate outputs, not one large prompt
- Angle generator across technical, product, business, career, contrarian,
  tutorial, breakdown, prediction, case study, comparison, framework
- Voice engine: analyzer, profile builder, transformer, evaluator
- AI-slop detector combining deterministic checks and model judgement, with
  explainable sub-scores
- Separate `LinkedInContentAdapter` and `XContentAdapter` — X is not a
  truncated LinkedIn post
- `AutomationPolicy` with approval levels; default Level 1 for anything
  public-facing

Should produce genuinely usable drafts before any platform API is connected.

Delivered: persisted append-only artifacts for every explicit stage;
eleven selectable angle types; evidence-claim mappings; deterministic fact
checking that stops foreign or unsupported claims; explainable deterministic
and model quality sub-scores; quality-guided rewrite; separate LinkedIn and X
adapters and prompts; local Level 1-by-default approval records; manual stage
revisions; request-linked model usage; and a functional Content workspace. No
platform API or external side effect is present.

## M4 — Content Memory ✅

Design and completed implementation plan:

- `docs/superpowers/specs/2026-08-12-m4-content-memory-design.md`
- `docs/superpowers/plans/2026-08-12-m4-content-memory.md`

Post history, embeddings, semantic duplicate detection, analytics model, mock
analytics.

Never auto-publish something highly similar to an existing post; threshold
configurable.

Delivered: post history from approved workflows and manual backfill; an
`EmbeddingProvider` protocol with a deterministic `MockEmbedder` whose spend is
cost-logged through `llm_calls`; versioned warn/block duplicate policy with
explainable lexical and semantic sub-scores; an approval gate that refuses a
near-duplicate without a recorded override reason; append-only mock metric
snapshots; and post history and duplicate surfaces in the web app. Nothing is
published — no platform API, scheduler, or autonomous loop was introduced.

## M5 — Job Engine

At least two legitimate job-source adapters, normalization, deduplication, fit
scoring, APIs, dashboard.

- `JobSource` protocol; Greenhouse / Lever / Ashby are the likely first
  adapters — see `docs/platform-capabilities.md`
- Store raw payload *and* normalized representation; never mutate the raw
- Deduplicate across sources via requisition ID, canonical URL, company plus
  normalized title plus location, description fingerprint, embedding similarity
- `JobFitEvaluator` returning a score with an explanation — matches, gaps,
  decision
- Application CRM states from DISCOVERED through OFFER/REJECTED

No auto-submission of applications.

## M6 — Network CRM

People, organizations, relationships, interactions, recommendations, outreach
drafting.

- Canonical person entity; never silently merge on name alone
- Relevance scoring with a stored explanation
- Relationship lifecycle and interaction history
- Outreach drafts grounded strictly in real public or user-provided facts,
  scored for personalization, relevance, clarity, authenticity, spam risk
- Rate limits enforced by us regardless of what the platform permits

Never fabricate shared interests or experiences. No mass messaging.

## M7 — Integrations 🔒

**Blocked until capabilities are verified against official documentation.**
See `docs/platform-capabilities.md`.

Only functionality the current official APIs actually support. `MockSocialAdapter`
comes first so every workflow is testable without credentials, and remains the
default in development.

Never: CAPTCHA bypass, credential or session-cookie theft, prohibited scraping,
fake accounts, rate-limit circumvention, spam.

## M8 — Orchestration

Goal → Plan → Task → TaskRun → ToolCall → Result, with a UUID per run
(foreign-keyed to `runs`). Scheduled workflows, daily brief, centralized
approvals.

Workflows are explicit. No unbounded autonomous loops. The recommendation engine
must be able to conclude that no post is better than a low-quality post.

## M9 — Learning

Performance analysis, experiment tracking, recommendation improvement.

Do not train blindly on engagement — a viral post is not automatically a good
one. Track audience quality alongside reach, express uncertainty, and do not
claim causation from small samples.

---

## Cross-cutting requirements

These apply to every milestone, not just one:

- **Policy engine** — every external side effect passes
  `PolicyEngine.evaluate(action)` before execution
- **Audit logging** — user, run, action, timestamp, source, model, reason,
  confidence, approval, result, external reference
- **Never claim success without confirmation** from the external service
- **Cost controls** — response and embedding caching, research deduplication,
  cheap-first model routing, daily budgets, per-task limits
- **Prompt registry** — versioned prompt files; the version is stored with every
  model output. No prompt strings scattered through the codebase
- **Security** — OAuth where supported, encrypted tokens at rest, least-privilege
  scopes, no secrets in logs or git
