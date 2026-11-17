"""One change-notification subscription per watched chat.

A watched chat has one Graph subscription to ``/chats/{id}/messages``
(``created,updated,deleted``, no resource data, so no encryption certificate):
Graph posts each change to ``/api/v1/teams/notifications`` and lifecycle
events to ``/api/v1/teams/lifecycle`` on ``TEAMS_NOTIFICATION_BASE_URL``,
each carrying ``GRAPH_CLIENT_STATE``. Graph validates both URLs while the
subscription is created, so the backend must be reachable at that URL.

The review of a chat (``teams_subscription`` job, one per chat):

- watched with no subscription: creates one (``SUBSCRIPTION_LIFETIME``, under
  Graph's 4,320-minute limit for chat messages) and records it; the caller
  then queues a sync, which reads the history the first time and otherwise
  what changed while there was no subscription;
- watched with one expiring within ``RENEW_BEFORE``, or when Graph asked
  (``reauthorizationRequired``): renews it, which also reauthorises it; one
  Graph no longer knows is made again;
- Graph removed it (``subscriptionRemoved``): makes it again;
- not watched (the placement ended): deletes it; the stored messages stay.

Reviews run after every watch review, on lifecycle events, and every
``TEAMS_SUBSCRIPTION_CHECK_SECONDS`` for every watched or subscribed chat.
"""

import enum
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import TeamsWatchState
from app.models.teams import GraphSubscription, TeamsGroup
from app.services.teams.graph_client import GraphClient, get_graph_client
from app.services.teams.messages import graph_time, parse_time
from app.utils.exceptions import GraphError

logger = logging.getLogger(__name__)

# Graph allows 4,320 minutes for chat messages; a margin for clock drift.
SUBSCRIPTION_LIFETIME = timedelta(minutes=4230)
RENEW_BEFORE = timedelta(days=1)
CHANGE_TYPES = "created,updated,deleted"
NOTIFICATION_PATH = "/api/v1/teams/notifications"
LIFECYCLE_PATH = "/api/v1/teams/lifecycle"


class Ask(enum.StrEnum):
    """Why a review runs, beyond the routine check (a job's ``reason``)."""

    RENEW = "renew"  # Graph asked for reauthorisation
    RECREATE = "recreate"  # Graph removed the subscription


class Outcome(enum.StrEnum):
    CREATED = "created"
    RENEWED = "renewed"
    KEPT = "kept"
    DELETED = "deleted"
    NONE = "none"


class SubscriptionApi(Protocol):
    async def create(self, body: dict[str, Any]) -> dict[str, Any]: ...

    async def renew(self, subscription_id: str, expires: str) -> dict[str, Any]: ...

    async def delete(self, subscription_id: str) -> None: ...


class GraphSubscriptionApi:
    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    async def create(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.graph.post("/subscriptions", body)

    async def renew(self, subscription_id: str, expires: str) -> dict[str, Any]:
        return await self.graph.patch(
            f"/subscriptions/{subscription_id}", {"expirationDateTime": expires}
        )

    async def delete(self, subscription_id: str) -> None:
        await self.graph.delete(f"/subscriptions/{subscription_id}")


def _not_found(exc: GraphError) -> bool:
    return exc.graph_status == 404


class TeamsSubscriptions:
    def __init__(
        self, session: AsyncSession, api: SubscriptionApi | None = None
    ) -> None:
        self.session = session
        self.api = api
        self.teams = TeamsRepository(session)

    def _api(self) -> SubscriptionApi:
        if self.api is None:
            self.api = GraphSubscriptionApi(get_graph_client())
        return self.api

    async def review(self, chat_id: uuid.UUID, ask: Ask | None = None) -> Outcome:
        chat = await self.teams.get_chat(chat_id)
        if chat is None:
            return Outcome.NONE
        sub = await self.teams.subscription_for_chat(chat.id)
        now = datetime.now(UTC)

        if chat.watch_state != TeamsWatchState.WATCHING.value:
            if sub is None:
                return Outcome.NONE
            await self._delete(sub)
            await self.session.commit()
            logger.info("Teams chat %s: subscription deleted (not watched)", chat.id)
            return Outcome.DELETED

        if sub is not None and ask == Ask.RECREATE:
            await self.session.delete(sub)
            await self.session.flush()
            sub = None
        if sub is None:
            await self._create(chat, now)
            await self.session.commit()
            return Outcome.CREATED
        if ask == Ask.RENEW or sub.expires_at - now < RENEW_BEFORE:
            outcome = await self._renew(chat, sub, now)
            await self.session.commit()
            return outcome
        return Outcome.KEPT

    async def _create(self, chat: TeamsGroup, now: datetime) -> None:
        base = settings.teams_notification_base_url.rstrip("/")
        if not base or not settings.graph_client_state:
            raise GraphError(
                "Teams subscriptions need TEAMS_NOTIFICATION_BASE_URL and "
                "GRAPH_CLIENT_STATE"
            )
        resource = f"/chats/{chat.graph_chat_id}/messages"
        answer = await self._api().create(
            {
                "changeType": CHANGE_TYPES,
                "notificationUrl": base + NOTIFICATION_PATH,
                "lifecycleNotificationUrl": base + LIFECYCLE_PATH,
                "resource": resource,
                "expirationDateTime": graph_time(now + SUBSCRIPTION_LIFETIME),
                "clientState": settings.graph_client_state,
            }
        )
        subscription_id = answer.get("id")
        if not isinstance(subscription_id, str) or not subscription_id:
            raise GraphError("Graph created a subscription without an id")
        expires = parse_time(answer.get("expirationDateTime")) or (
            now + SUBSCRIPTION_LIFETIME
        )
        self.session.add(
            GraphSubscription(
                subscription_id=subscription_id,
                teams_group_id=chat.id,
                resource=resource,
                expires_at=expires,
            )
        )
        logger.info(
            "Teams chat %s: subscription %s created, until %s",
            chat.id,
            subscription_id,
            expires.isoformat(),
        )

    async def _renew(
        self, chat: TeamsGroup, sub: GraphSubscription, now: datetime
    ) -> Outcome:
        expires = now + SUBSCRIPTION_LIFETIME
        try:
            answer = await self._api().renew(sub.subscription_id, graph_time(expires))
        except GraphError as exc:
            if not _not_found(exc):
                raise
            logger.warning(
                "Teams chat %s: subscription %s unknown to Graph; made again",
                chat.id,
                sub.subscription_id,
            )
            await self.session.delete(sub)
            await self.session.flush()
            await self._create(chat, now)
            return Outcome.CREATED
        sub.expires_at = parse_time(answer.get("expirationDateTime")) or expires
        logger.info(
            "Teams chat %s: subscription %s renewed, until %s",
            chat.id,
            sub.subscription_id,
            sub.expires_at.isoformat(),
        )
        return Outcome.RENEWED

    async def _delete(self, sub: GraphSubscription) -> None:
        try:
            await self._api().delete(sub.subscription_id)
        except GraphError as exc:
            if not _not_found(exc):
                raise
        await self.session.delete(sub)
