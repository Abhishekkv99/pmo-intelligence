"""The health recompute against a real database, at a fixed time.

One recompute loads a placement's signals, issues, register context and open
flags, and stores a snapshot and its flags in one commit: scores and
evidence, not scored without a signal, flags opened once and extended, never
closed by a recompute, the critical floor on the level, no new flags for an
ended placement.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    PlacementStatus,
    RiskLevel,
    RiskTrigger,
    SnapshotReason,
)
from app.models.health import HealthSnapshot, RiskFlag
from app.models.register import Client, Consultant, Placement, Project
from app.models.signal import Issue, Signal
from app.services.health_service import HealthService

# 13:00 in London on Friday 9 October 2026
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def placement(db_session: AsyncSession) -> Placement:
    client = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
    consultant = Consultant(full_name="Priya Shah")
    db_session.add_all([client, consultant])
    await db_session.flush()
    project = Project(client_id=client.id, name="Data platform")
    db_session.add(project)
    await db_session.flush()
    # Past the 30-day onboarding window, so the standard weights apply
    row = Placement(
        consultant_id=consultant.id, project_id=project.id, start_date=date(2026, 8, 1)
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _signal(db: AsyncSession, placement: Placement, **fields: object) -> Signal:
    values: dict[str, object] = {
        "placement_id": placement.id,
        "source_kind": "session",
        "source_id": uuid.uuid4(),
        "category": "client",
        "dimension": "delivery",
        "polarity": "negative",
        "severity": 2,
        "confidence": 1.0,
        "quote": "The client asked again.",
        "occurred_at": NOW,
    }
    values.update(fields)
    signal = Signal(**values)
    db.add(signal)
    await db.flush()
    return signal


async def _recompute(
    db: AsyncSession, placement: Placement, reason: SnapshotReason = SnapshotReason.CALL
) -> HealthSnapshot:
    snapshot = await HealthService(db, clock=lambda: NOW).recompute(
        placement.id, reason
    )
    assert snapshot is not None
    return snapshot


async def _open_flags(db: AsyncSession, placement: Placement) -> list[RiskFlag]:
    rows = await db.scalars(
        select(RiskFlag)
        .where(RiskFlag.placement_id == placement.id, RiskFlag.closed_at.is_(None))
        .order_by(RiskFlag.opened_at, RiskFlag.trigger)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


class TestSnapshot:
    async def test_a_scored_placement_is_stored_with_its_scores_and_evidence(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        late = await _signal(db_session, placement)

        snapshot = await _recompute(db_session, placement)

        # Delivery: (1 x 7.0 + 1 x 3.0) / 2 = 5.0; the rest sit at the prior.
        # Overall: (30 x 5.0 + 70 x 7.0) / 100 = 6.4, amber.
        assert snapshot.scored is True
        assert snapshot.delivery == 5.0
        assert snapshot.technical == 7.0
        assert snapshot.relationship == 7.0
        assert snapshot.overall == 6.4
        assert snapshot.risk_level == RiskLevel.AMBER.value
        # Nothing known 14 days ago: no trend yet
        assert snapshot.trend is None
        assert snapshot.trend_delta is None
        assert snapshot.signal_count == 1
        assert snapshot.weights_version == "v1"
        assert snapshot.reason == "call"
        assert snapshot.computed_at == NOW
        assert snapshot.evidence["delivery"] == {
            "signal_count": 1,
            "contributors": [{"signal_id": str(late.id), "weight": 1.0, "value": 3.0}],
        }
        assert snapshot.evidence["technical"] == {
            "signal_count": 0,
            "contributors": [],
        }
        assert await _open_flags(db_session, placement) == []

    async def test_signals_said_long_ago_or_on_another_placement_are_not_read(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        other = Placement(
            consultant_id=placement.consultant_id,
            project_id=placement.project_id,
            start_date=date(2026, 9, 1),
        )
        db_session.add(other)
        await db_session.flush()
        await _signal(db_session, placement, occurred_at=NOW - timedelta(days=200))
        await _signal(db_session, other)

        snapshot = await _recompute(db_session, placement)

        assert snapshot.scored is False
        assert snapshot.signal_count == 0

    async def test_without_a_signal_it_is_not_scored_but_can_still_be_flagged(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        placement.expected_end_date = date(2026, 10, 30)
        await db_session.flush()

        snapshot = await _recompute(db_session, placement, SnapshotReason.REGISTER)

        assert snapshot.scored is False
        assert snapshot.overall is None
        assert snapshot.delivery is None
        assert snapshot.risk_level is None
        assert snapshot.trend is None
        assert snapshot.evidence == {}
        assert snapshot.reason == "register"
        [flag] = await _open_flags(db_session, placement)
        assert flag.trigger == RiskTrigger.CONTRACT_HORIZON.value
        assert flag.severity == "high"
        assert flag.subject_key == ""
        assert flag.opened_at == NOW
        assert flag.evidence_signal_ids == []

    async def test_a_trend_is_stored_once_there_was_a_score_14_days_ago(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        await _signal(
            db_session,
            placement,
            polarity="positive",
            occurred_at=NOW - timedelta(days=20),
        )
        await _signal(db_session, placement, severity=3)

        snapshot = await _recompute(db_session, placement)

        assert snapshot.trend == "down"
        assert snapshot.trend_delta is not None
        assert snapshot.trend_delta < -0.5
        # Both were Delivery signals: Technical sat at 7.0 both times.
        assert snapshot.technical_trend == "flat"
        assert snapshot.technical_trend_delta == 0.0

    async def test_the_technical_trend_is_stored_from_the_technical_score(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        # Technical 14 days ago 7.9, now 4.8 (worked in test_health_scoring)
        await _signal(
            db_session,
            placement,
            dimension="technical",
            polarity="positive",
            occurred_at=NOW - timedelta(days=20),
        )
        await _signal(db_session, placement, dimension="technical", severity=3)

        snapshot = await _recompute(db_session, placement)

        assert snapshot.technical == 4.8
        assert snapshot.technical_trend == "down"
        assert snapshot.technical_trend_delta == -3.1

    async def test_a_missing_placement_stores_nothing(
        self, db_session: AsyncSession
    ) -> None:
        result = await HealthService(db_session, clock=lambda: NOW).recompute(
            uuid.uuid4(), SnapshotReason.DAILY
        )

        assert result is None


class TestFlags:
    async def test_a_flag_is_opened_once_and_gains_new_evidence(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        first = await _signal(
            db_session,
            placement,
            category="relationship_engagement",
            dimension="engagement",
            indicator="intent_to_leave",
            occurred_at=NOW - timedelta(days=2),
        )
        await _recompute(db_session, placement)
        await _recompute(db_session, placement)
        [flag] = await _open_flags(db_session, placement)
        assert flag.trigger == RiskTrigger.INTENT_TO_LEAVE.value
        assert flag.severity == "critical"
        assert flag.evidence_signal_ids == [first.id]

        second = await _signal(
            db_session,
            placement,
            category="relationship_engagement",
            dimension="engagement",
            indicator="intent_to_leave",
            quote="I have another offer.",
        )
        await _recompute(db_session, placement)

        [same] = await _open_flags(db_session, placement)
        assert same.id == flag.id
        assert same.evidence_signal_ids == [first.id, second.id]
        assert same.opened_at == NOW

    async def test_an_open_critical_flag_keeps_a_green_placement_amber(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        for n in range(3):
            await _signal(
                db_session,
                placement,
                polarity="positive",
                quote=f"Praise {n}.",
                occurred_at=NOW - timedelta(hours=n),
            )
        await _signal(
            db_session,
            placement,
            category="client",
            dimension="relationship",
            polarity="neutral",
            indicator="consultant_change_requested",
            quote="They asked about someone else.",
        )

        snapshot = await _recompute(db_session, placement)

        assert snapshot.overall is not None
        assert snapshot.overall >= 7.0
        assert snapshot.risk_level == RiskLevel.AMBER.value
        [flag] = await _open_flags(db_session, placement)
        assert flag.trigger == RiskTrigger.CLIENT_DISSATISFACTION.value

    async def test_a_flag_the_evidence_no_longer_calls_for_stays_open(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        placement.expected_end_date = date(2026, 10, 30)
        await db_session.flush()
        await _recompute(db_session, placement)

        placement.extension_status = "confirmed"
        await db_session.flush()
        await _recompute(db_session, placement, SnapshotReason.REGISTER)

        [flag] = await _open_flags(db_session, placement)
        assert flag.trigger == RiskTrigger.CONTRACT_HORIZON.value
        assert flag.closed_at is None

    async def test_a_repeated_blocker_opens_a_flag_per_issue(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        issues = []
        for topic in ("no VPN access", "no test data"):
            issue = Issue(
                placement_id=placement.id,
                topic=topic,
                first_seen_at=NOW - timedelta(days=3),
                last_seen_at=NOW,
                occurrence_count=2,
            )
            db_session.add(issue)
            await db_session.flush()
            issues.append(issue)
        technical = await _signal(
            db_session,
            placement,
            category="issue",
            dimension="technical",
            issue_id=issues[0].id,
        )
        await _signal(
            db_session,
            placement,
            category="issue",
            dimension="delivery",
            issue_id=issues[1].id,
            quote="Still no test data.",
        )

        await _recompute(db_session, placement)

        # Only the issue with a Technical signal is a repeated blocker
        [flag] = await _open_flags(db_session, placement)
        assert flag.trigger == RiskTrigger.REPEATED_BLOCKER.value
        assert flag.subject_key == str(issues[0].id)
        assert flag.evidence_signal_ids == [technical.id]

    async def test_an_ended_placement_is_scored_but_raises_no_flags(
        self, db_session: AsyncSession, placement: Placement
    ) -> None:
        placement.status = PlacementStatus.ENDED.value
        placement.expected_end_date = date(2026, 10, 1)
        await db_session.flush()
        await _signal(db_session, placement, indicator="client_dissatisfaction")

        snapshot = await _recompute(db_session, placement)

        assert snapshot.scored is True
        assert snapshot.risk_level == RiskLevel.AMBER.value
        assert await _open_flags(db_session, placement) == []
