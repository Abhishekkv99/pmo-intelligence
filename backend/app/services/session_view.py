"""The sessions list and the session page, as the frontend reads them.

Scope is decided before these run: the list filters by the caller's
``ListScope``, and the session page is reached only through the session
scope guard. The node errors are for the global roles; everyone who may read
the session sees the rest, its cost included (PRD, "Pages").
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.placement_repo import PlacementRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.signal_repo import SignalRepository
from app.db.repositories.user_repo import UserRepository
from app.models.enums import (
    ActionStatus,
    Dimension,
    IssueStatus,
    Polarity,
    SessionKind,
    SessionSource,
    SessionStatus,
    SignalCategory,
    SourceKind,
    SpeakerRole,
)
from app.models.session import Session
from app.models.signal import Action
from app.models.user import User
from app.schemas.sessions import (
    ActionView,
    IssueView,
    NamedRef,
    PersonView,
    SessionCost,
    SessionDetail,
    SessionListItem,
    SignalView,
    SpeakerView,
    UtteranceView,
)
from app.services.media_files import playback_type
from app.services.media_token import MEDIA_URL_SECONDS, create_media_token
from app.services.storage import get_storage_backend
from app.services.storage.base import StorageBackend
from app.utils.entitlements import Principal, has_global_scope, list_scope
from app.utils.exceptions import NotFoundError

TRANSCRIPTION_SERVICE = "assemblyai"


@dataclass(frozen=True)
class MediaAccess:
    """How the browser reaches a session's recording.

    ``url`` is a presigned URL on S3. On local storage it is None and
    ``token`` is set: the route builds the URL of the token-scoped media
    route, which only it knows.
    """

    url: str | None
    token: str | None
    content_type: str


def _is_local() -> bool:
    # As ``get_storage_backend`` decides: anything but S3 is local files.
    return settings.storage_backend != "s3"


class SessionViewService:
    def __init__(
        self, db: AsyncSession, *, storage: StorageBackend | None = None
    ) -> None:
        self.db = db
        self.sessions = SessionRepository(db)
        self.signals = SignalRepository(db)
        self.placements = PlacementRepository(db)
        self.users = UserRepository(db)
        self._storage = storage

    @property
    def storage(self) -> StorageBackend:
        if self._storage is None:
            self._storage = get_storage_backend()
        return self._storage

    async def list_sessions(
        self,
        user: Principal,
        *,
        consultant_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
    ) -> list[SessionListItem]:
        rows = await self.sessions.list_rows(
            list_scope(user),
            consultant_id=consultant_id,
            status=status.value if status is not None else None,
        )
        return [
            SessionListItem(
                id=row.session.id,
                placement_id=row.session.placement_id,
                consultant=NamedRef(
                    id=row.consultant.id, name=row.consultant.full_name
                ),
                client=NamedRef(id=row.client.id, name=row.client.name),
                project=NamedRef(id=row.project.id, name=row.project.name),
                held_at=row.session.held_at,
                duration_seconds=row.session.duration_seconds,
                kind=_kind(row.session.kind),
                status=SessionStatus(row.session.status),
                error_message=row.session.error_message,
                signal_count=row.signal_count,
                action_count=row.action_count,
            )
            for row in rows
        ]

    async def detail(self, session: Session, user: Principal) -> SessionDetail:
        row = await self.placements.get_row(session.placement_id)
        if row is None:
            raise NotFoundError("Session", str(session.id))
        transcript = await self.sessions.get_transcript(session.id)
        signals, actions = await self.signals.for_source(
            SourceKind.SESSION.value, session.id
        )
        closed = await self.signals.closed_by(session.id)
        issues = await self.signals.issues_by_id(
            {s.issue_id for s in signals if s.issue_id is not None}
        )
        costs = await self.sessions.costs_by_service(session.id)

        people: dict[uuid.UUID, User] = {
            person.id: person
            for person in (row.ps, row.sme, row.tech_lead)
            if person is not None
        }
        missing = {
            a.owner_user_id
            for a in [*actions, *closed]
            if a.owner_user_id is not None and a.owner_user_id not in people
        }
        for person in await self.users.get_by_ids(missing):
            people[person.id] = person

        # Where the call first talks about each issue.
        issue_offsets: dict[uuid.UUID, int | None] = {}
        for signal in signals:
            if signal.issue_id is not None and signal.issue_id not in issue_offsets:
                issue_offsets[signal.issue_id] = signal.offset_ms

        transcription = costs.get(TRANSCRIPTION_SERVICE, 0.0)
        total = sum(costs.values())
        speakers = (transcript.speaker_roles if transcript else None) or {}
        return SessionDetail(
            id=session.id,
            placement_id=session.placement_id,
            consultant=NamedRef(id=row.consultant.id, name=row.consultant.full_name),
            client=NamedRef(id=row.client.id, name=row.client.name),
            project=NamedRef(id=row.project.id, name=row.project.name),
            held_at=session.held_at,
            duration_seconds=session.duration_seconds,
            kind=_kind(session.kind),
            kind_overridden=session.kind_overridden_by_user_id is not None,
            session_class=_kind(transcript.session_class if transcript else None),
            project_phase=transcript.project_phase if transcript else None,
            source=SessionSource(session.source),
            original_filename=session.original_filename,
            status=SessionStatus(session.status),
            error_message=session.error_message,
            quotes_rejected=session.quotes_rejected,
            has_recording=session.recording_key is not None,
            summary=transcript.summary if transcript else None,
            speakers={
                label: SpeakerView(
                    role=SpeakerRole(value["role"]), name=value.get("name")
                )
                for label, value in speakers.items()
            },
            utterances=[
                UtteranceView(
                    speaker=str(u.get("speaker", "")),
                    text=str(u.get("text", "")),
                    start_ms=int(u.get("start_ms", 0)),
                    end_ms=int(u.get("end_ms", 0)),
                )
                for u in ((transcript.utterances if transcript else None) or [])
            ],
            signals=[
                SignalView(
                    id=s.id,
                    category=SignalCategory(s.category),
                    dimension=Dimension(s.dimension),
                    polarity=Polarity(s.polarity),
                    severity=s.severity,
                    confidence=s.confidence,
                    quote=s.quote,
                    note=s.note,
                    speaker_role=SpeakerRole(s.speaker_role)
                    if s.speaker_role
                    else None,
                    offset_ms=s.offset_ms,
                    issue_id=s.issue_id,
                )
                for s in signals
            ],
            issues=[
                IssueView(
                    id=issue.id,
                    topic=issue.topic,
                    status=IssueStatus(issue.status),
                    occurrence_count=issue.occurrence_count,
                    first_seen_at=issue.first_seen_at,
                    last_seen_at=issue.last_seen_at,
                    resolved_at=issue.resolved_at,
                    offset_ms=issue_offsets.get(issue.id),
                )
                for issue in sorted(
                    issues.values(),
                    key=lambda i: (issue_offsets.get(i.id) or 0, str(i.id)),
                )
            ],
            actions=[_action_view(a, people) for a in actions],
            closed_actions=[_action_view(a, people) for a in closed],
            cost=SessionCost(
                transcription_usd=round(transcription, 4),
                analysis_usd=round(total - transcription, 4),
                total_usd=round(total, 4),
            ),
            node_errors=list(session.node_errors) if has_global_scope(user) else None,
        )

    async def media_access(self, session: Session) -> MediaAccess:
        """How to play the session's recording; 404 when it has none stored."""
        if session.recording_key is None:
            raise NotFoundError("Recording", str(session.id))
        content_type = playback_type(session.recording_key)
        if _is_local():
            return MediaAccess(
                url=None,
                token=create_media_token(session.id),
                content_type=content_type,
            )
        url = await self.storage.get_url(
            session.recording_key,
            expires_in=MEDIA_URL_SECONDS,
            content_type=content_type,
        )
        return MediaAccess(url=url, token=None, content_type=content_type)

    async def local_media(self, session_id: uuid.UUID) -> tuple[Path, str]:
        """The stored file to serve on local storage, with its type.

        404 on S3 storage (the page uses presigned URLs there) and for a
        session without a stored recording.
        """
        session = await self.sessions.get(session_id)
        if not _is_local() or session is None or session.recording_key is None:
            raise NotFoundError("Session", str(session_id))
        if not await self.storage.exists(session.recording_key):
            raise NotFoundError("Session", str(session_id))
        path = Path(await self.storage.get_url(session.recording_key))
        return path, playback_type(session.recording_key)


def _kind(value: str | None) -> SessionKind | None:
    return SessionKind(value) if value is not None else None


def _action_view(action: Action, people: dict[uuid.UUID, User]) -> ActionView:
    owner = people.get(action.owner_user_id) if action.owner_user_id else None
    return ActionView(
        id=action.id,
        description=action.description,
        owner_role=SpeakerRole(action.owner_role),
        owner=PersonView(id=owner.id, full_name=owner.full_name, email=owner.email)
        if owner is not None
        else None,
        quote=action.quote,
        offset_ms=action.offset_ms,
        due_text=action.due_text,
        due_date=action.due_date,
        status=ActionStatus(action.status),
        closed_at=action.closed_at,
    )
