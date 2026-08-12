"""Finite, transaction-neutral M3 content workflow operations."""

import uuid
from datetime import UTC, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.brain.models import VoiceProfile
from src.brain.service import get_user_settings, require_primary_profile
from src.content.adapters import LinkedInContentAdapter, XContentAdapter
from src.content.generation import ContentGenerator
from src.content.models import (
    CONTENT_STAGES,
    ContentApproval,
    ContentArtifact,
    ContentClaimReference,
    ContentWorkflow,
)
from src.content.policy import AutomationPolicy, PublicAction
from src.content.quality import evaluate_deterministic_quality
from src.content.schemas import (
    ApprovalDecisionInput,
    ContentWorkflowCreate,
    GeneratedClaim,
    GeneratedContent,
    ManualArtifactPut,
)
from src.db.models import LLMCall, Run, utcnow
from src.llm.embeddings import EmbeddingProvider
from src.llm.persistence import log_llm_call
from src.llm.protocol import LLMClient
from src.memory import service as memory_service
from src.research.models import Claim, EvidencePack, TopicCandidate


class ContentError(Exception):
    status_code = 400


class ContentNotFound(ContentError):
    status_code = 404


class ContentConflict(ContentError):
    status_code = 409


class ContentValidationError(ContentError):
    status_code = 422


class DuplicateBlocked(ContentConflict):
    """Approval refused because the draft repeats existing post history.

    A distinct subclass rather than a bare ContentConflict so the route can
    commit the duplicate check that was just recorded before the 409 unwinds
    the request. A refused approval is precisely the thing that must stay
    inspectable; discarding it would leave no trace of the refusal.
    """


def _workflow_options():
    return (
        selectinload(ContentWorkflow.artifacts).selectinload(ContentArtifact.claim_references),
        selectinload(ContentWorkflow.approvals),
    )


async def list_workflows(session: AsyncSession) -> list[ContentWorkflow]:
    return list(
        await session.scalars(
            select(ContentWorkflow)
            .options(*_workflow_options())
            .order_by(ContentWorkflow.created_at.desc(), ContentWorkflow.id)
        )
    )


async def require_workflow(session: AsyncSession, workflow_id: uuid.UUID) -> ContentWorkflow:
    workflow = await session.scalar(
        select(ContentWorkflow)
        .where(ContentWorkflow.id == workflow_id)
        .options(*_workflow_options())
    )
    if workflow is None:
        raise ContentNotFound("content workflow not found")
    return workflow


async def _require_evidence_pack(session: AsyncSession, pack_id: uuid.UUID) -> EvidencePack:
    pack = await session.scalar(
        select(EvidencePack)
        .where(EvidencePack.id == pack_id)
        .options(selectinload(EvidencePack.claims).selectinload(Claim.sources))
    )
    if pack is None:
        raise ContentNotFound("evidence pack not found")
    return pack


def _supported_claims(pack: EvidencePack) -> list[Claim]:
    return [
        claim
        for claim in pack.claims
        if claim.verification_status == "supported"
        and any(source.supports for source in claim.sources)
    ]


async def create_workflow(session: AsyncSession, data: ContentWorkflowCreate) -> ContentWorkflow:
    await require_primary_profile(session)
    topic = await session.get(TopicCandidate, data.topic_id)
    if topic is None:
        raise ContentNotFound("topic candidate not found")
    pack = await session.scalar(
        select(EvidencePack)
        .where(EvidencePack.topic_id == topic.id)
        .options(selectinload(EvidencePack.claims).selectinload(Claim.sources))
    )
    if pack is None:
        raise ContentValidationError("create an evidence pack before starting content")
    if not _supported_claims(pack):
        raise ContentValidationError(
            "content requires at least one supported claim with supporting evidence"
        )
    workflow = ContentWorkflow(
        topic_id=topic.id,
        evidence_pack_id=pack.id,
        angle_type=data.angle_type,
        requested_platforms=list(data.platforms),
        current_stage="created",
        status="created",
    )
    session.add(workflow)
    await session.flush()
    return await require_workflow(session, workflow.id)


async def _ensure_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        run = Run(id=run_id)
        session.add(run)
        await session.flush()
    return run


async def _check_budget(session: AsyncSession) -> tuple[int, VoiceProfile | None]:
    profile = await require_primary_profile(session)
    settings = await get_user_settings(session)
    day_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    spent_today = await session.scalar(
        select(func.coalesce(func.sum(LLMCall.cost_usd), Decimal("0"))).where(
            LLMCall.created_at >= day_start
        )
    )
    if Decimal(spent_today or 0) >= settings.daily_llm_budget_usd:
        raise ContentValidationError("daily LLM budget is exhausted")
    voice = await session.scalar(select(VoiceProfile).where(VoiceProfile.profile_id == profile.id))
    return settings.public_action_approval_level, voice


def _claim_context(pack: EvidencePack) -> list[dict[str, object]]:
    return [
        {
            "id": str(claim.id),
            "statement": claim.statement,
            "verification_status": claim.verification_status,
            "confidence": str(claim.confidence),
            "sources": [
                {
                    "excerpt": source.excerpt,
                    "locator": source.locator,
                    "supports": source.supports,
                    "document_id": str(source.document_id),
                }
                for source in claim.sources
            ],
        }
        for claim in pack.claims
    ]


def _voice_context(voice: VoiceProfile | None) -> dict[str, object] | None:
    if voice is None:
        return None
    return {
        "summary": voice.summary,
        "tone_descriptors": voice.tone_descriptors,
        "sentence_patterns": voice.sentence_patterns,
        "vocabulary_preferences": voice.vocabulary_preferences,
        "avoid_phrases": voice.avoid_phrases,
        "formatting_preferences": voice.formatting_preferences,
        "signature_traits": voice.signature_traits,
        "confidence": str(voice.confidence),
    }


def _fallback_claims(claims: list[Claim]) -> list[GeneratedClaim]:
    return [GeneratedClaim(statement=claim.statement, claim_id=claim.id) for claim in claims]


def _fallback_for_stage(
    stage: str,
    *,
    thesis: str,
    angle_type: str,
    claims: list[Claim],
    previous: GeneratedContent | None = None,
) -> GeneratedContent:
    references = _fallback_claims(claims)
    statements = [claim.statement for claim in claims]
    if stage == "angle":
        content = f"{angle_type.replace('_', ' ').title()} angle: {thesis}"
        return GeneratedContent(content=content, notes=["Deterministic evidence-first angle."])
    if stage == "outline":
        evidence_lines = "\n".join(f"- Evidence: {statement}" for statement in statements)
        content = f"1. Hook: {thesis}\n2. Core argument\n{evidence_lines}\n3. Practical takeaway"
        return GeneratedContent(content=content, claims=references)
    if stage == "draft":
        body = "\n\n".join(statements)
        content = f"{thesis}\n\n{body}\n\nThe practical takeaway: keep the conclusion inspectable."
        return GeneratedContent(content=content, claims=references)
    if stage in {"voice_transform", "rewrite"} and previous is not None:
        return GeneratedContent(
            content=previous.content,
            claims=previous.claims,
            notes=["Preserved the grounded draft because no model content was available."],
        )
    raise ValueError(f"no deterministic fallback for stage {stage}")


async def _next_revision(session: AsyncSession, workflow_id: uuid.UUID, stage: str) -> int:
    current = await session.scalar(
        select(func.coalesce(func.max(ContentArtifact.revision), 0)).where(
            ContentArtifact.workflow_id == workflow_id,
            ContentArtifact.stage == stage,
        )
    )
    return int(current or 0) + 1


async def _persist_artifact(
    session: AsyncSession,
    workflow: ContentWorkflow,
    pack: EvidencePack,
    *,
    stage: str,
    output: GeneratedContent,
    source: str,
    structured_data: dict[str, object],
    prompt: str | None = None,
    model: str | None = None,
    run_id: uuid.UUID | None = None,
) -> ContentArtifact:
    known_claims = {claim.id: claim for claim in pack.claims}
    artifact = ContentArtifact(
        workflow_id=workflow.id,
        stage=stage,
        revision=await _next_revision(session, workflow.id, stage),
        content=output.content.strip(),
        structured_data=structured_data,
        source=source,
        prompt_version=prompt,
        model=model,
        run_id=run_id,
    )
    artifact.claim_references = [
        ContentClaimReference(
            claimed_claim_id=reference.claim_id,
            resolved_claim_id=(reference.claim_id if reference.claim_id in known_claims else None),
            statement=reference.statement.strip(),
        )
        for reference in output.claims
    ]
    workflow.artifacts.append(artifact)
    await session.flush()
    workflow.current_stage = stage
    return artifact


def _artifact_output(artifact: ContentArtifact) -> GeneratedContent:
    return GeneratedContent(
        content=artifact.content,
        claims=[
            GeneratedClaim(statement=reference.statement, claim_id=reference.claimed_claim_id)
            for reference in artifact.claim_references
        ],
    )


async def _generate_stage(
    session: AsyncSession,
    generator: ContentGenerator,
    run: Run,
    workflow: ContentWorkflow,
    pack: EvidencePack,
    *,
    stage: str,
    context: dict[str, object],
    fallback: GeneratedContent,
) -> ContentArtifact:
    result = await generator.generate(stage, context)
    await log_llm_call(session, run, result)
    generated = result.parsed
    used_fallback = not generated.content.strip()
    output = fallback if used_fallback else generated
    return await _persist_artifact(
        session,
        workflow,
        pack,
        stage=stage,
        output=output,
        source="deterministic_fallback" if used_fallback else "model",
        structured_data={"notes": output.notes, "used_fallback": used_fallback},
        prompt=result.usage.prompt_version,
        model=result.usage.model,
        run_id=run.id,
    )


def _grounding_findings(pack: EvidencePack, artifact: ContentArtifact) -> list[dict[str, object]]:
    allowed = {claim.id: claim for claim in pack.claims}
    findings: list[dict[str, object]] = []
    if not artifact.claim_references:
        findings.append(
            {
                "status": "unsupported",
                "statement": "The generated draft has no factual claim mappings.",
                "claim_id": None,
                "reason": "At least one supported evidence claim is required.",
            }
        )
    for reference in artifact.claim_references:
        claim = allowed.get(reference.claimed_claim_id)
        if claim is None:
            status = "foreign"
            reason = "The referenced claim does not belong to this evidence pack."
        elif claim.verification_status != "supported":
            status = claim.verification_status
            reason = f"The evidence claim is {claim.verification_status}, not supported."
        elif not any(source.supports for source in claim.sources):
            status = "unsupported"
            reason = "The evidence claim has no supporting excerpt."
        else:
            status = "supported"
            reason = "The statement maps to a supported claim with source evidence."
        findings.append(
            {
                "status": status,
                "statement": reference.statement,
                "claim_id": str(reference.claimed_claim_id),
                "reason": reason,
            }
        )
    return findings


async def _fact_check(
    session: AsyncSession,
    workflow: ContentWorkflow,
    pack: EvidencePack,
    artifact: ContentArtifact,
    *,
    run_id: uuid.UUID,
) -> tuple[ContentArtifact, bool]:
    findings = _grounding_findings(pack, artifact)
    passed = bool(findings) and all(finding["status"] == "supported" for finding in findings)
    summary = (
        f"Fact check passed for {len(findings)} grounded statement(s) in {artifact.stage}."
        if passed
        else (
            f"Fact check failed for {artifact.stage}; unsupported or unmapped statements "
            "cannot advance."
        )
    )
    output = GeneratedContent(content=summary)
    saved = await _persist_artifact(
        session,
        workflow,
        pack,
        stage="fact_check",
        output=output,
        source="deterministic",
        structured_data={
            "passed": passed,
            "checked_stage": artifact.stage,
            "checked_artifact_id": str(artifact.id),
            "findings": findings,
        },
        run_id=run_id,
    )
    return saved, passed


async def _quality_artifact(
    session: AsyncSession,
    generator: ContentGenerator,
    run: Run,
    workflow: ContentWorkflow,
    pack: EvidencePack,
    artifact: ContentArtifact,
) -> ContentArtifact:
    deterministic = evaluate_deterministic_quality(
        artifact.content, grounded_claim_count=len(artifact.claim_references)
    )
    result = await generator.evaluate_quality(
        {
            "content": artifact.content,
            "deterministic_score": str(deterministic.score),
            "deterministic_subscores": {
                key: str(value) for key, value in deterministic.subscores.items()
            },
            "deterministic_explanations": deterministic.explanations,
        }
    )
    await log_llm_call(session, run, result)
    judgement = result.parsed
    model_score = (judgement.authenticity + judgement.clarity + judgement.usefulness) / Decimal("3")
    overall = (deterministic.score * Decimal("0.700") + model_score * Decimal("0.300")).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    explanations = deterministic.explanations + judgement.explanations
    content = f"Overall quality score: {overall}. " + " ".join(explanations)
    return await _persist_artifact(
        session,
        workflow,
        pack,
        stage="quality_evaluation",
        output=GeneratedContent(content=content),
        source="model",
        structured_data={
            "overall_score": str(overall),
            "deterministic_score": str(deterministic.score),
            "deterministic_subscores": {
                key: str(value) for key, value in deterministic.subscores.items()
            },
            "model_score": str(model_score.quantize(Decimal("0.001"))),
            "model_subscores": {
                "authenticity": str(judgement.authenticity),
                "clarity": str(judgement.clarity),
                "usefulness": str(judgement.usefulness),
            },
            "explanations": explanations,
        },
        prompt=result.usage.prompt_version,
        model=result.usage.model,
        run_id=run.id,
    )


async def _reset_approvals(
    session: AsyncSession, workflow: ContentWorkflow, required_level: int
) -> None:
    by_platform = {approval.platform: approval for approval in workflow.approvals}
    policy = AutomationPolicy()
    for platform in workflow.requested_platforms:
        decision = policy.evaluate(
            PublicAction(platform=platform),  # type: ignore[arg-type]
            required_level=required_level,
        )
        approval = by_platform.get(platform)
        if approval is None:
            approval = ContentApproval(
                workflow_id=workflow.id,
                platform=platform,
                required_level=decision.required_level,
                decision="pending",
            )
            workflow.approvals.append(approval)
        else:
            approval.required_level = decision.required_level
            approval.decision = "pending"
            approval.actor = None
            approval.reason = None
            approval.decided_at = None
            approval.decision_run_id = None
    await session.flush()


async def run_workflow(
    session: AsyncSession,
    llm: LLMClient,
    *,
    workflow_id: uuid.UUID,
    run_id: uuid.UUID,
) -> ContentWorkflow:
    workflow = await require_workflow(session, workflow_id)
    required_level, voice = await _check_budget(session)
    pack = await _require_evidence_pack(session, workflow.evidence_pack_id)
    supported = _supported_claims(pack)
    if not supported:
        raise ContentValidationError(
            "content requires at least one supported claim with supporting evidence"
        )
    topic = await session.get(TopicCandidate, workflow.topic_id)
    if topic is None:
        raise ContentNotFound("topic candidate not found")

    run = await _ensure_run(session, run_id)
    generator = ContentGenerator(llm)
    workflow.status = "running"
    workflow.latest_run_id = run.id
    for approval in workflow.approvals:
        approval.decision = "pending"
        approval.actor = None
        approval.reason = None
        approval.decided_at = None
        approval.decision_run_id = None

    claims_context = _claim_context(pack)
    angle = await _generate_stage(
        session,
        generator,
        run,
        workflow,
        pack,
        stage="angle",
        context={
            "topic": {"title": topic.title, "summary": topic.summary},
            "thesis": pack.thesis,
            "angle_type": workflow.angle_type,
            "claims": claims_context,
        },
        fallback=_fallback_for_stage(
            "angle",
            thesis=pack.thesis,
            angle_type=workflow.angle_type,
            claims=supported,
        ),
    )
    outline = await _generate_stage(
        session,
        generator,
        run,
        workflow,
        pack,
        stage="outline",
        context={"angle": angle.content, "thesis": pack.thesis, "claims": claims_context},
        fallback=_fallback_for_stage(
            "outline",
            thesis=pack.thesis,
            angle_type=workflow.angle_type,
            claims=supported,
        ),
    )
    draft = await _generate_stage(
        session,
        generator,
        run,
        workflow,
        pack,
        stage="draft",
        context={"outline": outline.content, "thesis": pack.thesis, "claims": claims_context},
        fallback=_fallback_for_stage(
            "draft",
            thesis=pack.thesis,
            angle_type=workflow.angle_type,
            claims=supported,
        ),
    )
    voice_output = _fallback_for_stage(
        "voice_transform",
        thesis=pack.thesis,
        angle_type=workflow.angle_type,
        claims=supported,
        previous=_artifact_output(draft),
    )
    transformed = await _generate_stage(
        session,
        generator,
        run,
        workflow,
        pack,
        stage="voice_transform",
        context={
            "draft": draft.content,
            "draft_claims": [
                {
                    "statement": reference.statement,
                    "claim_id": str(reference.claimed_claim_id),
                }
                for reference in draft.claim_references
            ],
            "voice_profile": _voice_context(voice),
        },
        fallback=voice_output,
    )
    _fact_artifact, passed = await _fact_check(session, workflow, pack, transformed, run_id=run.id)
    if not passed:
        workflow.status = "fact_check_failed"
        await session.flush()
        return workflow

    quality = await _quality_artifact(session, generator, run, workflow, pack, transformed)
    rewrite_fallback = _fallback_for_stage(
        "rewrite",
        thesis=pack.thesis,
        angle_type=workflow.angle_type,
        claims=supported,
        previous=_artifact_output(transformed),
    )
    rewrite = await _generate_stage(
        session,
        generator,
        run,
        workflow,
        pack,
        stage="rewrite",
        context={
            "content": transformed.content,
            "quality": quality.structured_data,
            "claims": claims_context,
        },
        fallback=rewrite_fallback,
    )
    _rewrite_fact_check, passed = await _fact_check(session, workflow, pack, rewrite, run_id=run.id)
    if not passed:
        workflow.status = "fact_check_failed"
        await session.flush()
        return workflow

    claim_statements = [reference.statement for reference in rewrite.claim_references]
    adapters = {
        "linkedin": LinkedInContentAdapter(),
        "x": XContentAdapter(),
    }
    for platform in workflow.requested_platforms:
        adapter = adapters[platform]
        stage = f"{platform}_adaptation"
        fallback = GeneratedContent(
            content=adapter.fallback(pack.thesis, claim_statements),
            claims=[
                GeneratedClaim(
                    statement=reference.statement,
                    claim_id=reference.claimed_claim_id,
                )
                for reference in rewrite.claim_references
            ],
        )
        adaptation = await _generate_stage(
            session,
            generator,
            run,
            workflow,
            pack,
            stage=stage,
            context={
                "platform": platform,
                "content": rewrite.content,
                "claims": claims_context,
            },
            fallback=fallback,
        )
        _adaptation_fact_check, passed = await _fact_check(
            session, workflow, pack, adaptation, run_id=run.id
        )
        if not passed:
            workflow.status = "fact_check_failed"
            await session.flush()
            return workflow

    await _reset_approvals(session, workflow, required_level)
    workflow.status = "ready_for_approval"
    workflow.current_stage = "approval"
    await session.flush()
    return workflow


async def put_manual_artifact(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    stage: str,
    data: ManualArtifactPut,
    run_id: uuid.UUID,
) -> ContentWorkflow:
    editable = {
        "angle",
        "outline",
        "draft",
        "voice_transform",
        "rewrite",
        "linkedin_adaptation",
        "x_adaptation",
    }
    if stage not in editable or stage not in CONTENT_STAGES:
        raise ContentValidationError("this content stage cannot be edited manually")
    workflow = await require_workflow(session, workflow_id)
    if stage == "linkedin_adaptation" and "linkedin" not in workflow.requested_platforms:
        raise ContentValidationError("LinkedIn was not requested for this workflow")
    if stage == "x_adaptation" and "x" not in workflow.requested_platforms:
        raise ContentValidationError("X was not requested for this workflow")
    pack = await _require_evidence_pack(session, workflow.evidence_pack_id)
    run = await _ensure_run(session, run_id)
    artifact = await _persist_artifact(
        session,
        workflow,
        pack,
        stage=stage,
        output=GeneratedContent(content=data.content, claims=data.claims),
        source="manual",
        structured_data={"note": data.note} if data.note else {},
        run_id=run.id,
    )
    workflow.latest_run_id = run.id
    if stage in {"linkedin_adaptation", "x_adaptation"}:
        _manual_fact_check, passed = await _fact_check(
            session, workflow, pack, artifact, run_id=run.id
        )
        if not passed:
            workflow.status = "fact_check_failed"
            await session.flush()
            return workflow
        platform = "linkedin" if stage.startswith("linkedin") else "x"
        for approval in workflow.approvals:
            if approval.platform == platform:
                approval.decision = "pending"
                approval.actor = None
                approval.reason = None
                approval.decided_at = None
                approval.decision_run_id = None
        workflow.status = "ready_for_approval"
        workflow.current_stage = "approval"
    else:
        workflow.status = "created"
    await session.flush()
    return workflow


async def decide_approval(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    data: ApprovalDecisionInput,
    run_id: uuid.UUID,
    embedder: EmbeddingProvider,
) -> ContentWorkflow:
    workflow = await require_workflow(session, workflow_id)
    if workflow.status not in {"ready_for_approval", "approved", "rejected"}:
        raise ContentConflict("workflow is not ready for approval")
    approval = next((item for item in workflow.approvals if item.platform == data.platform), None)
    if approval is None:
        raise ContentNotFound("platform approval record not found")
    pack = await _require_evidence_pack(session, workflow.evidence_pack_id)
    adaptation_stage = f"{data.platform}_adaptation"
    latest_adaptation = max(
        (artifact for artifact in workflow.artifacts if artifact.stage == adaptation_stage),
        key=lambda artifact: artifact.revision,
        default=None,
    )
    if latest_adaptation is None:
        raise ContentConflict("platform adaptation does not exist")
    findings = _grounding_findings(pack, latest_adaptation)
    if not findings or any(finding["status"] != "supported" for finding in findings):
        raise ContentConflict("latest platform adaptation has not passed grounding checks")
    run = await _ensure_run(session, run_id)
    # M4 duplicate gate. Runs only for approvals: a rejection needs no
    # duplicate opinion, and must not write history.
    if data.decision == "approved":
        config = await memory_service.get_active_duplicate_config(session)
        evaluation = await memory_service.evaluate_duplicate(
            session,
            text=latest_adaptation.content,
            platform=data.platform,
            config=config,
            embedder=embedder,
            # Or a re-approval would find the post this workflow itself
            # recorded last time and block on it.
            exclude_workflow_id=workflow.id,
            run_id=run.id,
        )
        # An override only means anything against a block: recording one for a
        # verdict that was never going to stop the approval would overstate
        # what the human actually decided.
        overridden = evaluation.verdict == "block" and data.duplicate_override
        await memory_service.persist_duplicate_check(
            session,
            workflow_id=workflow.id,
            platform=data.platform,
            evaluation=evaluation,
            overridden=overridden,
            override_reason=data.override_reason if overridden else None,
            run_id=run.id,
        )
        if evaluation.verdict == "block" and not overridden:
            raise DuplicateBlocked(
                "this draft is a near-duplicate of an existing post "
                f"(similarity {evaluation.top_similarity:.2f}); "
                "approve again with duplicate_override and a reason to proceed"
            )
    decision = AutomationPolicy().evaluate(
        PublicAction(platform=data.platform),
        required_level=approval.required_level,
        approval_decision=data.decision,
    )
    if data.decision == "approved" and not decision.allowed:
        raise ContentConflict("approval policy did not authorize this local decision")
    approval.decision = data.decision
    approval.actor = data.actor.strip()
    approval.reason = data.reason.strip() if data.reason else None
    approval.decided_at = utcnow()
    approval.decision_run_id = run.id
    workflow.latest_run_id = run.id
    decisions = {
        item.platform: (data.decision if item.id == approval.id else item.decision)
        for item in workflow.approvals
    }
    if any(value == "rejected" for value in decisions.values()):
        workflow.status = "rejected"
    elif decisions and all(value == "approved" for value in decisions.values()):
        workflow.status = "approved"
    else:
        workflow.status = "ready_for_approval"
    if data.decision == "approved":
        # Post history is per platform, so it follows the platform approval,
        # not the workflow status: the other platform may still be pending.
        # Idempotent across re-approval by (workflow_id, platform).
        await memory_service.record_workflow_post(
            session,
            workflow_id=workflow.id,
            platform=data.platform,
            content=latest_adaptation.content,
            embedder=embedder,
            run_id=run.id,
        )
    await session.flush()
    return workflow
