"""The sessions list, the session page and its actions, against Postgres.

Pinned here: the list shows only sessions in the caller's scope; a by-id
route answers 404 outside scope, exactly as for a missing session; only the
session page writes an ``access_log`` row; node errors are for the global
roles; the audio URL is presigned on S3 and token-scoped on local storage;
retry resumes from where the session failed; the kind is set by a person.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.main import app
from app.models.access_log import AccessLog
from app.models.enums import Role, SessionStatus
from app.models.processing_cost import ProcessingCost
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session, SessionTranscript
from app.models.signal import Action, Issue, Signal
from app.models.user import User
from app.services import session_view
from app.services.auth_service import AuthService
from app.services.media_token import create_media_token
from app.services.processing_queue import get_processing_queue
from app.services.session_service import session_job
from app.services.storage.local import LocalStorageBackend

WEBM = b"\x1a\x45\xdf\xa3" + bytes(range(256)) * 4
CALL = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {AuthService.create_access_token(user.id)}"}


class World:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def user(self, role: Role, name: str) -> User:
        user = User(
            email=f"{name.lower()}-{uuid.uuid4()}@example.com",
            full_name=name,
            role=role.value,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def placement(
        self,
        consultant_name: str,
        *,
        ps: User | None = None,
        sme: User | None = None,
        tech_lead: User | None = None,
    ) -> Placement:
        client = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
        consultant = Consultant(full_name=consultant_name)
        self.db.add_all([client, consultant])
        await self.db.flush()
        project = Project(
            client_id=client.id,
            name="Data platform",
            tech_lead_user_id=tech_lead.id if tech_lead else None,
        )
        self.db.add(project)
        await self.db.flush()
        placement = Placement(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=date(2026, 9, 1),
            ps_user_id=ps.id if ps else None,
            sme_user_id=sme.id if sme else None,
        )
        self.db.add(placement)
        await self.db.flush()
        return placement

    async def session(
        self,
        placement: Placement,
        *,
        held_at: datetime = CALL,
        status: SessionStatus = SessionStatus.COMPLETED,
        recording_key: str | None = None,
        node_errors: list[dict[str, object]] | None = None,
    ) -> Session:
        session = Session(
            placement_id=placement.id,
            held_at=held_at,
            source="upload",
            status=status.value,
            kind="technical",
            duration_seconds=1200.0,
            recording_key=recording_key,
            original_filename="call.webm",
            node_errors=node_errors or [],
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def analysed(self, placement: Placement, session: Session) -> None:
        """A transcript, an issue with its signal, another signal, two actions."""
        self.db.add(
            SessionTranscript(
                session_id=session.id,
                full_text="We are blocked on VPN access. I will raise a ticket.",
                utterances=[
                    {
                        "speaker": "A",
                        "text": "We are blocked on VPN access.",
                        "start_ms": 1000,
                        "end_ms": 4000,
                        "confidence": 0.9,
                    },
                    {
                        "speaker": "B",
                        "text": "I will raise a ticket.",
                        "start_ms": 5000,
                        "end_ms": 7000,
                        "confidence": 0.9,
                    },
                ],
                speaker_roles={
                    "A": {"role": "consultant", "name": "Priya"},
                    "B": {"role": "sme", "name": None},
                },
                summary="Priya is blocked on VPN access.",
                session_class="technical",
                project_phase="first month",
            )
        )
        issue = Issue(
            placement_id=placement.id,
            topic="VPN access",
            first_seen_at=CALL,
            last_seen_at=CALL,
        )
        self.db.add(issue)
        await self.db.flush()
        for quote, offset, issue_id in (
            ("We are blocked on VPN access.", 1000, issue.id),
            ("I will raise a ticket.", 5000, None),
        ):
            self.db.add(
                Signal(
                    placement_id=placement.id,
                    source_kind="session",
                    source_id=session.id,
                    category="issue" if issue_id else "relationship_engagement",
                    dimension="onboarding" if issue_id else "engagement",
                    polarity="negative" if issue_id else "positive",
                    severity=2,
                    confidence=0.8,
                    quote=quote,
                    speaker_role="consultant",
                    occurred_at=CALL + timedelta(milliseconds=offset),
                    offset_ms=offset,
                    issue_id=issue_id,
                )
            )
        self.db.add(
            Action(
                placement_id=placement.id,
                source_kind="session",
                source_id=session.id,
                owner_role="sme",
                owner_user_id=placement.sme_user_id,
                description="Raise a VPN ticket",
                quote="I will raise a ticket.",
                offset_ms=5000,
                due_text="tomorrow",
                due_date=date(2026, 10, 2),
            )
        )
        self.db.add(
            Action(
                placement_id=placement.id,
                source_kind="session",
                source_id=uuid.uuid4(),
                owner_role="consultant",
                description="Send the laptop request",
                quote="I sent it.",
                status="done",
                closed_at=CALL,
                closed_source_id=session.id,
            )
        )
        for service, amount in (("assemblyai", 0.07), ("azure_openai", 0.02)):
            self.db.add(
                ProcessingCost(
                    session_id=session.id,
                    service=service,
                    operation="x",
                    amount_usd=amount,
                )
            )
        await self.db.flush()


@pytest.fixture
def world(db_session: AsyncSession) -> World:
    return World(db_session)


@pytest.fixture
async def anonymous(manager_client: AsyncClient) -> AsyncGenerator[AsyncClient]:
    """A client with no Bearer token, sharing the test database overrides."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def _access_rows(db: AsyncSession) -> list[AccessLog]:
    return list((await db.execute(select(AccessLog))).scalars().all())


class TestList:
    async def test_a_manager_lists_every_session_newest_first_with_counts(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        sme = await world.user(Role.SME, "Sam")
        first = await world.placement("Priya Shah", sme=sme)
        second = await world.placement("Ann Brooks")
        older = await world.session(first, held_at=datetime(2026, 9, 1, tzinfo=UTC))
        newer = await world.session(second)
        await world.analysed(first, older)

        response = await manager_client.get("/api/v1/sessions")

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(newer.id), str(older.id)]
        analysed = body[1]
        assert analysed["consultant"]["name"] == "Priya Shah"
        assert analysed["client"]["name"] == "Acme"
        assert analysed["project"]["name"] == "Data platform"
        assert analysed["signal_count"] == 2
        assert analysed["action_count"] == 1
        assert body[0]["signal_count"] == 0

    @pytest.mark.parametrize("named_as", ["ps", "sme", "tech_lead"])
    async def test_a_named_role_lists_only_the_placements_naming_them(
        self, manager_client: AsyncClient, world: World, named_as: str
    ) -> None:
        role = {"ps": Role.PS, "sme": Role.SME, "tech_lead": Role.TECH_LEAD}[named_as]
        person = await world.user(role, "Named")
        mine = await world.placement("Priya Shah", **{named_as: person})
        theirs = await world.placement("Ann Brooks")
        visible = await world.session(mine)
        await world.session(theirs)

        response = await manager_client.get("/api/v1/sessions", headers=_bearer(person))

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [str(visible.id)]

    async def test_filters_by_consultant_and_status(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        first = await world.placement("Priya Shah")
        second = await world.placement("Ann Brooks")
        failed = await world.session(first, status=SessionStatus.FAILED)
        await world.session(first)
        await world.session(second, status=SessionStatus.FAILED)

        response = await manager_client.get(
            "/api/v1/sessions",
            params={"consultant_id": str(first.consultant_id), "status": "failed"},
        )

        assert [item["id"] for item in response.json()] == [str(failed.id)]

    async def test_listing_writes_no_access_log(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        await world.session(await world.placement("Priya Shah"))

        await manager_client.get("/api/v1/sessions")

        assert await _access_rows(db_session) == []


class TestDetail:
    async def test_the_session_page_has_everything_and_is_logged(
        self,
        manager_client: AsyncClient,
        world: World,
        db_session: AsyncSession,
        test_manager: User,
    ) -> None:
        sme = await world.user(Role.SME, "Sam")
        placement = await world.placement("Priya Shah", sme=sme)
        session = await world.session(
            placement,
            node_errors=[{"node": "actions", "error": "Timed out", "elapsed": 240}],
        )
        await world.analysed(placement, session)

        response = await manager_client.get(f"/api/v1/sessions/{session.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["consultant"]["name"] == "Priya Shah"
        assert body["summary"] == "Priya is blocked on VPN access."
        assert body["session_class"] == "technical"
        assert body["project_phase"] == "first month"
        assert body["kind_overridden"] is False
        assert body["speakers"]["A"] == {"role": "consultant", "name": "Priya"}
        assert [u["start_ms"] for u in body["utterances"]] == [1000, 5000]
        assert [s["offset_ms"] for s in body["signals"]] == [1000, 5000]
        assert [i["topic"] for i in body["issues"]] == ["VPN access"]
        assert body["issues"][0]["offset_ms"] == 1000
        assert body["actions"][0]["owner"]["full_name"] == "Sam"
        assert body["actions"][0]["due_date"] == "2026-10-02"
        assert [a["description"] for a in body["closed_actions"]] == [
            "Send the laptop request"
        ]
        assert body["cost"] == {
            "transcription_usd": 0.07,
            "analysis_usd": 0.02,
            "total_usd": 0.09,
        }
        assert body["node_errors"] == [
            {"node": "actions", "error": "Timed out", "elapsed": 240}
        ]
        rows = await _access_rows(db_session)
        assert [(r.user_id, r.placement_id, r.route) for r in rows] == [
            (test_manager.id, placement.id, f"/api/v1/sessions/{session.id}")
        ]

    async def test_a_named_role_reads_it_without_node_errors(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        placement = await world.placement("Priya Shah", ps=ps)
        session = await world.session(
            placement, node_errors=[{"node": "issues", "error": "x"}]
        )

        response = await manager_client.get(
            f"/api/v1/sessions/{session.id}", headers=_bearer(ps)
        )

        assert response.status_code == 200
        assert response.json()["node_errors"] is None
        assert len(await _access_rows(db_session)) == 1

    async def test_outside_scope_is_a_404_like_a_missing_session_and_not_logged(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        stranger = await world.user(Role.PS, "Stranger")
        session = await world.session(await world.placement("Priya Shah"))
        missing = uuid.uuid4()

        denied = await manager_client.get(
            f"/api/v1/sessions/{session.id}", headers=_bearer(stranger)
        )
        absent = await manager_client.get(
            f"/api/v1/sessions/{missing}", headers=_bearer(stranger)
        )

        assert denied.status_code == absent.status_code == 404
        assert denied.json()["detail"] == absent.json()["detail"].replace(
            str(missing), str(session.id)
        )
        assert await _access_rows(db_session) == []


class TestMedia:
    @pytest.fixture
    def local_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(settings, "storage_backend", "local")
        monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
        return tmp_path

    async def _stored(self, world: World, root: Path) -> Session:
        key = f"sessions/{uuid.uuid4()}/call.webm"
        path = root / key
        path.parent.mkdir(parents=True)
        path.write_bytes(WEBM)
        return await world.session(
            await world.placement("Priya Shah"), recording_key=key
        )

    async def test_local_storage_gives_a_token_url_that_plays_without_a_bearer(
        self,
        manager_client: AsyncClient,
        anonymous: AsyncClient,
        world: World,
        local_storage: Path,
        db_session: AsyncSession,
    ) -> None:
        session = await self._stored(world, local_storage)

        response = await manager_client.get(f"/api/v1/sessions/{session.id}/media-url")

        assert response.status_code == 200
        body = response.json()
        assert body["content_type"] == "audio/webm"
        assert body["expires_in_seconds"] == 900
        assert body["url"].startswith(
            f"http://test/api/v1/sessions/{session.id}/media?token="
        )
        played = await anonymous.get(body["url"])
        assert played.status_code == 200
        assert played.content == WEBM
        assert played.headers["content-type"] == "audio/webm"
        ranged = await anonymous.get(body["url"], headers={"Range": "bytes=4-9"})
        assert ranged.status_code == 206
        assert ranged.content == WEBM[4:10]
        assert await _access_rows(db_session) == []

    async def test_a_bad_or_other_sessions_token_is_a_404(
        self, anonymous: AsyncClient, world: World, local_storage: Path
    ) -> None:
        session = await self._stored(world, local_storage)
        other = create_media_token(uuid.uuid4())
        access = AuthService.create_access_token(uuid.uuid4())

        for token in ("nonsense", other, access):
            response = await anonymous.get(
                f"/api/v1/sessions/{session.id}/media", params={"token": token}
            )
            assert response.status_code == 404

    async def test_the_media_route_is_a_404_on_s3_storage(
        self,
        anonymous: AsyncClient,
        world: World,
        local_storage: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = await self._stored(world, local_storage)
        monkeypatch.setattr(settings, "storage_backend", "s3")

        response = await anonymous.get(
            f"/api/v1/sessions/{session.id}/media",
            params={"token": create_media_token(session.id)},
        )

        assert response.status_code == 404

    async def test_s3_storage_gives_a_presigned_url_with_the_playback_type(
        self,
        manager_client: AsyncClient,
        world: World,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        asked: list[tuple[str, int, str | None]] = []

        class Presigning(LocalStorageBackend):
            async def get_url(
                self,
                file_key: str,
                expires_in: int = 3600,
                content_type: str | None = None,
            ) -> str:
                asked.append((file_key, expires_in, content_type))
                return "https://bucket.example/signed"

        monkeypatch.setattr(settings, "storage_backend", "s3")
        monkeypatch.setattr(
            session_view, "get_storage_backend", lambda: Presigning(str(tmp_path))
        )
        session = await world.session(
            await world.placement("Priya Shah"), recording_key="sessions/x/call.webm"
        )

        response = await manager_client.get(f"/api/v1/sessions/{session.id}/media-url")

        assert response.json()["url"] == "https://bucket.example/signed"
        assert asked == [("sessions/x/call.webm", 900, "audio/webm")]

    async def test_no_stored_recording_or_outside_scope_is_a_404(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        stranger = await world.user(Role.SME, "Stranger")
        bare = await world.session(await world.placement("Priya Shah"))

        assert (
            await manager_client.get(f"/api/v1/sessions/{bare.id}/media-url")
        ).status_code == 404
        assert (
            await manager_client.get(
                f"/api/v1/sessions/{bare.id}/media-url", headers=_bearer(stranger)
            )
        ).status_code == 404


class TestKind:
    async def test_a_manager_sets_the_kind_and_it_is_marked_overridden(
        self,
        manager_client: AsyncClient,
        world: World,
        db_session: AsyncSession,
        test_manager: User,
    ) -> None:
        session = await world.session(await world.placement("Priya Shah"))

        response = await manager_client.patch(
            f"/api/v1/sessions/{session.id}/kind", json={"kind": "escalation"}
        )

        assert response.status_code == 200
        assert response.json()["kind"] == "escalation"
        assert response.json()["kind_overridden"] is True
        await db_session.refresh(session)
        assert session.kind_overridden_by_user_id == test_manager.id

    async def test_an_unknown_kind_is_a_422(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        session = await world.session(await world.placement("Priya Shah"))

        response = await manager_client.patch(
            f"/api/v1/sessions/{session.id}/kind", json={"kind": "lunch"}
        )

        assert response.status_code == 422

    async def test_a_named_role_may_not_set_the_kind(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        session = await world.session(await world.placement("Priya Shah", ps=ps))

        response = await manager_client.patch(
            f"/api/v1/sessions/{session.id}/kind",
            json={"kind": "other"},
            headers=_bearer(ps),
        )

        assert response.status_code == 403


class TestRetry:
    async def test_a_failed_session_with_a_transcript_is_analysed_again(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        placement = await world.placement("Priya Shah")
        session = await world.session(placement, status=SessionStatus.FAILED)
        session.error_message = "Analysis produced nothing; retry it"
        db_session.add(SessionTranscript(session_id=session.id, full_text="hi"))
        await db_session.flush()

        response = await manager_client.post(f"/api/v1/sessions/{session.id}/retry")

        assert response.status_code == 202
        assert response.json()["status"] == "transcribed"
        await db_session.refresh(session)
        assert session.error_message is None
        assert get_processing_queue().is_queued(session_job(session.id))

    async def test_a_failed_session_without_a_transcript_starts_again(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        session = await world.session(
            await world.placement("Priya Shah"), status=SessionStatus.FAILED
        )

        response = await manager_client.post(f"/api/v1/sessions/{session.id}/retry")

        assert response.status_code == 202
        assert response.json()["status"] == "uploaded"
        assert get_processing_queue().is_queued(session_job(session.id))

    async def test_only_a_failed_session_can_be_retried(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        session = await world.session(await world.placement("Priya Shah"))

        response = await manager_client.post(f"/api/v1/sessions/{session.id}/retry")

        assert response.status_code == 409
        assert not get_processing_queue().is_queued(session_job(session.id))

    async def test_a_named_role_may_not_retry(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        session = await world.session(
            await world.placement("Priya Shah", ps=ps), status=SessionStatus.FAILED
        )

        response = await manager_client.post(
            f"/api/v1/sessions/{session.id}/retry", headers=_bearer(ps)
        )

        assert response.status_code == 403
        count = await db_session.scalar(
            select(func.count())
            .select_from(Session)
            .where(Session.id == session.id, Session.status == "failed")
        )
        assert count == 1
