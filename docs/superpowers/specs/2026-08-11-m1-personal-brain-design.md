# M1: Personal Brain — Design

Date: 2026-08-11
Status: Implemented

## Purpose

Give the single-user engine an explicit, editable source of truth about the
person it serves. M1 adds profile, career, interests, preferences, bounded
memory, and a voice profile derived only from writing samples the user
deliberately supplies.

M1 does not publish, scrape, message, recommend jobs, or ingest external
sources. It makes later research, content, job, and network decisions
configurable instead of embedding assumptions in prompts or code.

## Success criteria

- A primary user profile and career profile can be created and edited through
  the API.
- Interests are weighted, enabled/disabled, and may form a validated hierarchy.
- User settings are distinct from process/environment configuration.
- Memory records use one of seven explicit domains: Personal, Voice, Content,
  Research, Relationship, Career, and Performance.
- Writing samples require an affirmative user-provided confirmation before
  storage.
- Voice analysis uses a versioned prompt, returns structured attributes, stores
  the prompt version, and logs usage against the HTTP request run.
- The Settings UI edits the profile, career targets, settings, interests, and
  writing samples and can trigger voice analysis.
- Models and migration stay in sync; unit, integration, lint, type, and web
  build checks pass.

## Data model

`UserProfile` is keyed by a unique `profile_key`. M1 uses `primary`, making the
single-user assumption explicit without baking a particular person's identity
into the schema.

`CareerProfile` and `UserSettings` are one-to-one with `UserProfile`.
`VoiceProfile` is also one-to-one and contains derived attributes, the sample
count, analysis confidence, analysis time, and prompt version.

`Interest` belongs to a profile and optionally points to a parent interest.
Names are preserved for display while a normalized name prevents duplicate
case variants. Weights are decimals between zero and one. The service rejects
cross-profile parents and hierarchy cycles.

`WritingSample` stores only text explicitly confirmed as user-provided, plus a
consent timestamp and optional label. Deleting a sample does not silently
rewrite a prior voice analysis; the next analysis records the new sample count.

`MemoryRecord` is the base persistence primitive for later milestones. A
domain, stable key, JSON value, provenance string, confidence, and enabled flag
keep memory inspectable and reversible. Domain-specific behavior belongs in
the owning milestone; M1 does not create a generic autonomous memory loop.

All identifiers are UUIDs. Timestamps are timezone-aware and have database
defaults. Money and bounded scores use `Decimal`/`NUMERIC`, never floats in the
database.

## API

- `GET|PUT /api/profile`
- `GET|PUT /api/profile/career`
- `GET|POST /api/interests`
- `PATCH|DELETE /api/interests/{interest_id}`
- `GET|PUT /api/settings`
- `GET /api/voice`
- `GET|POST /api/voice/samples`
- `DELETE /api/voice/samples/{sample_id}`
- `POST /api/voice/analyze`

The API returns `404` when profile-dependent operations are attempted before a
primary profile exists. Mutating endpoints own their transaction and return
the persisted representation.

## Voice analysis

The prompt lives at `prompts/voice-analysis/v1.md`; no prompt text lives in a
route or service. `VoiceAnalyzer` accepts the `LLMClient` protocol so tests and
development use `MockLLM`, while a later provider can be substituted without
changing the workflow.

Analysis creates a `Run` whose UUID is the request's `run_id`, logs the
structured call in `llm_calls`, and updates `VoiceProfile` in one transaction.
The source samples remain available so every derived profile is explainable.
Before calling the client, the workflow enforces the user's daily LLM budget
and a 100,000-character combined sample limit.

## Boundaries

- No auth or multi-tenancy; those remain explicitly deferred.
- No inference from scraped posts, private accounts, or third-party data.
- No real LLM provider is required for M1 acceptance.
- No embeddings or pgvector extension; semantic memory starts in a later
  milestone.
- No public side effects, so policy approval is not invoked in M1.
