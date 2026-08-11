# M3 Content Engine Implementation Plan

**Status:** Complete and verified on 2026-08-11.

**Goal:** Build an evidence-grounded, inspectable content pipeline that ends in
separate LinkedIn/X drafts and explicit local approval.

**Design:** `docs/superpowers/specs/2026-08-11-m3-content-engine-design.md`

## Tasks

- [x] Add M3 ORM models and migration `0004_content_engine`.
- [x] Add content request/response and structured generation schemas.
- [x] Add versioned prompts for every model-backed stage.
- [x] Add deterministic fact checking and explainable AI-slop scoring.
- [x] Add separate LinkedIn and X content adapters.
- [x] Add a finite, transaction-neutral workflow service with cost logging.
- [x] Add workflow, artifact revision, and approval APIs.
- [x] Replace the Content placeholder with the staged workflow UI.
- [x] Add unit and integration coverage, including migration/model drift.
- [x] Run the complete Python and web verification suites.
- [x] Update `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, and `HANDOVER.md`.

Verification result: 52 unit tests and 22 integration tests passed; Ruff,
Ruff format, Pyright, model/migration drift, a fresh empty-database migration
through `0004`, and the Next.js production build also passed.

## Acceptance constraints

- No external publishing or account integration.
- No unsupported factual claim advances beyond fact checking.
- No model prompt lives in Python or route code.
- Every model call stores prompt/model/cost/run provenance.
- Stage reruns and manual edits append revisions.
- LinkedIn and X adaptations are independently generated.
- Approval records are explicit and never imply publication.
