"""Read a watched chat's messages from Graph and store them.

One sync job per chat (``teams_sync``) does both reads, so they never overlap
for a chat:

- **History**, the first time: every message the chat has
  (``GET /chats/{id}/messages``, 50 a page, paced one page per 1.25 s by the
  Graph client), stored with ``is_history``; the chat's history state becomes
  ``stored``. Stored history is analysed only when a person asks (Phase 6).
- **Changes**, every time after: the messages changed since the newest change
  stored (``$filter=lastModifiedDateTime gt …`` with ``$orderby`` on the same
  property, as Graph requires), read again from ``WATERMARK_OVERLAP`` earlier
  so a change Graph lists a little late is not missed; storing is idempotent.

A sync runs only when a notification, a lifecycle ``missed`` event or the
daily catch-up asks for one, never on a timer: Microsoft allows polling a
Teams resource once a day at most.

Storing keeps each message once per chat (by Graph id): a new one is added, an
edited one has its text and time updated, a deleted one keeps its row with
``deleted_at`` set and the text cleared. System events (``systemEventMessage``)
are stored as such and never analysed. The author's role comes from the chat:
its consultant member, the placement's PS, SME and CDM, and the PMO managers,
by Entra id; anyone else is ``other``.

``last_synced_at`` is when the last successful sync started; a takeover
queues the chat again while ``sync_requested_at`` is newer. Nothing here logs
a message's text.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import HistoryState, SpeakerRole, TeamsWatchState
from app.models.teams import Message, TeamsGroup
from app.services.teams.graph_client import GraphClient, get_graph_client
from app.services.teams.message_text import message_text
from app.utils.exceptions import GraphError

logger = logging.getLogger(__name__)

WATERMARK_OVERLAP = timedelta(minutes=5)
PAGE_SIZE = "50"
MAX_GRAPH_ID = 100
MAX_AUTHOR_NAME = 255


class MessageSource(Protocol):
    def history(self, graph_chat_id: str) -> AsyncIterator[dict[str, Any]]: ...

    def changed_since(
        self, graph_chat_id: str, since: datetime
    ) -> AsyncIterator[dict[str, Any]]: ...


def graph_time(value: datetime) -> str:
    """A UTC time as Graph's filters take it: ``2026-11-17T10:00:00.000Z``."""
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


class GraphMessageSource:
    """A chat's messages from Graph (``Chat.Read.All``)."""

    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    def history(self, graph_chat_id: str) -> AsyncIterator[dict[str, Any]]:
        return self.graph.get_all(
            f"/chats/{graph_chat_id}/messages", params={"$top": PAGE_SIZE}
        )

    def changed_since(
        self, graph_chat_id: str, since: datetime
    ) -> AsyncIterator[dict[str, Any]]:
        return self.graph.get_all(
            f"/chats/{graph_chat_id}/messages",
            params={
                "$top": PAGE_SIZE,
                "$orderby": "lastModifiedDateTime desc",
                "$filter": f"lastModifiedDateTime gt {graph_time(since)}",
            },
        )


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True)
class GraphMessage:
    """The parts of a Graph ``chatMessage`` that are stored."""

    graph_id: str
    message_type: str
    posted_at: datetime
    last_modified_at: datetime
    deleted_at: datetime | None
    author_oid: str | None
    author_name: str | None
    body_text: str
    reply_to_id: str | None


def read_message(item: dict[str, Any]) -> GraphMessage | None:
    """The stored parts of one Graph message; None when it lacks an id or time."""
    graph_id = item.get("id")
    posted = parse_time(item.get("createdDateTime"))
    if not isinstance(graph_id, str) or not graph_id or posted is None:
        return None
    modified = parse_time(item.get("lastModifiedDateTime")) or posted
    deleted = parse_time(item.get("deletedDateTime"))
    sender = item.get("from") or {}
    user = sender.get("user") if isinstance(sender, dict) else None
    user = user if isinstance(user, dict) else {}
    oid = user.get("id")
    name = user.get("displayName")
    reply_to = item.get("replyToId")
    return GraphMessage(
        graph_id=graph_id[:MAX_GRAPH_ID],
        message_type=str(item.get("messageType") or "message")[:50],
        posted_at=posted,
        last_modified_at=max(modified, deleted or modified),
        deleted_at=deleted,
        author_oid=str(oid) if oid else None,
        author_name=str(name)[:MAX_AUTHOR_NAME] if name else None,
        body_text="" if deleted else message_text(item.get("body")),
        reply_to_id=str(reply_to)[:MAX_GRAPH_ID] if reply_to else None,
    )


@dataclass
class SyncCounts:
    read: int = 0
    added: int = 0
    edited: int = 0
    deleted: int = 0


class TeamsSync:
    def __init__(
        self, session: AsyncSession, source: MessageSource | None = None
    ) -> None:
        self.session = session
        self.source = source
        self.teams = TeamsRepository(session)

    async def sync(self, chat_id: uuid.UUID) -> SyncCounts | None:
        """Read and store the chat's history or its changes; None when the chat
        is not watched (nothing is read)."""
        row = await self.teams.chat_with_placement(chat_id)
        if row is None:
            return None
        chat, placement, _consultant = row
        if chat.watch_state != TeamsWatchState.WATCHING.value:
            logger.info("Teams chat %s: not watched; no sync", chat.id)
            return None

        started = datetime.now(UTC)
        roles = await self.teams.author_roles(placement)
        if chat.consultant_member_oid:
            roles[chat.consultant_member_oid] = SpeakerRole.CONSULTANT
        is_history = chat.history_state == HistoryState.NONE.value
        source = self.source or GraphMessageSource(get_graph_client())
        counts = SyncCounts()
        try:
            if is_history:
                items = source.history(chat.graph_chat_id)
            else:
                watermark = await self.teams.latest_modified_at(chat.id)
                since = (watermark or chat.watched_at or started) - WATERMARK_OVERLAP
                items = source.changed_since(chat.graph_chat_id, since)
            async for item in items:
                message = read_message(item)
                if message is None:
                    continue
                counts.read += 1
                await self._store(chat, message, roles, is_history, counts)
        except GraphError as exc:
            await self.session.rollback()
            logger.warning(
                "Teams chat %s: sync failed (%s stored before): %s",
                chat_id,
                counts.read,
                exc.message,
            )
            raise

        if is_history:
            chat.history_state = HistoryState.STORED.value
        chat.last_synced_at = started
        await self.session.flush()
        chat.last_message_at = await self.teams.latest_post_at(chat.id)
        await self.session.commit()
        logger.info(
            "Teams chat %s: %s synced, %d read (%d new, %d edited, %d deleted)",
            chat.id,
            "history" if is_history else "changes",
            counts.read,
            counts.added,
            counts.edited,
            counts.deleted,
        )
        return counts

    async def _store(
        self,
        chat: TeamsGroup,
        message: GraphMessage,
        roles: dict[str, SpeakerRole],
        is_history: bool,
        counts: SyncCounts,
    ) -> None:
        known = (
            await self.teams.messages_by_graph_id(chat.id, [message.graph_id])
        ).get(message.graph_id)
        if known is None:
            self.session.add(
                Message(
                    teams_group_id=chat.id,
                    graph_message_id=message.graph_id,
                    author_entra_oid=message.author_oid,
                    author_name=message.author_name,
                    author_role=_role(message, roles),
                    posted_at=message.posted_at,
                    last_modified_at=message.last_modified_at,
                    deleted_at=message.deleted_at,
                    body_text=message.body_text,
                    reply_to_message_id=message.reply_to_id,
                    message_type=message.message_type,
                    is_history=is_history,
                )
            )
            # A message first seen deleted is stored as a deletion.
            if message.deleted_at is not None:
                counts.deleted += 1
            else:
                counts.added += 1
            await self.session.flush()
            return
        if message.last_modified_at <= known.last_modified_at:
            return  # read again in the overlap: nothing changed
        known.last_modified_at = message.last_modified_at
        if message.deleted_at is not None:
            if known.deleted_at is None:
                counts.deleted += 1
            known.deleted_at = message.deleted_at
            known.body_text = ""
            return
        if message.body_text != known.body_text:
            counts.edited += 1
            known.body_text = message.body_text
            # An edited message is looked at again by the chat pipeline.
            known.analysed_at = None
            known.message_class = None
            known.is_noise = False


def _role(message: GraphMessage, roles: dict[str, SpeakerRole]) -> str | None:
    if message.message_type != "message" or message.author_oid is None:
        return None
    return roles.get(message.author_oid, SpeakerRole.OTHER).value
