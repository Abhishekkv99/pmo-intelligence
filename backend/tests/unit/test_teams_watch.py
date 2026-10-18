"""The watch rules: which chats are watched, who the consultant member is, and
when the review is queued."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.config import settings
from app.models.enums import FolderMatchStatus, PlacementStatus, TeamsChatMatch
from app.models.register import Consultant, Placement
from app.models.teams import TeamsGroup
from app.services.processing_queue import (
    SESSION_PRIORITY,
    ProcessingQueue,
    set_processing_queue,
)
from app.services.teams.jobs import (
    WATCH_JOB_KIND,
    WATCH_PLACEMENT_JOB_KIND,
    request_placement_watch,
    request_watch,
)
from app.services.teams.watch import chat_members, is_watchable, match_member

# 2026-10-18 09:00 UTC is 10:00 on 18 October in London.
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
ALEX_OID = "8f0c5a2e-1111-4a6b-9a35-000000000001"
SAM_OID = "8f0c5a2e-2222-4a6b-9a35-000000000002"
PMO_OID = "8f0c5a2e-3333-4a6b-9a35-000000000003"


@pytest.fixture
def queue() -> Iterator[ProcessingQueue]:
    fresh = ProcessingQueue(concurrency=1)
    set_processing_queue(fresh)
    yield fresh
    set_processing_queue(None)


def _chat(match: TeamsChatMatch = TeamsChatMatch.MATCHED) -> TeamsGroup:
    return TeamsGroup(
        graph_chat_id="19:c@thread.v2", title="PRJ ITC", match_status=match.value
    )


def _placement(
    status: PlacementStatus = PlacementStatus.ACTIVE, end: date | None = None
) -> Placement:
    return Placement(
        consultant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        start_date=date(2026, 9, 1),
        expected_end_date=end,
        status=status.value,
    )


class TestIsWatchable:
    def test_a_linked_chat_of_an_active_placement_is_watched(self) -> None:
        assert is_watchable(_chat(), _placement(end=date(2027, 3, 31)), NOW)
        assert is_watchable(_chat(TeamsChatMatch.CHOSEN), _placement(), NOW)

    def test_the_last_day_still_counts_in_uk_time(self) -> None:
        assert is_watchable(_chat(), _placement(end=date(2026, 10, 18)), NOW)
        assert not is_watchable(_chat(), _placement(end=date(2026, 10, 17)), NOW)

    @pytest.mark.parametrize(
        "match",
        [
            TeamsChatMatch.UNMATCHED,
            TeamsChatMatch.NEEDS_CHOICE,
            TeamsChatMatch.UNPARSED,
        ],
    )
    def test_a_chat_not_tied_to_a_placement_is_not_watched(
        self, match: TeamsChatMatch
    ) -> None:
        assert not is_watchable(_chat(match), _placement(), NOW)
        assert not is_watchable(_chat(), None, NOW)

    @pytest.mark.parametrize(
        "status", [PlacementStatus.ENDED, PlacementStatus.TERMINATED]
    )
    def test_an_ended_placement_is_not_watched(self, status: PlacementStatus) -> None:
        assert not is_watchable(_chat(), _placement(status=status), NOW)


class TestChatMembers:
    def test_keeps_people_with_an_entra_id(self) -> None:
        listed: list[dict[str, Any]] = [
            {"userId": ALEX_OID, "displayName": "Alex Sample"},
            {"userId": None, "displayName": "Guest without id"},
            {"displayName": "No id at all"},
            {"userId": SAM_OID},
        ]

        assert chat_members(listed) == [
            {"oid": ALEX_OID, "name": "Alex Sample"},
            {"oid": SAM_OID, "name": ""},
        ]


class TestMatchMember:
    def _members(self, *people: tuple[str, str]) -> list[dict[str, str]]:
        return [{"oid": oid, "name": name} for oid, name in people]

    def test_the_consultants_own_entra_id_wins(self) -> None:
        consultant = Consultant(full_name="Alex Sample", entra_oid=SAM_OID)
        members = self._members((ALEX_OID, "Alex Sample"), (SAM_OID, "A. S."))

        found = match_member(consultant, members)

        assert (found.status, found.oid) == (FolderMatchStatus.MATCHED, SAM_OID)

    def test_one_member_with_the_name_is_matched(self) -> None:
        members = self._members((ALEX_OID, "Alex Sample"), (PMO_OID, "Pat Manager"))

        found = match_member(Consultant(full_name="Alex Sample"), members)

        assert (found.status, found.oid) == (FolderMatchStatus.MATCHED, ALEX_OID)

    def test_the_member_with_both_names_wins_among_several(self) -> None:
        members = self._members((ALEX_OID, "Alex Sample"), (SAM_OID, "Alex Other"))

        found = match_member(Consultant(full_name="Alex Sample"), members)

        assert found.oid == ALEX_OID

    def test_two_members_the_name_may_mean_need_a_choice(self) -> None:
        members = self._members((ALEX_OID, "Alex Other"), (SAM_OID, "Alex Third"))

        found = match_member(Consultant(full_name="Alex Sample"), members)

        assert (found.status, found.oid) == (FolderMatchStatus.NEEDS_CHOICE, None)

    def test_no_member_with_the_name_is_unmatched(self) -> None:
        members = self._members((PMO_OID, "Pat Manager"), ("not-a-guid", "Alex Sample"))

        found = match_member(Consultant(full_name="Alex Sample"), members)

        assert (found.status, found.oid) == (FolderMatchStatus.UNMATCHED, None)


class TestRequests:
    def test_nothing_is_queued_while_teams_is_off(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", False)

        assert request_watch([uuid.uuid4()]) == 0
        assert request_placement_watch([uuid.uuid4()]) == 0
        assert queue.snapshot().depth == 0

    def test_each_chat_and_placement_is_queued_once_at_session_priority(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        chat, placement = uuid.uuid4(), uuid.uuid4()

        assert request_watch([chat, chat]) == 1
        assert request_watch([chat]) == 0
        assert request_placement_watch([placement, placement]) == 1

        pending = {(job.kind, job.id): job for job in queue.snapshot().pending}
        assert set(pending) == {
            (WATCH_JOB_KIND, chat),
            (WATCH_PLACEMENT_JOB_KIND, placement),
        }
        assert {job.priority for job in pending.values()} == {SESSION_PRIORITY}
