# M3: Content Engine — Design

Date: 2026-08-11
Status: Implemented

## Purpose

Turn an M2 topic and evidence pack into inspectable, editable LinkedIn and X
drafts. M3 stops at approval: it does not connect an account, publish content,
or imply that approval caused an external side effect.

The workflow must preserve its intermediate reasoning artifacts. A single
opaque prompt cannot replace angle selection, outline, drafting, voice
transformation, fact checking, quality evaluation, rewrite, and platform
adaptation.

## Success criteria

- A workflow can only start from an existing topic with an evidence pack.
- The selected angle is one of technical, product, business, career,
  contrarian, tutorial, breakdown, prediction, case study, comparison, or
  framework.
- Every stage is persisted as a versioned artifact and model-backed artifacts
  retain prompt, model, and request `run_id` provenance.
- Generated factual statements reference M2 claims. The deterministic fact
  checker rejects missing, foreign, unverified, disputed, or unsupported
  claim references before platform adaptation.
- The AI-slop detector stores explainable deterministic and model sub-scores.
- `LinkedInContentAdapter` and `XContentAdapter` are separate implementations;
  the X output is a native post/thread structure, not sliced LinkedIn text.
- Every requested platform receives a pending approval record at the user's
  configured level. Approval changes local workflow state only.
- The `/content` page can create, run, inspect, manually revise, approve, and
  reject workflows.
- Unit, integration, migration-drift, lint, type, and web-build checks pass.

## Boundaries

- No social platform API, browser automation, account connection, scheduling,
  or publishing is introduced. Those remain behind the M7 capability gate.
- No unbounded agent loop is introduced. One explicit request runs a finite,
  ordered pipeline.
- A model cannot promote its own statement to verified evidence. Grounding is
  checked against persisted M2 claims and sources.
- MockLLM remains the local default. Deterministic fallbacks keep the complete
  workflow testable and reviewable without credentials.
- M4 owns semantic duplicate detection against previously published content.

## Workflow and stages

`ContentWorkflow` owns one attempt for a topic/evidence-pack pair. Multiple
attempts are allowed so angle and platform experiments remain independent. It
stores the selected angle type, requested platforms, current stage, status,
and the run that most recently generated it.

The ordered artifact stages are:

1. `angle`
2. `outline`
3. `draft`
4. `voice_transform`
5. `fact_check`
6. `quality_evaluation`
7. `rewrite`
8. `linkedin_adaptation` and/or `x_adaptation`

`ContentArtifact` stores stage, revision, text, structured metadata,
prompt/model/run provenance, and creation time. Re-running or manually editing
a stage appends a revision; it never silently overwrites the earlier result.

`ContentClaimReference` maps an exact factual statement in an artifact to an
M2 `Claim`. This relation is the grounding boundary used by fact checking.

## Generation contract

Model stages return a common structured shape: content, factual statements
with claim UUIDs, and concise notes. Each prompt receives only the context
required for that stage. Evidence context includes claim statements,
verification status, and supporting excerpts; voice context comes from the M1
voice profile when one exists.

If the credential-free mock returns no useful content, a deterministic
evidence-first fallback produces a reviewable artifact from the topic thesis
and supported claims. This fallback is deliberately conservative and never
invents facts.

All model calls in one pipeline request share the request `run_id`, are logged
to `llm_calls`, and are stopped before execution when the daily budget is
already exhausted.

## Fact checking

The fact checker is deterministic. It runs after the voice transform, then
revalidates rewrites, platform adaptations, and manual platform edits so a
later stage cannot reintroduce an unsupported fact. For every referenced
generated statement it verifies that:

- the claim exists in the workflow's evidence pack;
- its status is `supported`; and
- it has at least one supporting evidence source.

Each persisted fact-check revision names the exact artifact it checked and
lists every finding and its reason. A failed check leaves the workflow in
`fact_check_failed` and prevents all later stages or approval. Approval also
rechecks the latest platform revision as defense in depth. A later explicit run
can create new revisions after evidence or prompts are corrected.

## Quality evaluation

Deterministic checks score specificity, lexical diversity, sentence rhythm,
formatting restraint, and cliché avoidance. Each sub-score is in `[0, 1]` and
has an explanation. A versioned model judgement adds authenticity, clarity,
and usefulness sub-scores. The persisted overall score combines the two while
keeping both inputs visible; it is guidance, not a claim of objective quality.

The rewrite stage always receives the quality explanations, making the
evaluation actionable and preserving the explicit roadmap stage.

## Platform adapters

`LinkedInContentAdapter` targets a readable hook, short paragraphs, grounded
body, and restrained closing. `XContentAdapter` targets a concise standalone
post or numbered thread. They own different prompts and deterministic
fallbacks and do not call external services.

## Approval policy

`AutomationPolicy.evaluate()` treats a public-facing action as disallowed
until an explicit approval exists. M3 creates one `ContentApproval` per
requested platform using `UserSettings.public_action_approval_level` (Level 1
by default). Approval and rejection store actor, reason, decision time, and
request `run_id`.

An approved workflow means "locally approved for a possible future action."
It never means published.

## API

- `GET|POST /api/content/workflows`
- `GET /api/content/workflows/{workflow_id}`
- `POST /api/content/workflows/{workflow_id}/run`
- `PUT /api/content/workflows/{workflow_id}/artifacts/{stage}`
- `POST /api/content/workflows/{workflow_id}/approval`

The manual artifact endpoint appends an inspectable revision and exists so a
useful human-edited draft never depends on a configured model provider.

## Testing

- Unit tests cover angle/platform validation, fact-check invariants, quality
  sub-scores, native adapter behavior, and policy decisions.
- Integration tests cover migration/model parity, workflow generation with
  prompt/run usage logging, failed grounding, manual revisions, and approval
  state without external effects.
- Tests use local evidence fixtures and MockLLM; no network or platform account
  is required.
