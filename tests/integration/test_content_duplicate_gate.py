import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.main import app
from src.db.session import get_session
from src.llm.mock import MockLLM
from src.memory.models import DuplicateCheck, PostRecord
from tests.integration.test_content_api import create_grounded_topic


@pytest_asyncio.fixture
async def content_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client for the whole app, matching the per-module style of the suite.

    Defined here rather than imported from the M3 suite: importing a fixture
    makes every test parameter that uses it a redefinition of the imported
    name.
    """

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    original_llm = app.state.llm_client
    app.state.llm_client = MockLLM()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.state.llm_client = original_llm
        app.dependency_overrides.pop(get_session, None)


async def ready_workflow(client: AsyncClient, suffix: str) -> tuple[str, str, str]:
    """Drive a workflow to ready_for_approval.

    Returns (workflow_id, latest LinkedIn adaptation text, grounded claim id).
    `create_grounded_topic` returns (topic_id, claim_id) — the workflow endpoint
    resolves the evidence pack from the topic itself, so no pack id is sent.
    """
    topic_id, claim_id = await create_grounded_topic(client, suffix)
    created = await client.post(
        "/api/content/workflows",
        json={
            "topic_id": topic_id,
            "angle_type": "framework",
            "platforms": ["linkedin"],
        },
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    run = await client.post(f"/api/content/workflows/{workflow_id}/run")
    assert run.status_code == 200, run.text
    workflow = run.json()
    assert workflow["status"] == "ready_for_approval", workflow["status"]
    adaptation = max(
        (a for a in workflow["artifacts"] if a["stage"] == "linkedin_adaptation"),
        key=lambda a: a["revision"],
    )
    return workflow_id, adaptation["content"], claim_id


async def approve_workflow(client: AsyncClient, suffix: str) -> tuple[str, str]:
    """`ready_workflow` for the tests that have no use for the claim id."""
    workflow_id, content, _claim_id = await ready_workflow(client, suffix)
    return workflow_id, content


async def post_records_for(session: AsyncSession, workflow_id: str) -> list[PostRecord]:
    result = await session.execute(
        select(PostRecord).where(PostRecord.workflow_id == uuid.UUID(workflow_id))
    )
    return list(result.scalars().all())


async def duplicate_checks_for(session: AsyncSession, workflow_id: str) -> list[DuplicateCheck]:
    result = await session.execute(
        select(DuplicateCheck)
        .where(DuplicateCheck.workflow_id == uuid.UUID(workflow_id))
        .order_by(DuplicateCheck.created_at)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_approval_records_a_post_and_a_clear_check(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert response.status_code == 200, response.text

    records = await post_records_for(db_session, workflow_id)
    assert len(records) == 1
    assert records[0].origin == "workflow"
    assert records[0].status == "approved_unpublished"
    assert records[0].platform == "linkedin"

    checks = await duplicate_checks_for(db_session, workflow_id)
    assert len(checks) == 1
    assert checks[0].verdict == "clear"
    assert checks[0].overridden is False


@pytest.mark.asyncio
async def test_reapproval_does_not_duplicate_the_post_record(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    for _ in range(2):
        response = await content_client.post(
            f"/api/content/workflows/{workflow_id}/approval",
            json={"platform": "linkedin", "decision": "approved", "actor": "user"},
        )
        assert response.status_code == 200, response.text
    assert len(await post_records_for(db_session, workflow_id)) == 1


@pytest.mark.asyncio
async def test_near_duplicate_is_blocked_then_allowed_with_an_override(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    first_id, text = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{first_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text

    # Record the same text again so the second workflow has a true duplicate to
    # find that does not belong to its own workflow.
    manual = await content_client.post(
        "/api/memory/posts", json={"platform": "linkedin", "content": text}
    )
    assert manual.status_code == 201, manual.text

    second_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    blocked = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert blocked.status_code == 409
    assert "duplicate" in blocked.json()["detail"].lower()

    # A blocked attempt is exactly the thing that must stay inspectable.
    blocked_checks = await duplicate_checks_for(db_session, second_id)
    assert [check.verdict for check in blocked_checks] == ["block"]
    assert blocked_checks[0].overridden is False
    assert await post_records_for(db_session, second_id) == []

    overridden = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={
            "platform": "linkedin",
            "decision": "approved",
            "actor": "user",
            "duplicate_override": True,
            "override_reason": "Intentional follow-up in a series.",
        },
    )
    assert overridden.status_code == 200, overridden.text

    checks = await duplicate_checks_for(db_session, second_id)
    assert len(checks) == 2
    assert checks[-1].overridden is True
    assert checks[-1].override_reason == "Intentional follow-up in a series."
    assert len(await post_records_for(db_session, second_id)) == 1


@pytest.mark.asyncio
async def test_rejecting_a_platform_withdraws_its_post_record(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text
    assert len(await post_records_for(db_session, workflow_id)) == 1

    rejected = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "rejected", "actor": "user"},
    )
    assert rejected.status_code == 200, rejected.text
    assert await post_records_for(db_session, workflow_id) == []
    # The audit trail records what happened and stays put; only the claim that
    # this text is approved history is withdrawn.
    assert len(await duplicate_checks_for(db_session, workflow_id)) == 1

    # And a fresh workflow over the same text is no longer blocked by it.
    second_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    second = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert second.status_code == 200, second.text
    second_checks = await duplicate_checks_for(db_session, second_id)
    assert [check.verdict for check in second_checks] == ["clear"]


@pytest.mark.asyncio
async def test_rejection_leaves_a_manual_record_of_the_same_text_alone(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, text = await approve_workflow(content_client, uuid.uuid4().hex)
    manual = await content_client.post(
        "/api/memory/posts", json={"platform": "linkedin", "content": text}
    )
    assert manual.status_code == 201, manual.text

    rejected = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "rejected", "actor": "user"},
    )
    assert rejected.status_code == 200, rejected.text

    still_there = await content_client.get(f"/api/memory/posts/{manual.json()['id']}")
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_rerunning_a_workflow_withdraws_its_post_records(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A re-run resets the approval, so the record claiming it must go too.

    Otherwise the row survives as a claim that a live approval exists for text
    the re-run has already replaced, and it goes on blocking other workflows.
    """
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text
    assert len(await post_records_for(db_session, workflow_id)) == 1

    rerun = await content_client.post(f"/api/content/workflows/{workflow_id}/run")
    assert rerun.status_code == 200, rerun.text
    assert [a["decision"] for a in rerun.json()["approvals"]] == ["pending"]
    assert await post_records_for(db_session, workflow_id) == []


@pytest.mark.asyncio
async def test_editing_an_adaptation_withdraws_that_platforms_record(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, _, claim_id = await ready_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text
    assert len(await post_records_for(db_session, workflow_id)) == 1

    edited = await content_client.put(
        f"/api/content/workflows/{workflow_id}/artifacts/linkedin_adaptation",
        json={
            "content": "A human-edited LinkedIn draft grounded in the stored claim.",
            "claims": [{"statement": "A staged system checks claims.", "claim_id": claim_id}],
        },
    )
    assert edited.status_code == 200, edited.text
    assert [a["decision"] for a in edited.json()["approvals"]] == ["pending"]
    # The approved text no longer exists, so neither may the record of it.
    assert await post_records_for(db_session, workflow_id) == []


@pytest.mark.asyncio
async def test_a_published_record_survives_withdrawal_with_its_snapshots(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Withdrawal is about a claim, and a published post is no longer a claim.

    Once the user marks the row `published_externally` it describes something
    that exists in the world; deleting it would take its append-only metric
    history with it via the snapshots cascade.
    """
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text
    records = await post_records_for(db_session, workflow_id)
    post_id = str(records[0].id)

    published = await content_client.patch(
        f"/api/memory/posts/{post_id}",
        json={
            "status": "published_externally",
            "posted_at": "2026-08-01T09:00:00+00:00",
            "external_url": "https://www.linkedin.com/posts/real-one",
        },
    )
    assert published.status_code == 200, published.text
    snapshot = await content_client.post(f"/api/memory/posts/{post_id}/metrics")
    assert snapshot.status_code == 201, snapshot.text

    rejected = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "rejected", "actor": "user"},
    )
    assert rejected.status_code == 200, rejected.text

    survivor = await content_client.get(f"/api/memory/posts/{post_id}")
    assert survivor.status_code == 200, survivor.text
    assert survivor.json()["status"] == "published_externally"
    assert survivor.json()["external_url"] == "https://www.linkedin.com/posts/real-one"
    assert [item["id"] for item in survivor.json()["snapshots"]] == [snapshot.json()["id"]]

    # A re-run is the other withdrawal path and must spare it just the same.
    rerun = await content_client.post(f"/api/content/workflows/{workflow_id}/run")
    assert rerun.status_code == 200, rerun.text
    assert (await content_client.get(f"/api/memory/posts/{post_id}")).status_code == 200


@pytest.mark.asyncio
async def test_preview_and_gate_agree_for_a_workflows_own_record(
    content_client: AsyncClient,
) -> None:
    """The panel must score the corpus the gate scores, own record excluded."""
    workflow_id, text = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text

    scoped = await content_client.post(
        "/api/memory/duplicate-check",
        json={"platform": "linkedin", "content": text, "workflow_id": workflow_id},
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["verdict"] == "clear"

    # Without a workflow the endpoint is still an honest ad-hoc check, and the
    # workflow's own row is part of the corpus it reports on.
    ad_hoc = await content_client.post(
        "/api/memory/duplicate-check",
        json={"platform": "linkedin", "content": text},
    )
    assert ad_hoc.status_code == 200, ad_hoc.text
    assert ad_hoc.json()["verdict"] == "block"


@pytest.mark.asyncio
async def test_a_blocked_verdict_is_readable_over_http(content_client: AsyncClient) -> None:
    first_id, text = await approve_workflow(content_client, uuid.uuid4().hex)
    approved = await content_client.post(
        f"/api/content/workflows/{first_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert approved.status_code == 200, approved.text
    manual = await content_client.post(
        "/api/memory/posts", json={"platform": "linkedin", "content": text}
    )
    assert manual.status_code == 201, manual.text

    second_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    blocked = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={"platform": "linkedin", "decision": "approved", "actor": "user"},
    )
    assert blocked.status_code == 409, blocked.text

    listed = await content_client.get(f"/api/content/workflows/{second_id}/duplicate-checks")
    assert listed.status_code == 200, listed.text
    assert [check["verdict"] for check in listed.json()] == ["block"]
    assert listed.json()[0]["overridden"] is False
    # The stored evidence for the verdict comes back too, not just the verdict.
    assert listed.json()[0]["top_similarity"] == "1.000"
    neighbours = {item["post_record_id"] for item in listed.json()[0]["components"]}
    assert manual.json()["id"] in neighbours

    overridden = await content_client.post(
        f"/api/content/workflows/{second_id}/approval",
        json={
            "platform": "linkedin",
            "decision": "approved",
            "actor": "user",
            "duplicate_override": True,
            "override_reason": "Deliberate follow-up in a series.",
        },
    )
    assert overridden.status_code == 200, overridden.text

    after = await content_client.get(f"/api/content/workflows/{second_id}/duplicate-checks")
    assert after.status_code == 200, after.text
    # Newest first, so the override is the head of the list.
    assert [check["verdict"] for check in after.json()] == ["block", "block"]
    assert after.json()[0]["overridden"] is True
    assert after.json()[0]["override_reason"] == "Deliberate follow-up in a series."
    assert after.json()[1]["overridden"] is False


@pytest.mark.asyncio
async def test_duplicate_checks_for_an_unknown_workflow_is_404(
    content_client: AsyncClient,
) -> None:
    response = await content_client.get(f"/api/content/workflows/{uuid.uuid4()}/duplicate-checks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_override_without_a_reason_is_rejected(content_client: AsyncClient) -> None:
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={
            "platform": "linkedin",
            "decision": "approved",
            "actor": "user",
            "duplicate_override": True,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejection_does_not_record_a_post(
    content_client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow_id, _ = await approve_workflow(content_client, uuid.uuid4().hex)
    response = await content_client.post(
        f"/api/content/workflows/{workflow_id}/approval",
        json={"platform": "linkedin", "decision": "rejected", "actor": "user"},
    )
    assert response.status_code == 200, response.text
    assert await post_records_for(db_session, workflow_id) == []
    # A rejection needs no duplicate opinion either.
    assert await duplicate_checks_for(db_session, workflow_id) == []
