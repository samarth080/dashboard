# M2 Research Engine Implementation Plan

**Status:** Complete and verified on 2026-08-11.

**Goal:** Build a credential-free research pipeline from normalized public
documents to ranked topics and source-grounded evidence packs.

**Design:** `docs/superpowers/specs/2026-08-11-m2-research-engine-design.md`

## Tasks

- [x] Add the official `pgvector` Python integration.
- [x] Add M2 ORM models and migration `0003_research_engine`, enabling `vector`.
- [x] Add research request/response schemas and scoring-weight validation.
- [x] Add `ContentSource`, `SourceDocument`, and RSS/Atom parsing.
- [x] Add public-URL validation and bounded HTTP feed retrieval.
- [x] Add canonical URL, content hash, and token-similarity deduplication.
- [x] Add configurable, reproducible topic scoring.
- [x] Add evidence-pack persistence with supported-claim invariants.
- [x] Add source, document, scoring, topic, and evidence APIs.
- [x] Replace the Research placeholder with corpus/topic/evidence inspection UI.
- [x] Add unit and integration coverage, including pgvector extension checks.
- [x] Run the complete Python and web verification suites.
- [x] Update `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, and `HANDOVER.md`.

Verification result: 43 unit tests and 20 integration tests passed; Ruff,
Ruff format, Pyright, the Next.js production build, pgvector extension check,
model/migration drift, and a fresh `0001` → `0003` migration also passed.

## Acceptance constraints

- No live network call is required by tests.
- No source adapter persists directly.
- No ranking weight is hard-coded in scorer logic.
- Near-duplicate thresholds are stored in `ScoringConfig`.
- Claims and excerpts always retain raw-document provenance.
- M2 does not publish, message, apply, or connect platform accounts.
