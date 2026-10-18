"""Find the PMO group chats and tie each to its placement; read no message.

One pass lists the chats of the PMO accounts in ``TEAMS_DISCOVERY_ACCOUNTS``
(``GET /users/{upn}/chats``, application ``Chat.ReadBasic.All``: titles, not
messages), merges them by chat id, keeps the group chats titled ``PRJ ITC …``,
records new ones, refreshes the titles of known ones, and ties each to its
placement from the title (``chat_titles``, ``chat_match``). Chats still
unparsed, unmatched or awaiting a choice are matched again on every pass, since
the register may have gained the placement; a chat matched or chosen by a
person is never re-matched.

Every pass writes a ``teams_scans`` row. The chats are written in one
transaction, so a pass that fails or runs past ``SCAN_TIME_LIMIT_SECONDS``
leaves them as they were and records why.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import ScanStatus, TeamsChatMatch
from app.models.teams import TeamsGroup, TeamsScan
from app.services.teams.chat_match import PlacementCandidate, match_chat
from app.services.teams.chat_titles import (
    TitleFormatError,
    is_pmo_title,
    parse_chat_title,
)
from app.services.teams.graph_client import GraphClient, get_graph_client

logger = logging.getLogger(__name__)

# Listing two accounts' chats (about 3,900 on 2026-10-14, 50 a page, one page
# per account every 1.25 s) takes under two minutes.
SCAN_TIME_LIMIT_SECONDS = 600
MAX_TITLE = 1024

# Chats whose placement is looked for again on every pass.
REMATCHED = frozenset(
    {TeamsChatMatch.UNPARSED, TeamsChatMatch.UNMATCHED, TeamsChatMatch.NEEDS_CHOICE}
)


class ChatSource(Protocol):
    async def list_chats(self, account: str) -> list[dict[str, Any]]: ...


class GraphChatSource:
    """An account's chats from Graph (titles and types, no messages)."""

    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    async def list_chats(self, account: str) -> list[dict[str, Any]]:
        return [
            chat
            async for chat in self.graph.get_all(
                f"/users/{account}/chats", params={"$top": "50"}
            )
        ]


@dataclass
class DiscoveryCounts:
    chats_seen: int = 0
    chats_added: int = 0
    chats_matched: int = 0


class TeamsDiscovery:
    def __init__(self, session: AsyncSession, source: ChatSource | None = None) -> None:
        self.session = session
        self.source = source
        self.teams = TeamsRepository(session)

    async def run(self) -> TeamsScan:
        """One pass; always ends with its ``teams_scans`` row finished.

        A pass cancelled at shutdown stays ``running`` until the next owner's
        takeover sweep fails it.
        """
        scan = await self.teams.start_scan(datetime.now(UTC))
        scan_id = scan.id
        await self.session.commit()
        try:
            async with asyncio.timeout(SCAN_TIME_LIMIT_SECONDS):
                source = self.source or GraphChatSource(get_graph_client())
                counts = await self._discover(source)
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            reason = (
                f"Stopped after {SCAN_TIME_LIMIT_SECONDS} s"
                if isinstance(exc, TimeoutError)
                else f"{type(exc).__name__}: {exc}"
            )
            logger.exception("Teams discovery %s failed: %s", scan_id, reason)
            await self.teams.finish_scan(
                scan_id,
                finished_at=datetime.now(UTC),
                status=ScanStatus.FAILED,
                error_message=reason[:2000],
            )
        else:
            logger.info(
                "Teams discovery %s: %d chats (%d new, %d matched)",
                scan_id,
                counts.chats_seen,
                counts.chats_added,
                counts.chats_matched,
            )
            await self.teams.finish_scan(
                scan_id,
                finished_at=datetime.now(UTC),
                status=ScanStatus.COMPLETED,
                **vars(counts),
            )
        await self.session.commit()
        await self.session.refresh(scan)
        return scan

    async def _discover(self, source: ChatSource) -> DiscoveryCounts:
        accounts = settings.teams_discovery_accounts
        if not accounts:
            raise ValueError("TEAMS_DISCOVERY_ACCOUNTS names no account")
        titles: dict[str, str] = {}
        for account in accounts:
            for listed in await source.list_chats(account):
                topic = (listed.get("topic") or "").strip()
                if listed.get("chatType") == "group" and is_pmo_title(topic):
                    titles[str(listed["id"])] = topic[:MAX_TITLE]

        known = await self.teams.chats_by_graph_id()
        placements = await self.teams.placement_candidates()
        counts = DiscoveryCounts(chats_seen=len(titles))
        for chat_id, title in titles.items():
            chat = known.get(chat_id)
            if chat is None:
                chat = TeamsGroup(graph_chat_id=chat_id, title=title)
                self.teams.add(chat)
                counts.chats_added += 1
                rematch = True
            else:
                chat.title = title
                rematch = TeamsChatMatch(chat.match_status) in REMATCHED
            if self._read_title(chat, rematch, placements):
                counts.chats_matched += 1
        await self.teams.flush()
        return counts

    @staticmethod
    def _read_title(
        chat: TeamsGroup, rematch: bool, placements: list[PlacementCandidate]
    ) -> bool:
        """Parse the chat's title and, when ``rematch``, tie it to its placement.

        Returns whether the chat became matched.
        """
        try:
            parsed = parse_chat_title(chat.title)
        except TitleFormatError as exc:
            chat.parsed_stack = chat.parsed_consultant_name = None
            chat.parsed_client_name = None
            chat.parsed_start_date = chat.parsed_end_date = None
            if rematch:
                chat.match_status = TeamsChatMatch.UNPARSED.value
                chat.placement_id = None
                chat.candidate_placement_ids = []
                chat.error_message = f"Title not read: {exc}"
            return False

        chat.parsed_stack = parsed.stack[:50]
        chat.parsed_consultant_name = parsed.consultant[:255]
        chat.parsed_client_name = parsed.client[:255]
        chat.parsed_start_date = parsed.start_date
        chat.parsed_end_date = parsed.end_date
        if not rematch:
            return False
        found = match_chat(parsed, placements)
        chat.match_status = found.status.value
        chat.placement_id = found.placement_id
        chat.candidate_placement_ids = [str(i) for i in found.candidate_ids]
        chat.error_message = None
        return found.status == TeamsChatMatch.MATCHED
