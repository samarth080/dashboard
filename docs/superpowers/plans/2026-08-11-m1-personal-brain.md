# M1 Personal Brain Implementation Plan

**Status:** Complete and verified on 2026-08-11.

**Goal:** Add the editable personal context that later engines consume, with a
versioned and cost-logged voice-analysis workflow.

**Design:** `docs/superpowers/specs/2026-08-11-m1-personal-brain-design.md`

## Tasks

- [x] Add M1 ORM models and migration `0002_personal_brain`.
- [x] Add validated Pydantic request/response schemas.
- [x] Add profile, career, interest, settings, and writing-sample services.
- [x] Add a prompt registry and `prompts/voice-analysis/v1.md`.
- [x] Add `VoiceAnalyzer` behind the existing `LLMClient` protocol.
- [x] Add profile/settings/interest/voice API routes and LLM dependency wiring.
- [x] Replace the Settings placeholder with a usable Personal Brain editor.
- [x] Add unit tests for validation, prompt loading, and voice analysis.
- [x] Add integration tests for persistence, hierarchy safeguards, API flows,
  voice usage logging, and migration drift.
- [x] Run Ruff, format check, Pyright, unit/integration tests, and Next.js build.
- [x] Update `ROADMAP.md`, `ARCHITECTURE.md`, and `HANDOVER.md` to match reality.

Verification result: 27 unit tests and 15 integration tests passed; Ruff,
Ruff format, Pyright, the Next.js production build, model/migration drift, and a
fresh `0001` → `0002` migration also passed.

## Acceptance notes

- Tests must use `MockLLM`; credentials are not an M1 prerequisite.
- Interest domains remain user-configurable. Seed data may be offered later,
  but the schema and scoring logic must not assume AI or any other niche.
- Only confirmed user-provided samples may enter voice analysis.
- M1 is complete only when migration drift is empty against a live Postgres.
