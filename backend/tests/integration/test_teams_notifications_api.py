"""Graph's change and lifecycle notifications, through the public routes.

Pins what the plan promises: the validation token is echoed as text/plain; a
notification without this app's client state (or from another tenant) is
refused; one for a watched chat records ``sync_requested_at`` and queues the
chat's sync, answered 202; one for an unknown subscription or a chat not
watched is dropped; and each lifecycle event queues what it asks for.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import TeamsChatMatch, TeamsWatchState
from app.models.teams import GraphSubscription, TeamsGroup
from app.services.processing_queue import CHAT_PRIORITY, ProcessingQueue
from app.services.teams.jobs import SUBSCRIPTION_JOB_KIND, SYNC_JOB_KIND

STATE = "client-state-secret"
TENANT = "2b32b1fa-0000-4000-8000-000000000001"
CHANGES = "/api/v1/teams/notifications"
LIFECYCLE = "/api/v1/teams/lifecycle"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "graph_client_state", STATE)
    monkeypatch.setattr(settings, "graph_tenant_id", TENANT)
    monkeypatch.setattr(settings, "teams_enabled", True)


async def _subscribed_chat(
    db: AsyncSession, watch: TeamsWatchState = TeamsWatchState.WATCHING
) -> tuple[TeamsGroup, str]:
    chat = TeamsGroup(
        graph_chat_id=f"19:{uuid.uuid4().hex}@thread.v2",
        title="PRJ ITC DS - Alex Sample - Demo - 1/9/2026 - 31/3/2027",
        match_status=TeamsChatMatch.MATCHED.value,
        watch_state=watch.value,
    )
    db.add(chat)
    await db.flush()
    subscription_id = f"sub-{uuid.uuid4().hex[:8]}"
    db.add(
        GraphSubscription(
            subscription_id=subscription_id,
            teams_group_id=chat.id,
            resource=f"/chats/{chat.graph_chat_id}/messages",
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    await db.flush()
    return chat, subscription_id


def _note(subscription_id: str, state: str = STATE, **extra: Any) -> dict[str, Any]:
    return {
        "subscriptionId": subscription_id,
        "clientState": state,
        "changeType": "created",
        "resource": "chats('19:x@thread.v2')/messages('1')",
        "tenantId": TENANT,
        **extra,
    }


class TestValidation:
    @pytest.mark.parametrize("path", [CHANGES, LIFECYCLE])
    async def test_the_validation_token_is_echoed_as_text(
        self, client: AsyncClient, path: str
    ) -> None:
        response = await client.post(
            path, params={"validationToken": "Validation: a b"}
        )

        assert response.status_code == 200
        assert response.text == "Validation: a b"
        assert response.headers["content-type"].startswith("text/plain")


class TestRefused:
    async def test_a_wrong_client_state_is_refused(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _fresh_processing_queue: ProcessingQueue,
    ) -> None:
        chat, sub = await _subscribed_chat(db_session)

        response = await client.post(CHANGES, json={"value": [_note(sub, "guess")]})

        assert response.status_code == 403
        await db_session.refresh(chat)
        assert chat.sync_requested_at is None
        assert _fresh_processing_queue.snapshot().depth == 0

    async def test_another_tenant_is_refused(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _chat, sub = await _subscribed_chat(db_session)
        note = _note(sub, tenantId="ffffffff-0000-4000-8000-000000000000")

        response = await client.post(CHANGES, json={"value": [note]})

        assert response.status_code == 403

    async def test_nothing_is_accepted_without_a_configured_client_state(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "graph_client_state", "")
        _chat, sub = await _subscribed_chat(db_session)

        response = await client.post(CHANGES, json={"value": [_note(sub, "")]})

        assert response.status_code == 403

    async def test_a_body_that_is_not_a_notification_list_is_refused(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(CHANGES, json={"nothing": []})
        assert response.status_code == 422


class TestChanges:
    async def test_a_change_records_the_request_and_queues_one_sync(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _fresh_processing_queue: ProcessingQueue,
    ) -> None:
        chat, sub = await _subscribed_chat(db_session)

        response = await client.post(
            CHANGES, json={"value": [_note(sub), _note(sub, changeType="updated")]}
        )

        assert response.status_code == 202
        await db_session.refresh(chat)
        assert chat.sync_requested_at is not None
        (job,) = _fresh_processing_queue.snapshot().pending
        assert (job.kind, job.id, job.priority) == (
            SYNC_JOB_KIND,
            chat.id,
            CHAT_PRIORITY,
        )

    async def test_only_the_notifications_with_the_client_state_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _fresh_processing_queue: ProcessingQueue,
    ) -> None:
        chat, sub = await _subscribed_chat(db_session)
        other, other_sub = await _subscribed_chat(db_session)

        response = await client.post(
            CHANGES, json={"value": [_note(sub), _note(other_sub, "guess")]}
        )

        assert response.status_code == 202
        assert [j.id for j in _fresh_processing_queue.snapshot().pending] == [chat.id]

    @pytest.mark.parametrize("watch", [TeamsWatchState.STOPPED, None])
    async def test_one_for_a_chat_not_watched_or_unknown_is_dropped(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _fresh_processing_queue: ProcessingQueue,
        watch: TeamsWatchState | None,
    ) -> None:
        if watch is None:
            sub = "never-made"
        else:
            _chat, sub = await _subscribed_chat(db_session, watch=watch)

        response = await client.post(CHANGES, json={"value": [_note(sub)]})

        assert response.status_code == 202
        assert _fresh_processing_queue.snapshot().depth == 0


class TestLifecycle:
    @pytest.mark.parametrize(
        ("event", "kind", "reason"),
        [
            ("reauthorizationRequired", SUBSCRIPTION_JOB_KIND, "renew"),
            ("subscriptionRemoved", SUBSCRIPTION_JOB_KIND, "recreate"),
            ("missed", SYNC_JOB_KIND, None),
        ],
    )
    async def test_each_event_queues_what_it_asks_for(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _fresh_processing_queue: ProcessingQueue,
        event: str,
        kind: str,
        reason: str | None,
    ) -> None:
        chat, sub = await _subscribed_chat(db_session)

        response = await client.post(
            LIFECYCLE, json={"value": [_note(sub, lifecycleEvent=event)]}
        )

        assert response.status_code == 202
        (job,) = _fresh_processing_queue.snapshot().pending
        assert (job.kind, job.id, job.reason) == (kind, chat.id, reason)
        await db_session.refresh(chat)
        assert (chat.sync_requested_at is not None) == (event == "missed")
