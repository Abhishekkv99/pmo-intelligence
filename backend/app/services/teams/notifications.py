"""What the change and lifecycle notifications from Graph ask for.

The routes check each notification's ``clientState`` first
(``require_graph_client_state``); here, each one is tied to its chat by the
subscription id Graph sends. A notification for a subscription not on record,
or for a chat no longer watched, is dropped and logged. Nothing here reads a
message: a change notification only records ``sync_requested_at`` on its chat
and queues the chat's sync, so the route can answer within Graph's limit and
many changes to one chat make one sync.

Lifecycle events: ``reauthorizationRequired`` queues the chat's subscription
renewal, ``subscriptionRemoved`` its re-creation (which then syncs what was
missed), and ``missed`` a sync.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import TeamsWatchState
from app.services.teams.jobs import request_subscription_review, request_sync
from app.services.teams.subscriptions import Ask

logger = logging.getLogger(__name__)


@dataclass
class Handled:
    queued: int = 0
    dropped: int = 0


async def _known_watched(
    session: AsyncSession, items: list[dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    """The chats (by subscription id) of the notifications that are for a
    watched chat on record; and how many were dropped."""
    ids = [str(item.get("subscriptionId") or "") for item in items]
    known = await TeamsRepository(session).subscriptions_by_id(
        [i for i in dict.fromkeys(ids) if i]
    )
    chats: dict[str, Any] = {}
    dropped = 0
    for subscription_id in ids:
        found = known.get(subscription_id)
        if found is None or found[1].watch_state != TeamsWatchState.WATCHING.value:
            dropped += 1
            logger.warning(
                "Teams notification dropped: subscription %s %s",
                subscription_id or "(none)",
                "is not on record" if found is None else "is for a chat not watched",
            )
            continue
        chats[subscription_id] = found[1]
    return chats, dropped


async def handle_changes(session: AsyncSession, items: list[dict[str, Any]]) -> Handled:
    chats, dropped = await _known_watched(session, items)
    chat_ids = list(dict.fromkeys(chat.id for chat in chats.values()))
    await TeamsRepository(session).request_sync(chat_ids, datetime.now(UTC))
    await session.commit()
    return Handled(queued=request_sync(chat_ids), dropped=dropped)


async def handle_lifecycle(
    session: AsyncSession, items: list[dict[str, Any]]
) -> Handled:
    chats, dropped = await _known_watched(session, items)
    handled = Handled(dropped=dropped)
    missed = []
    for item in items:
        chat = chats.get(str(item.get("subscriptionId") or ""))
        if chat is None:
            continue
        event = str(item.get("lifecycleEvent") or "")
        logger.info("Teams lifecycle event %s for chat %s", event, chat.id)
        if event == "reauthorizationRequired":
            handled.queued += request_subscription_review([chat.id], Ask.RENEW)
        elif event == "subscriptionRemoved":
            handled.queued += request_subscription_review([chat.id], Ask.RECREATE)
        elif event == "missed":
            missed.append(chat.id)
        else:
            logger.warning("Teams lifecycle event %r not handled", event)
    if missed:
        await TeamsRepository(session).request_sync(missed, datetime.now(UTC))
        await session.commit()
        handled.queued += request_sync(missed)
    return handled
