"""Admin > Teams routes: each called and its response read.

Chats are seeded directly (discovery has its own tests); titles and names are
made up.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import FolderMatchStatus, ScanStatus, TeamsChatMatch
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup
from app.services.health_jobs import RECOMPUTE_JOB_KIND
from app.services.processing_queue import get_processing_queue
from app.services.teams.jobs import DISCOVERY_JOB_KIND, WATCH_JOB_KIND

ALEX_OID = "8f0c5a2e-1111-4a6b-9a35-000000000001"
PMO_OID = "8f0c5a2e-3333-4a6b-9a35-000000000003"


async def _placement(
    db: AsyncSession, name: str, client: str = "Demo Client", start: str = "2026-09-21"
) -> Placement:
    consultant = Consultant(full_name=name)
    firm = Client(
        name=f"{client} {uuid.uuid4().hex[:6]}", normalized_name=uuid.uuid4().hex
    )
    db.add_all([consultant, firm])
    await db.flush()
    project = Project(client_id=firm.id, name="Payments")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date.fromisoformat(start),
        expected_end_date=date(2027, 3, 21),
    )
    db.add(placement)
    await db.flush()
    return placement


async def _chat(db: AsyncSession, **fields: object) -> TeamsGroup:
    values: dict[str, object] = {
        "graph_chat_id": f"19:{uuid.uuid4().hex}@thread.v2",
        "title": "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027",
        "parsed_stack": "DS",
        "parsed_consultant_name": "Alex Sample",
        "parsed_client_name": "Demo Client",
        "parsed_start_date": date(2026, 9, 21),
        "parsed_end_date": date(2027, 3, 21),
        "match_status": TeamsChatMatch.UNMATCHED.value,
    }
    values.update(fields)
    chat = TeamsGroup(**values)
    db.add(chat)
    await db.flush()
    return chat


def _queued(kind: str) -> list[uuid.UUID]:
    return [j.id for j in get_processing_queue().snapshot().pending if j.kind == kind]


class TestList:
    async def test_lists_chats_with_placements_candidates_members_and_the_scan(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alex = await _placement(db_session, "Alex Sample")
        other = await _placement(db_session, "Alex Other")
        await _chat(
            db_session,
            title="PRJ ITC DS - Alex - Demo Client - 21/9/2026 - 21/3/2027",
            match_status=TeamsChatMatch.NEEDS_CHOICE.value,
            candidate_placement_ids=[str(alex.id), str(other.id)],
        )
        await _chat(
            db_session,
            title="PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027",
            match_status=TeamsChatMatch.MATCHED.value,
            placement_id=alex.id,
            watch_state="watching",
            members=[
                {"oid": ALEX_OID, "name": "Alex Sample"},
                {"oid": PMO_OID, "name": "Pat Manager"},
            ],
            consultant_member_oid=ALEX_OID,
            consultant_member_match=FolderMatchStatus.MATCHED.value,
        )
        await _chat(
            db_session,
            title="PRJ ITC - social",
            parsed_stack=None,
            parsed_consultant_name=None,
            parsed_client_name=None,
            parsed_start_date=None,
            parsed_end_date=None,
            match_status=TeamsChatMatch.UNPARSED.value,
            error_message="Title not read: found 0",
        )
        repo = TeamsRepository(db_session)
        scan = await repo.start_scan(datetime(2026, 10, 18, 9, 0, tzinfo=UTC))
        await repo.finish_scan(
            scan.id,
            finished_at=datetime(2026, 10, 18, 9, 1, tzinfo=UTC),
            status=ScanStatus.COMPLETED,
            chats_seen=3,
            chats_added=3,
            chats_matched=1,
        )

        response = await manager_client.get("/api/v1/teams/chats")

        assert response.status_code == 200
        body = response.json()
        assert body["latest_scan"]["chats_seen"] == 3
        assert body["latest_scan"]["status"] == "completed"
        assert body["discovery_enabled"] is settings.teams_discovery_enabled
        assert body["watching_enabled"] is settings.teams_enabled
        by_title = {chat["title"]: chat for chat in body["chats"]}
        choice = by_title["PRJ ITC DS - Alex - Demo Client - 21/9/2026 - 21/3/2027"]
        social = by_title["PRJ ITC - social"]
        watched = by_title[
            "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027"
        ]
        assert choice["match_status"] == "needs_choice"
        assert {c["consultant_name"] for c in choice["candidates"]} == {
            "Alex Sample",
            "Alex Other",
        }
        assert choice["placement"] is None
        assert watched["placement"]["id"] == str(alex.id)
        assert watched["placement"]["consultant_name"] == "Alex Sample"
        assert watched["placement"]["project_name"] == "Payments"
        assert watched["watch_state"] == "watching"
        assert watched["consultant_member"] == {"oid": ALEX_OID, "name": "Alex Sample"}
        assert len(watched["members"]) == 2
        assert watched["parsed"]["start_date"] == "2026-09-21"
        assert watched["quick_add_line"] == (
            "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027"
        )
        assert social["parsed"] is None
        assert social["quick_add_line"] == "PRJ ITC - social"
        assert social["error_message"] == "Title not read: found 0"

    async def test_an_empty_list_has_no_scan(self, manager_client: AsyncClient) -> None:
        body = (await manager_client.get("/api/v1/teams/chats")).json()

        assert body["chats"] == [] and body["latest_scan"] is None


class TestScan:
    async def test_queues_discovery_when_it_is_on(
        self, manager_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_discovery_enabled", True)

        first = await manager_client.post("/api/v1/teams/scan")
        second = await manager_client.post("/api/v1/teams/scan")

        assert (first.status_code, first.json()) == (202, {"queued": True})
        assert second.json() == {"queued": False}
        assert len(_queued(DISCOVERY_JOB_KIND)) == 1

    async def test_refuses_while_discovery_is_off(
        self, manager_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_discovery_enabled", False)

        response = await manager_client.post("/api/v1/teams/scan")

        assert response.status_code == 409
        assert response.json()["detail"] == "Teams discovery is off on this environment"
        assert _queued(DISCOVERY_JOB_KIND) == []


class TestChoosePlacement:
    async def test_links_the_chat_and_queues_its_review(
        self,
        manager_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        placement = await _placement(db_session, "Alex Sample")
        chat = await _chat(
            db_session,
            match_status=TeamsChatMatch.NEEDS_CHOICE.value,
            candidate_placement_ids=[str(placement.id)],
            consultant_member_oid=PMO_OID,
            consultant_member_match=FolderMatchStatus.CHOSEN.value,
        )

        response = await manager_client.put(
            f"/api/v1/teams/chats/{chat.id}/placement",
            json={"placement_id": str(placement.id)},
        )

        assert response.status_code == 204
        await db_session.refresh(chat)
        assert chat.match_status == "chosen"
        assert chat.placement_id == placement.id
        assert chat.candidate_placement_ids == []
        # A new placement may mean a new consultant: found again by the review.
        assert chat.consultant_member_match == "unmatched"
        assert chat.consultant_member_oid is None
        assert _queued(WATCH_JOB_KIND) == [chat.id]

    async def test_an_unknown_chat_or_placement_is_refused(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)

        missing_chat = await manager_client.put(
            f"/api/v1/teams/chats/{uuid.uuid4()}/placement",
            json={"placement_id": str(uuid.uuid4())},
        )
        missing_placement = await manager_client.put(
            f"/api/v1/teams/chats/{chat.id}/placement",
            json={"placement_id": str(uuid.uuid4())},
        )

        assert missing_chat.status_code == 404
        assert missing_placement.status_code == 422
        assert "does not exist" in missing_placement.json()["detail"]


class TestCreatePlacementFromTitle:
    async def test_creates_the_placement_and_links_the_chat(
        self,
        manager_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        chat = await _chat(db_session)

        response = await manager_client.post(
            f"/api/v1/teams/chats/{chat.id}/placement",
            json={"line": chat.title},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is True
        assert body["lines"][0]["outcome"] == "create"
        await db_session.refresh(chat)
        assert chat.match_status == "chosen"
        assert chat.placement_id is not None
        assert _queued(RECOMPUTE_JOB_KIND) == [chat.placement_id]
        assert _queued(WATCH_JOB_KIND) == [chat.id]

    async def test_a_line_with_an_error_writes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session)

        response = await manager_client.post(
            f"/api/v1/teams/chats/{chat.id}/placement",
            json={"line": "PRJ ITC DS - Alex Sample - Demo Client"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is False
        assert body["lines"][0]["errors"]
        await db_session.refresh(chat)
        assert chat.match_status == "unmatched"
        assert chat.placement_id is None
        assert _queued(RECOMPUTE_JOB_KIND) == []


class TestChooseConsultantMember:
    async def test_marks_the_member_and_records_their_entra_id(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session, "Alex Sample")
        chat = await _chat(
            db_session,
            match_status=TeamsChatMatch.MATCHED.value,
            placement_id=placement.id,
            members=[
                {"oid": ALEX_OID, "name": "A. Sample"},
                {"oid": PMO_OID, "name": "Pat Manager"},
            ],
            consultant_member_match=FolderMatchStatus.NEEDS_CHOICE.value,
        )

        response = await manager_client.put(
            f"/api/v1/teams/chats/{chat.id}/consultant-member",
            json={"oid": ALEX_OID},
        )

        assert response.status_code == 204
        await db_session.refresh(chat)
        assert chat.consultant_member_match == "chosen"
        assert chat.consultant_member_oid == ALEX_OID
        consultant = await db_session.get(Consultant, placement.consultant_id)
        assert consultant is not None
        await db_session.refresh(consultant)
        assert consultant.entra_oid == ALEX_OID

    async def test_someone_outside_the_chat_is_refused(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session, members=[{"oid": PMO_OID, "name": "Pat"}])

        response = await manager_client.put(
            f"/api/v1/teams/chats/{chat.id}/consultant-member",
            json={"oid": ALEX_OID},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "That person is not a member of the chat"


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("get", "/api/v1/teams/chats", None),
            ("post", "/api/v1/teams/scan", None),
            ("put", "/api/v1/teams/chats/{id}/placement", {"placement_id": "{id}"}),
            ("post", "/api/v1/teams/chats/{id}/placement", {"line": "x"}),
            ("put", "/api/v1/teams/chats/{id}/consultant-member", {"oid": "x"}),
        ],
    )
    async def test_other_roles_are_refused(
        self,
        authenticated_client: AsyncClient,
        method: str,
        path: str,
        body: dict[str, str] | None,
    ) -> None:
        some_id = str(uuid.uuid4())
        url = path.replace("{id}", some_id)
        payload = (
            {k: v.replace("{id}", some_id) for k, v in body.items()} if body else None
        )

        response = await authenticated_client.request(method, url, json=payload)

        assert response.status_code == 403
