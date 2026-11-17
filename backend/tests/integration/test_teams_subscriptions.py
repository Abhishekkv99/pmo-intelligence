"""The subscription manager against a real database and a fake Graph.

Pins what the plan promises: a watched chat gets one subscription to its
messages with both notification URLs and the client state; one that expires
within a day, or that Graph asked to reauthorise, is renewed; one Graph no
longer knows, or removed, is made again; a chat no longer watched has its
subscription deleted; and nothing is made without the public URL and secret.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import TeamsChatMatch, TeamsWatchState
from app.models.teams import GraphSubscription, TeamsGroup
from app.services.teams.subscriptions import (
    RENEW_BEFORE,
    SUBSCRIPTION_LIFETIME,
    Ask,
    Outcome,
    TeamsSubscriptions,
)
from app.utils.exceptions import GraphError

BASE = "https://pmo.example.com"
STATE = "client-state-secret"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "teams_notification_base_url", BASE + "/")
    monkeypatch.setattr(settings, "graph_client_state", STATE)


class FakeGraph:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.renewed: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.renew_error: GraphError | None = None
        self.delete_error: GraphError | None = None
        self._next = 0

    async def create(self, body: dict[str, Any]) -> dict[str, Any]:
        self.created.append(body)
        self._next += 1
        return {
            "id": f"sub-{self._next}",
            "expirationDateTime": body["expirationDateTime"],
        }

    async def renew(self, subscription_id: str, expires: str) -> dict[str, Any]:
        self.renewed.append((subscription_id, expires))
        if self.renew_error:
            raise self.renew_error
        return {"id": subscription_id, "expirationDateTime": expires}

    async def delete(self, subscription_id: str) -> None:
        self.deleted.append(subscription_id)
        if self.delete_error:
            raise self.delete_error


async def _chat(
    db: AsyncSession, watch: TeamsWatchState = TeamsWatchState.WATCHING
) -> TeamsGroup:
    chat = TeamsGroup(
        graph_chat_id=f"19:{uuid.uuid4().hex}@thread.v2",
        title="PRJ ITC DS - Alex Sample - Demo - 1/9/2026 - 31/3/2027",
        match_status=TeamsChatMatch.MATCHED.value,
        watch_state=watch.value,
    )
    db.add(chat)
    await db.flush()
    return chat


async def _subscription(
    db: AsyncSession, chat: TeamsGroup, expires_in: timedelta
) -> GraphSubscription:
    sub = GraphSubscription(
        subscription_id=f"old-{uuid.uuid4().hex[:8]}",
        teams_group_id=chat.id,
        resource=f"/chats/{chat.graph_chat_id}/messages",
        expires_at=datetime.now(UTC) + expires_in,
    )
    db.add(sub)
    await db.flush()
    return sub


async def _subs(db: AsyncSession, chat: TeamsGroup) -> list[GraphSubscription]:
    rows = await db.execute(
        select(GraphSubscription).where(GraphSubscription.teams_group_id == chat.id)
    )
    return list(rows.scalars())


class TestCreate:
    async def test_a_watched_chat_gets_one_subscription(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        graph = FakeGraph()

        outcome = await TeamsSubscriptions(db_session, graph).review(chat.id)

        assert outcome == Outcome.CREATED
        (body,) = graph.created
        assert body["resource"] == f"/chats/{chat.graph_chat_id}/messages"
        assert body["changeType"] == "created,updated,deleted"
        assert body["notificationUrl"] == BASE + "/api/v1/teams/notifications"
        assert body["lifecycleNotificationUrl"] == BASE + "/api/v1/teams/lifecycle"
        assert body["clientState"] == STATE
        (sub,) = await _subs(db_session, chat)
        assert sub.subscription_id == "sub-1"
        lifetime = sub.expires_at - datetime.now(UTC)
        assert SUBSCRIPTION_LIFETIME - timedelta(minutes=1) < lifetime
        assert lifetime < timedelta(minutes=4320)

    async def test_nothing_is_made_without_the_url_and_secret(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "graph_client_state", "")
        chat = await _chat(db_session)
        graph = FakeGraph()

        with pytest.raises(GraphError):
            await TeamsSubscriptions(db_session, graph).review(chat.id)
        assert graph.created == []

    async def test_a_chat_not_watched_and_without_one_is_left_alone(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session, watch=TeamsWatchState.NOT_WATCHED)
        graph = FakeGraph()

        assert await TeamsSubscriptions(db_session, graph).review(chat.id) == (
            Outcome.NONE
        )
        assert graph.created == [] and graph.deleted == []


class TestRenew:
    async def test_one_far_from_expiry_is_kept(self, db_session: AsyncSession) -> None:
        chat = await _chat(db_session)
        await _subscription(db_session, chat, RENEW_BEFORE + timedelta(hours=1))
        graph = FakeGraph()

        assert await TeamsSubscriptions(db_session, graph).review(chat.id) == (
            Outcome.KEPT
        )
        assert graph.renewed == []

    async def test_one_expiring_within_a_day_is_renewed(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        sub = await _subscription(db_session, chat, timedelta(hours=10))
        graph = FakeGraph()

        assert await TeamsSubscriptions(db_session, graph).review(chat.id) == (
            Outcome.RENEWED
        )
        assert [r[0] for r in graph.renewed] == [sub.subscription_id]
        await db_session.refresh(sub)
        assert sub.expires_at - datetime.now(UTC) > timedelta(days=2)

    async def test_graph_asking_for_reauthorisation_renews_it(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        sub = await _subscription(db_session, chat, timedelta(days=2))
        graph = FakeGraph()

        outcome = await TeamsSubscriptions(db_session, graph).review(chat.id, Ask.RENEW)

        assert outcome == Outcome.RENEWED
        assert [r[0] for r in graph.renewed] == [sub.subscription_id]

    async def test_one_graph_no_longer_knows_is_made_again(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        await _subscription(db_session, chat, timedelta(hours=1))
        graph = FakeGraph()
        graph.renew_error = GraphError("gone", graph_status=404, graph_code="NotFound")

        outcome = await TeamsSubscriptions(db_session, graph).review(chat.id)

        assert outcome == Outcome.CREATED
        assert [s.subscription_id for s in await _subs(db_session, chat)] == ["sub-1"]

    async def test_another_renewal_failure_is_raised(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        await _subscription(db_session, chat, timedelta(hours=1))
        graph = FakeGraph()
        graph.renew_error = GraphError("busy", graph_status=503)

        with pytest.raises(GraphError):
            await TeamsSubscriptions(db_session, graph).review(chat.id)
        assert graph.created == []


class TestRecreateAndDelete:
    async def test_one_graph_removed_is_made_again(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)
        await _subscription(db_session, chat, timedelta(days=2))
        graph = FakeGraph()

        outcome = await TeamsSubscriptions(db_session, graph).review(
            chat.id, Ask.RECREATE
        )

        assert outcome == Outcome.CREATED
        assert graph.deleted == []
        assert [s.subscription_id for s in await _subs(db_session, chat)] == ["sub-1"]

    @pytest.mark.parametrize(
        "error", [None, GraphError("gone", graph_status=404, graph_code="NotFound")]
    )
    async def test_a_chat_no_longer_watched_has_it_deleted(
        self, db_session: AsyncSession, error: GraphError | None
    ) -> None:
        chat = await _chat(db_session, watch=TeamsWatchState.STOPPED)
        sub = await _subscription(db_session, chat, timedelta(days=2))
        graph = FakeGraph()
        graph.delete_error = error

        outcome = await TeamsSubscriptions(db_session, graph).review(chat.id)

        assert outcome == Outcome.DELETED
        assert graph.deleted == [sub.subscription_id]
        assert await _subs(db_session, chat) == []
