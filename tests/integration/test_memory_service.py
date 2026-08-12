import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.content.models import ContentWorkflow
from src.llm.embeddings import MockEmbedder
from src.memory import service
from src.memory.analytics import MockAnalyticsProvider
from src.memory.models import DuplicateCheck
from src.memory.schemas import DuplicateConfigCreate, PostRecordCreate, PostRecordUpdate
from src.memory.service import ContentMemoryConflict, ContentMemoryNotFound
from src.research.models import EvidencePack, ScoringConfig, TopicCandidate


async def create_workflow(session: AsyncSession) -> ContentWorkflow:
    """Persist the minimum M2/M3 chain a workflow-origin post record needs."""
    suffix = uuid.uuid4().hex
    config = ScoringConfig(
        name="memory-test",
        version=suffix,
        weights={},
        near_duplicate_threshold=Decimal("0.900"),
        active=False,
    )
    session.add(config)
    await session.flush()
    topic = TopicCandidate(
        cluster_key=suffix,
        title="A topic that only exists to hang a workflow from",
        summary="Fixture topic.",
        freshness=Decimal("0.500"),
        relevance=Decimal("0.500"),
        novelty=Decimal("0.500"),
        momentum=Decimal("0.500"),
        credibility=Decimal("0.500"),
        authority_fit=Decimal("0.500"),
        insight_potential=Decimal("0.500"),
        platform_fit={"linkedin": "0.500", "x": "0.500"},
        total_score=Decimal("0.5000"),
        scoring_config_id=config.id,
        scored_at=datetime.now(UTC),
    )
    session.add(topic)
    await session.flush()
    pack = EvidencePack(topic_id=topic.id, thesis="Fixture thesis.")
    session.add(pack)
    await session.flush()
    workflow = ContentWorkflow(
        topic_id=topic.id,
        evidence_pack_id=pack.id,
        angle_type="technical",
        requested_platforms=["linkedin"],
        current_stage="created",
        status="created",
    )
    session.add(workflow)
    await session.flush()
    return workflow


@pytest.mark.asyncio
async def test_seeded_config_is_active(db_session: AsyncSession):
    config = await service.get_active_duplicate_config(db_session)
    assert config.version == "v1"
    assert config.warn_threshold == Decimal("0.700")
    assert config.block_threshold == Decimal("0.850")


@pytest.mark.asyncio
async def test_create_manual_post_embeds_and_hashes(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content="Evidence beats opinion every time."),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    assert record.origin == "manual"
    assert record.content_hash
    assert record.embedding_model == "mock-embed-v1"
    assert record.embedding is not None


@pytest.mark.asyncio
async def test_manual_post_is_always_recorded_as_published_externally(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="x", content="Something I posted last week."),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    assert record.status == "published_externally"
    assert record.embedding is not None
    assert len(record.embedding) == MockEmbedder.dimensions


@pytest.mark.asyncio
async def test_external_url_can_be_cleared(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(
            platform="x", content="Backfilled with a typo'd link.", external_url="https://typo"
        ),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    updated = await service.update_post_record(
        db_session, record.id, PostRecordUpdate(external_url=None)
    )
    assert updated.external_url is None


@pytest.mark.asyncio
async def test_identical_text_is_blocked(db_session: AsyncSession):
    text = "A staged content pipeline keeps every intermediate artifact inspectable."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "block"
    assert evaluation.top_similarity == pytest.approx(1.0)
    assert evaluation.nearest_post_record_id is not None


@pytest.mark.asyncio
async def test_unrelated_text_is_clear(db_session: AsyncSession):
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content="Kubernetes operators reconcile state."),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text="Sourdough hydration changes the crumb structure entirely.",
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"


@pytest.mark.asyncio
async def test_other_platform_is_ignored_by_default(db_session: AsyncSession):
    text = "One idea, posted to exactly one platform."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="x", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"


@pytest.mark.asyncio
async def test_cross_platform_check_sees_the_other_platform(db_session: AsyncSession):
    text = "One idea, checked across both platforms this time."
    await service.create_post_record(
        db_session,
        PostRecordCreate(platform="x", content=text),
        embedder=MockEmbedder(),
        run_id=uuid.uuid4(),
    )
    config = await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="cross-v1",
            warn_threshold=Decimal("0.700"),
            block_threshold=Decimal("0.850"),
            cross_platform_check=True,
        ),
    )
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "block"


@pytest.mark.asyncio
async def test_activating_a_config_deactivates_the_previous_one(db_session: AsyncSession):
    await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="v2",
            warn_threshold=Decimal("0.600"),
            block_threshold=Decimal("0.800"),
            active=True,
        ),
    )
    active = await service.get_active_duplicate_config(db_session)
    assert active.version == "v2"


@pytest.mark.asyncio
async def test_duplicate_config_version_must_be_unique(db_session: AsyncSession):
    with pytest.raises(ContentMemoryConflict, match="already exists"):
        await service.create_duplicate_config(
            db_session,
            DuplicateConfigCreate(
                version="v1", warn_threshold=Decimal("0.600"), block_threshold=Decimal("0.800")
            ),
        )


@pytest.mark.asyncio
async def test_missing_post_record_raises_not_found(db_session: AsyncSession):
    with pytest.raises(ContentMemoryNotFound):
        await service.require_post_record(db_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_lookback_window_excludes_older_history(db_session: AsyncSession):
    text = "History older than the lookback window is outside the policy."
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content=text),
        embedder=MockEmbedder(),
        run_id=None,
    )
    record.created_at = datetime.now(UTC) - timedelta(days=30)
    await db_session.flush()
    config = await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="lookback-v1",
            warn_threshold=Decimal("0.700"),
            block_threshold=Decimal("0.850"),
            lookback_days=7,
        ),
    )
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"
    assert evaluation.nearest_post_record_id is None


@pytest.mark.asyncio
async def test_lookback_uses_the_posted_date_not_the_backfill_date(db_session: AsyncSession):
    """A two-year-old post backfilled today is old history, not fresh history.

    `created_at` is when the row was typed in, which for manual backfill — the
    corpus this criterion exists to build — says nothing about when the post
    went out.
    """
    text = "A conference talk I gave two years ago and only now wrote down."
    await service.create_post_record(
        db_session,
        PostRecordCreate(
            platform="linkedin",
            content=text,
            posted_at=datetime.now(UTC) - timedelta(days=730),
        ),
        embedder=MockEmbedder(),
        run_id=None,
    )
    config = await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="lookback-posted-at",
            warn_threshold=Decimal("0.700"),
            block_threshold=Decimal("0.850"),
            lookback_days=90,
        ),
    )
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "clear"
    assert evaluation.nearest_post_record_id is None


@pytest.mark.asyncio
async def test_lookback_keeps_a_recently_posted_backfill(db_session: AsyncSession):
    """The mirror image: an old row about a recent post stays in the window."""
    text = "Something I posted three days ago and backfilled straight away."
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(
            platform="linkedin",
            content=text,
            posted_at=datetime.now(UTC) - timedelta(days=3),
        ),
        embedder=MockEmbedder(),
        run_id=None,
    )
    # An old `created_at` must not evict a post that went out this week.
    record.created_at = datetime.now(UTC) - timedelta(days=400)
    await db_session.flush()
    config = await service.create_duplicate_config(
        db_session,
        DuplicateConfigCreate(
            version="lookback-recent-post",
            warn_threshold=Decimal("0.700"),
            block_threshold=Decimal("0.850"),
            lookback_days=90,
        ),
    )
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=None,
    )
    assert evaluation.verdict == "block"
    assert evaluation.nearest_post_record_id == record.id


@pytest.mark.asyncio
async def test_workflow_post_withdrawal_spares_a_published_record(db_session: AsyncSession):
    """Withdrawal unwrites a claim about an approval, never a published post."""
    workflow = await create_workflow(db_session)
    record = await service.record_workflow_post(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        content="Approved locally, and then actually published.",
        embedder=MockEmbedder(),
        run_id=None,
    )
    await service.update_post_record(
        db_session,
        record.id,
        PostRecordUpdate(status="published_externally", external_url="https://example.test/post"),
    )
    snapshot = await service.capture_metrics(
        db_session, post_id=record.id, provider=MockAnalyticsProvider()
    )
    await service.remove_workflow_post(db_session, workflow_id=workflow.id, platform="linkedin")
    survivor = await service.require_post_record(db_session, record.id)
    assert survivor.status == "published_externally"
    # The snapshots cascade, so losing the row would silently lose these too.
    assert [item.id for item in survivor.snapshots] == [snapshot.id]


@pytest.mark.asyncio
async def test_a_workflow_does_not_block_itself(db_session: AsyncSession):
    workflow = await create_workflow(db_session)
    text = "The draft this very workflow already recorded as history."
    await service.record_workflow_post(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        content=text,
        embedder=MockEmbedder(),
        run_id=None,
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=workflow.id,
    )
    assert evaluation.verdict == "clear"
    assert evaluation.nearest_post_record_id is None

    # Any other workflow is still blocked by the same history.
    other = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=uuid.uuid4(),
    )
    assert other.verdict == "block"


@pytest.mark.asyncio
async def test_re_recording_a_workflow_post_updates_it_in_place(db_session: AsyncSession):
    workflow = await create_workflow(db_session)
    first = await service.record_workflow_post(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        content="The first approved draft.",
        embedder=MockEmbedder(),
        run_id=None,
    )
    assert first.status == "approved_unpublished"
    assert first.origin == "workflow"
    # Read the hash now: the second call updates this very instance in place.
    first_hash = first.content_hash
    second = await service.record_workflow_post(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        content="The revised draft, approved after a rejection.",
        embedder=MockEmbedder(),
        run_id=None,
    )
    assert second.id == first.id
    assert second.content == "The revised draft, approved after a rejection."
    assert second.content_hash != first_hash
    records = await service.list_post_records(db_session)
    assert len([item for item in records if item.workflow_id == workflow.id]) == 1


@pytest.mark.asyncio
async def test_workflow_history_cannot_be_deleted_but_manual_backfill_can(
    db_session: AsyncSession,
):
    workflow = await create_workflow(db_session)
    from_workflow = await service.record_workflow_post(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        content="Workflow history is not the user's to delete.",
        embedder=MockEmbedder(),
        run_id=None,
    )
    with pytest.raises(ContentMemoryConflict, match="cannot be deleted"):
        await service.delete_post_record(db_session, from_workflow.id)

    manual = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content="A backfill entered by mistake."),
        embedder=MockEmbedder(),
        run_id=None,
    )
    await service.delete_post_record(db_session, manual.id)
    with pytest.raises(ContentMemoryNotFound):
        await service.require_post_record(db_session, manual.id)


@pytest.mark.asyncio
async def test_persisted_check_keeps_the_evidence_for_the_verdict(db_session: AsyncSession):
    workflow = await create_workflow(db_session)
    text = "Every verdict has to stay explainable after the fact."
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(platform="linkedin", content=text),
        embedder=MockEmbedder(),
        run_id=None,
    )
    config = await service.get_active_duplicate_config(db_session)
    evaluation = await service.evaluate_duplicate(
        db_session,
        text=text,
        platform="linkedin",
        config=config,
        embedder=MockEmbedder(),
        exclude_workflow_id=workflow.id,
    )
    check = await service.persist_duplicate_check(
        db_session,
        workflow_id=workflow.id,
        platform="linkedin",
        evaluation=evaluation,
        overridden=True,
        override_reason="Different audience, deliberate repetition.",
        run_id=None,
    )
    stored = await db_session.scalar(select(DuplicateCheck).where(DuplicateCheck.id == check.id))
    assert stored is not None
    assert stored.verdict == "block"
    assert stored.top_similarity == Decimal("1.000")
    assert stored.config_version == "v1"
    assert stored.nearest_post_record_id == record.id
    assert stored.components[0]["post_record_id"] == str(record.id)
    assert stored.overridden is True


@pytest.mark.asyncio
async def test_captured_metrics_are_tagged_as_mock(db_session: AsyncSession):
    record = await service.create_post_record(
        db_session,
        PostRecordCreate(
            platform="linkedin",
            content="A post whose numbers are invented.",
            posted_at=datetime.now(UTC) - timedelta(days=3),
        ),
        embedder=MockEmbedder(),
        run_id=None,
    )
    snapshot = await service.capture_metrics(
        db_session, post_id=record.id, provider=MockAnalyticsProvider()
    )
    assert snapshot.source == "mock"
    assert snapshot.is_mock is True
    assert snapshot.impressions is not None and snapshot.impressions >= 0
    reloaded = await service.require_post_record(db_session, record.id)
    assert [item.id for item in reloaded.snapshots] == [snapshot.id]
