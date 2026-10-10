"""The risk board and the placement (consultant) page, as the frontend reads them.

Both read stored snapshots and flags; nothing here scores. Scope is decided
before these run: the board lists the caller's ``ListScope``, and the page is
reached only through the logged placement-scope guard.

An SME sees the technical view (``sees_technical_only``): the Technical score
and its own trend, the Technical evidence, and the register's dates, status
and people. No overall, RAG level, overall trend, flags or other dimension,
and their board is ordered by Technical score so the order cannot reveal the
overall ranking.
"""

import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.health_repo import HealthRepository
from app.db.repositories.placement_repo import PlacementRepository, PlacementRow
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.signal_repo import SignalRepository
from app.db.repositories.user_repo import UserRepository
from app.health.config import load_health_config
from app.health.scoring import local_date
from app.models.enums import (
    ActionStatus,
    Dimension,
    ExtensionStatus,
    FlagSeverity,
    HealthView,
    IssueStatus,
    PlacementStatus,
    Polarity,
    RiskLevel,
    RiskTrigger,
    SessionKind,
    SessionStatus,
    SignalIndicator,
    SnapshotReason,
    SourceKind,
    SpeakerRole,
    Trend,
)
from app.models.health import HealthSnapshot, RiskFlag
from app.models.register import Placement
from app.models.signal import Action, Signal
from app.models.user import User
from app.schemas.health import (
    Contributor,
    DimensionEvidence,
    DimensionScores,
    EvidenceSignal,
    FlagDetail,
    FlagSummary,
    NextAction,
    OpenIssue,
    OtherPlacement,
    PlacementAction,
    PlacementHealth,
    PlacementSession,
    RagThresholds,
    RegisterFields,
    RiskBoardRow,
    SnapshotDetail,
    SnapshotPoint,
)
from app.schemas.sessions import NamedRef, PersonView
from app.utils.entitlements import (
    ListScope,
    Principal,
    list_scope,
    sees_technical_only,
)
from app.utils.exceptions import NotFoundError

# Board order: red first, then by trend (falling first); no snapshot or no
# score sorts last.
_LEVEL_ORDER = {
    RiskLevel.RED.value: 0,
    RiskLevel.AMBER.value: 1,
    RiskLevel.GREEN.value: 2,
}
_TREND_ORDER = {Trend.DOWN.value: 0, Trend.FLAT.value: 1, Trend.UP.value: 2}
_LAST = 99


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HealthViewService:
    def __init__(
        self, db: AsyncSession, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.db = db
        self.health = HealthRepository(db)
        self.placements = PlacementRepository(db)
        self.sessions = SessionRepository(db)
        self.signals = SignalRepository(db)
        self.users = UserRepository(db)
        self._clock = clock or _utc_now

    def _today(self) -> date:
        return local_date(self._clock(), ZoneInfo(settings.health_timezone))

    async def risk_board(self, user: Principal) -> list[RiskBoardRow]:
        """Every active placement in the caller's scope, in board order."""
        technical = sees_technical_only(user)
        rows = await self.placements.active_rows(list_scope(user))
        ids = [row.placement.id for row in rows]
        snapshots = await self.health.latest_snapshots(ids)
        flags = {} if technical else await self.health.open_flags_for(ids)
        last_calls = await self.sessions.last_completed_calls(ids)
        next_actions = await self.signals.next_due_actions(ids)
        today = self._today()
        tz = ZoneInfo(settings.health_timezone)

        board = [
            _board_row(
                row,
                snapshots.get(row.placement.id),
                flags.get(row.placement.id, []),
                last_calls.get(row.placement.id),
                next_actions.get(row.placement.id),
                today=today,
                tz=tz,
                technical=technical,
            )
            for row in rows
        ]
        board.sort(key=_technical_order if technical else _board_order)
        return board

    async def placement_health(
        self, placement: Placement, user: Principal
    ) -> PlacementHealth:
        """The placement page; the caller's scope is already checked."""
        technical = sees_technical_only(user)
        row = await self.placements.get_row(placement.id)
        if row is None:
            raise NotFoundError("Placement", str(placement.id))
        history = await self.health.history(placement.id)
        latest = history[-1] if history else None
        flags = [] if technical else await self.health.open_flags(placement.id)

        # Every signal the page quotes, in one read.
        wanted: set[uuid.UUID] = set()
        if latest is not None:
            wanted |= _contributor_ids(latest.evidence, technical)
        for flag in flags:
            wanted |= set(flag.evidence_signal_ids)
        signals = await self.signals.signals_by_id(wanted)

        sessions = await self.sessions.list_rows(
            ListScope(everything=True, named_user_id=None),
            placement_id=placement.id,
            signal_dimension=Dimension.TECHNICAL.value if technical else None,
        )
        issues = await self.signals.open_issues(placement.id)
        actions = await self.signals.actions_for_placement(placement.id)
        owners = await self._owners(row, actions)
        others = await self.placements.rows_for_consultant(
            row.consultant.id, list_scope(user)
        )

        today = self._today()
        return PlacementHealth(
            placement_id=placement.id,
            view=HealthView.TECHNICAL if technical else HealthView.FULL,
            consultant=NamedRef(id=row.consultant.id, name=row.consultant.full_name),
            client=NamedRef(id=row.client.id, name=row.client.name),
            project=NamedRef(id=row.project.id, name=row.project.name),
            weeks_in=_weeks_in(row.placement.start_date, today),
            register_fields=_register(row, technical),
            latest=_snapshot_detail(latest, signals, technical) if latest else None,
            history=[_snapshot_point(s, technical) for s in history],
            open_flags=[
                FlagDetail(
                    id=flag.id,
                    trigger=RiskTrigger(flag.trigger),
                    severity=FlagSeverity(flag.severity),
                    opened_at=flag.opened_at,
                    evidence=_evidence_signals(flag.evidence_signal_ids, signals),
                )
                for flag in flags
            ],
            sessions=[
                PlacementSession(
                    id=s.session.id,
                    held_at=s.session.held_at,
                    kind=SessionKind(s.session.kind) if s.session.kind else None,
                    status=SessionStatus(s.session.status),
                    duration_seconds=s.session.duration_seconds,
                    signal_count=s.signal_count,
                    action_count=s.action_count,
                )
                for s in sessions
            ],
            open_issues=[
                OpenIssue(
                    id=issue.id,
                    topic=issue.topic,
                    status=IssueStatus(issue.status),
                    occurrence_count=issue.occurrence_count,
                    first_seen_at=issue.first_seen_at,
                    last_seen_at=issue.last_seen_at,
                )
                for issue in issues
            ],
            actions=[_placement_action(action, owners) for action in actions],
            other_placements=[
                OtherPlacement(
                    id=other.placement.id,
                    client=NamedRef(id=other.client.id, name=other.client.name),
                    project=NamedRef(id=other.project.id, name=other.project.name),
                    start_date=other.placement.start_date,
                    expected_end_date=other.placement.expected_end_date,
                    status=PlacementStatus(other.placement.status),
                )
                for other in others
                if other.placement.id != placement.id
            ],
            thresholds=_thresholds(),
        )

    async def _owners(
        self, row: PlacementRow, actions: Iterable[Action]
    ) -> dict[uuid.UUID, User]:
        people: dict[uuid.UUID, User] = {
            person.id: person
            for person in (row.ps, row.sme, row.tech_lead)
            if person is not None
        }
        missing = {
            a.owner_user_id
            for a in actions
            if a.owner_user_id is not None and a.owner_user_id not in people
        }
        for person in await self.users.get_by_ids(missing):
            people[person.id] = person
        return people


def _weeks_in(start: date, today: date) -> int:
    """Whole weeks since the start; 0 before it."""
    return max(0, (today - start).days // 7)


def _thresholds() -> RagThresholds:
    """The RAG thresholds of the configuration in use, for the page's bands."""
    rag = load_health_config(settings.health_config_version).rag
    return RagThresholds(green_from=rag.green_min, amber_from=rag.amber_min)


def _person(user: User | None) -> PersonView | None:
    if user is None:
        return None
    return PersonView(id=user.id, full_name=user.full_name, email=user.email)


def _board_row(
    row: PlacementRow,
    snapshot: HealthSnapshot | None,
    flags: list[RiskFlag],
    last_call: datetime | None,
    next_action: Action | None,
    *,
    today: date,
    tz: ZoneInfo,
    technical: bool,
) -> RiskBoardRow:
    full = not technical
    scored = snapshot is not None and snapshot.scored
    return RiskBoardRow(
        placement_id=row.placement.id,
        view=HealthView.TECHNICAL if technical else HealthView.FULL,
        consultant=NamedRef(id=row.consultant.id, name=row.consultant.full_name),
        client=NamedRef(id=row.client.id, name=row.client.name),
        project=NamedRef(id=row.project.id, name=row.project.name),
        ps=_person(row.ps),
        tech_lead=_person(row.tech_lead),
        start_date=row.placement.start_date,
        weeks_in=_weeks_in(row.placement.start_date, today),
        scored=scored,
        computed_at=snapshot.computed_at if snapshot else None,
        overall=snapshot.overall if snapshot and full else None,
        risk_level=_level(snapshot.risk_level) if snapshot and full else None,
        trend=_trend(snapshot.trend) if snapshot and full else None,
        trend_delta=snapshot.trend_delta if snapshot and full else None,
        technical=snapshot.technical if snapshot else None,
        technical_trend=_trend(snapshot.technical_trend) if snapshot else None,
        technical_trend_delta=snapshot.technical_trend_delta if snapshot else None,
        open_flags=[
            FlagSummary(
                id=flag.id,
                trigger=RiskTrigger(flag.trigger),
                severity=FlagSeverity(flag.severity),
                opened_at=flag.opened_at,
            )
            for flag in flags
        ]
        if full
        else [],
        last_call_at=last_call,
        days_since_last_call=(today - local_date(last_call, tz)).days
        if last_call
        else None,
        next_action=NextAction(
            id=next_action.id,
            description=next_action.description,
            owner_role=SpeakerRole(next_action.owner_role),
            due_date=next_action.due_date,
        )
        if next_action is not None and next_action.due_date is not None
        else None,
    )


def _name_order(row: RiskBoardRow) -> tuple[str, str, str, str]:
    return (
        row.consultant.name.casefold(),
        row.client.name.casefold(),
        row.project.name.casefold(),
        str(row.placement_id),
    )


def _board_order(row: RiskBoardRow) -> tuple[Any, ...]:
    """Red, amber, green, not scored; falling first; lowest overall; name."""
    return (
        _LEVEL_ORDER.get(row.risk_level.value, _LAST) if row.risk_level else _LAST,
        _TREND_ORDER.get(row.trend.value, _LAST) if row.trend else _LAST,
        row.overall if row.overall is not None else float("inf"),
        *_name_order(row),
    )


def _technical_order(row: RiskBoardRow) -> tuple[Any, ...]:
    """An SME's board: lowest Technical score first, not scored last; name."""
    return (
        row.technical if row.technical is not None else float("inf"),
        *_name_order(row),
    )


def _level(value: str | None) -> RiskLevel | None:
    return RiskLevel(value) if value is not None else None


def _trend(value: str | None) -> Trend | None:
    return Trend(value) if value is not None else None


def _scores(snapshot: HealthSnapshot, technical: bool) -> DimensionScores:
    full = not technical
    return DimensionScores(
        delivery=snapshot.delivery if full else None,
        technical=snapshot.technical,
        relationship=snapshot.relationship if full else None,
        engagement=snapshot.engagement if full else None,
        onboarding=snapshot.onboarding if full else None,
        communication=snapshot.communication if full else None,
    )


def _shown_dimensions(technical: bool) -> list[Dimension]:
    return [Dimension.TECHNICAL] if technical else list(Dimension)


def _contributor_ids(evidence: Mapping[str, Any], technical: bool) -> set[uuid.UUID]:
    return {
        uuid.UUID(str(c["signal_id"]))
        for dimension in _shown_dimensions(technical)
        for c in evidence.get(dimension.value, {}).get("contributors", [])
    }


def _evidence_signal(signal: Signal) -> EvidenceSignal:
    return EvidenceSignal(
        id=signal.id,
        source_kind=SourceKind(signal.source_kind),
        source_id=signal.source_id,
        dimension=Dimension(signal.dimension),
        polarity=Polarity(signal.polarity),
        severity=signal.severity,
        confidence=signal.confidence,
        quote=signal.quote,
        note=signal.note,
        speaker_role=SpeakerRole(signal.speaker_role) if signal.speaker_role else None,
        occurred_at=signal.occurred_at,
        offset_ms=signal.offset_ms,
        indicator=SignalIndicator(signal.indicator) if signal.indicator else None,
    )


def _evidence_signals(
    ids: Iterable[uuid.UUID], signals: Mapping[uuid.UUID, Signal]
) -> list[EvidenceSignal]:
    """The signals by id, newest said first."""
    found = [signals[i] for i in ids if i in signals]
    found.sort(key=lambda s: (s.occurred_at, s.offset_ms or 0, str(s.id)), reverse=True)
    return [_evidence_signal(s) for s in found]


def _snapshot_detail(
    snapshot: HealthSnapshot, signals: Mapping[uuid.UUID, Signal], technical: bool
) -> SnapshotDetail:
    full = not technical
    evidence: list[DimensionEvidence] = []
    for dimension in _shown_dimensions(technical):
        stored = snapshot.evidence.get(dimension.value)
        if stored is None:
            continue
        evidence.append(
            DimensionEvidence(
                dimension=dimension,
                signal_count=int(stored.get("signal_count", 0)),
                contributors=[
                    Contributor(
                        signal=_evidence_signal(signals[signal_id]),
                        weight=float(c["weight"]),
                        value=float(c["value"]),
                    )
                    for c in stored.get("contributors", [])
                    if (signal_id := uuid.UUID(str(c["signal_id"]))) in signals
                ],
            )
        )
    return SnapshotDetail(
        computed_at=snapshot.computed_at,
        reason=SnapshotReason(snapshot.reason),
        scored=snapshot.scored,
        scores=_scores(snapshot, technical),
        overall=snapshot.overall if full else None,
        risk_level=_level(snapshot.risk_level) if full else None,
        trend=_trend(snapshot.trend) if full else None,
        trend_delta=snapshot.trend_delta if full else None,
        technical_trend=_trend(snapshot.technical_trend),
        technical_trend_delta=snapshot.technical_trend_delta,
        signal_count=snapshot.signal_count if full else None,
        weights_version=snapshot.weights_version,
        evidence=evidence,
    )


def _snapshot_point(snapshot: HealthSnapshot, technical: bool) -> SnapshotPoint:
    full = not technical
    return SnapshotPoint(
        computed_at=snapshot.computed_at,
        reason=SnapshotReason(snapshot.reason),
        scored=snapshot.scored,
        scores=_scores(snapshot, technical),
        overall=snapshot.overall if full else None,
        risk_level=_level(snapshot.risk_level) if full else None,
        trend=_trend(snapshot.trend) if full else None,
        technical_trend=_trend(snapshot.technical_trend),
    )


def _register(row: PlacementRow, technical: bool) -> RegisterFields:
    full = not technical
    placement = row.placement
    return RegisterFields(
        start_date=placement.start_date,
        expected_end_date=placement.expected_end_date,
        status=PlacementStatus(placement.status),
        client_manager_name=row.project.client_manager_name,
        ps=_person(row.ps),
        sme=_person(row.sme),
        tech_lead=_person(row.tech_lead),
        extension_status=ExtensionStatus(placement.extension_status) if full else None,
        rate_band=placement.rate_band if full else None,
        ended_reason=placement.ended_reason if full else None,
    )


def _placement_action(
    action: Action, people: Mapping[uuid.UUID, User]
) -> PlacementAction:
    owner = people.get(action.owner_user_id) if action.owner_user_id else None
    return PlacementAction(
        id=action.id,
        description=action.description,
        owner_role=SpeakerRole(action.owner_role),
        owner=_person(owner),
        quote=action.quote,
        offset_ms=action.offset_ms,
        due_text=action.due_text,
        due_date=action.due_date,
        status=ActionStatus(action.status),
        closed_at=action.closed_at,
        source_kind=SourceKind(action.source_kind),
        source_id=action.source_id,
    )
